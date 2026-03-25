import asyncio
import os
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

app = typer.Typer(help="Forge — Multi-model AI film orchestration engine")
console = Console()


@app.command()
def run(
    story_file: Path = typer.Argument(..., help="Path to story text file"),
    scenes: int = typer.Option(6, help="Number of scenes"),
    workers: int = typer.Option(0, help="Parallel workers (0 = use forge.yaml/default)"),
    backend: str = typer.Option("", help="Override all backends: mock|kling|cogvideo"),
    output: Path = typer.Option(Path("./output"), help="Output directory"),
    no_validate: bool = typer.Option(False, "--no-validate", help="Skip VLM validation"),
    config: Path = typer.Option(Path("forge.yaml"), help="Path to forge.yaml config"),
):
    """Generate a film from a story file using multi-model DAG + CPM scheduling."""
    asyncio.run(_run(story_file, scenes, workers, backend, str(output), no_validate, config))


async def _run(
    story_file: Path,
    num_scenes: int,
    workers: int,
    backend_override: str,
    output_dir: str,
    no_validate: bool,
    config_path: Path,
):
    from forge.config import ForgeConfig
    from forge.compiler.vision_compiler import VisionCompiler
    from forge.assets.cache import AssetCache
    from forge.assets.foundry import AssetFoundry
    from forge.generation.mock_pipeline import MockPipeline
    from forge.generation.router import PipelineRouter
    from forge.scheduler.scheduler import ForgeScheduler
    from forge.assembler.stream_assembler import StreamAssembler
    from forge.continuity.color_calibration import ColorCalibrator
    from forge.scheduler.cpm import compute_critical_path_with_routing

    cfg = ForgeConfig(config_path)
    story = Path(story_file).read_text(encoding="utf-8")
    t_start = time.monotonic()

    # ── Step 1: Compile story → ProductionPlan ──────────────────────────
    llm_provider = cfg.build_llm_provider()
    compiler = VisionCompiler(llm_provider)
    try:
        plan = await compiler.compile(story, num_scenes)
    except Exception as exc:
        console.print(f"[yellow]LLM compile failed ({exc}) — using mock plan[/yellow]")
        plan = _mock_plan(story, num_scenes)

    # ── Step 2: Print enhanced DAG ──────────────────────────────────────
    routing = cfg.routing
    if backend_override:
        routing = {k: backend_override for k in routing}
    _print_dag_enhanced(plan, routing, cfg)

    # ── Step 3: Build assets ────────────────────────────────────────────
    cache = AssetCache(os.path.join(output_dir, "assets"))
    imagegen_provider = cfg.build_imagegen_provider()

    async def image_gen_fn(description: str) -> str:
        return await imagegen_provider.generate(description, os.path.join(output_dir, "assets"))

    foundry = AssetFoundry(image_gen_fn, cache)
    asset_map = await foundry.build(plan.assets)

    # ── Step 4: Build backend map + router ──────────────────────────────
    backends = _build_backends(backend_override, cfg)
    router = PipelineRouter(backends=backends, routing=routing)
    console.print("[bold]Backend routing:[/bold]")
    console.print(router.describe_routing())

    def backend_used_fn(scene_id: str) -> str:
        scene = next((s for s in plan.scenes if s.id == scene_id), None)
        if scene is None:
            return "mock"
        scene_type_val = scene.scene_type.value if hasattr(scene.scene_type, "value") else str(scene.scene_type)
        return routing.get(scene_type_val, routing.get("default", "mock"))

    async def generate_fn(scene, assets, prev_frame=None):
        return await router.generate(scene, asset_map, output_dir, prev_frame=prev_frame)

    # ── Step 5: Optionally wrap with VLM validation ─────────────────────
    if not no_validate:
        vlm_provider = cfg.build_vlm_provider()
        from forge.validation.vlm_validator import VLMValidator
        validator = VLMValidator(vlm_provider)

        async def validated_generate_fn(scene, assets, prev_frame=None):
            async def _gen(s, a):
                return await router.generate(s, a, output_dir, prev_frame=prev_frame)
            return await validator.validate_with_retry(scene, asset_map, _gen)

        _generate_fn = validated_generate_fn
    else:
        _generate_fn = generate_fn

    # ── Step 6: Schedule with CPM + color calibration ───────────────────
    num_workers = workers if workers > 0 else cfg.workers
    calibrator = ColorCalibrator()
    scheduler = ForgeScheduler(
        plan,
        _generate_fn,
        num_workers=num_workers,
        console=console,
        max_retries=cfg.max_retries,
        color_calibrator=calibrator,
        backend_used_fn=backend_used_fn,
    )

    # Use routing-aware CPM durations
    from forge.scheduler.cpm import compute_critical_path_with_routing, get_priority_queue_items
    cp = compute_critical_path_with_routing(plan.dag, plan.scenes, routing)

    assembler = StreamAssembler(
        output_path=os.path.join(output_dir, "final.mp4"),
        timeline=[s.id for s in plan.scenes],
    )
    scheduler.on_scene_complete = assembler.on_scene_complete

    results, failed_scenes = await scheduler.run(asset_map, output_dir)

    if failed_scenes:
        console.print(f"[red]Failed scenes: {failed_scenes}[/red]")

    # ── Step 7: Finalize assembly ────────────────────────────────────────
    assembler.finalize()

    wall = time.monotonic() - t_start
    stats = scheduler.stats
    console.print(f"\n[bold green]Done in {wall:.1f}s[/bold green]")
    console.print(f"Parallelism efficiency: {stats.get('parallelism_efficiency', 0):.2f}x")
    console.print("Scene timings:")
    for sid, t in scheduler.timings.items():
        console.print(f"  {sid}: {t:.1f}s")


def _build_backends(backend_override: str, cfg) -> dict:
    """Build the backends dict based on override or forge.yaml routing needs."""
    from forge.generation.mock_pipeline import MockPipeline
    mock = MockPipeline()
    backends = {"mock": mock}

    # Determine which backends are actually needed
    needed = set(cfg.routing.values())
    if backend_override:
        needed = {backend_override}

    if "kling_light" in needed or "kling_heavy" in needed or backend_override == "kling":
        try:
            from forge.generation.light_pipeline import LightPipeline
            from forge.generation.heavy_pipeline import HeavyPipeline
            backends["kling_light"] = LightPipeline()
            backends["kling_heavy"] = HeavyPipeline()
        except Exception as e:
            console.print(f"[yellow]Kling backend unavailable ({e}), falling back to mock[/yellow]")
            backends["kling_light"] = mock
            backends["kling_heavy"] = mock

    if "cogvideo" in needed or backend_override == "cogvideo":
        try:
            from forge.generation.cogvideo_pipeline import CogVideoPipeline
            backends["cogvideo"] = CogVideoPipeline()
        except Exception as e:
            console.print(f"[yellow]CogVideo backend unavailable ({e}), falling back to mock[/yellow]")
            backends["cogvideo"] = mock

    # seedance / wan — placeholders (fall back to mock until implemented)
    for name in ("seedance", "wan"):
        if name in needed:
            console.print(f"[yellow]{name} backend not yet implemented, using mock[/yellow]")
            backends[name] = mock

    return backends


def _mock_plan(story: str, num_scenes: int):
    from forge.compiler.schema import ProductionPlan, Scene, SceneType
    types = list(SceneType)
    scenes = [
        Scene(
            id=f"S{i+1}",
            description=f"Scene {i+1} from story",
            complexity=3,
            scene_type=types[i % len(types)],
            estimated_duration_sec=5.0,
        )
        for i in range(num_scenes)
    ]
    dag = {s.id: [] for s in scenes}
    return ProductionPlan(title="Mock Film", scenes=scenes, assets=[], dag=dag)


def _print_dag_enhanced(plan, routing: dict, cfg=None):
    """Print DAG with scene_type, assigned backend, and CPM priority."""
    from forge.scheduler.cpm import compute_critical_path_with_routing
    cp = compute_critical_path_with_routing(plan.dag, plan.scenes, routing)
    max_cp = max(cp.values(), default=1.0)

    table = Table(title=f"Production Plan: {plan.title}", show_lines=True)
    table.add_column("Scene", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta")
    table.add_column("Backend", style="green")
    table.add_column("CP Priority", justify="right")
    table.add_column("Depends On")
    table.add_column("Description", max_width=50)

    for scene in plan.scenes:
        scene_type_val = scene.scene_type.value if hasattr(scene.scene_type, "value") else str(scene.scene_type)
        backend = routing.get(scene_type_val, routing.get("default", "mock"))
        cp_val = cp.get(scene.id, 0.0)
        cp_bar = "█" * int(8 * cp_val / max_cp) if max_cp > 0 else ""
        deps = ", ".join(plan.dag.get(scene.id, [])) or "—"
        table.add_row(
            scene.id,
            scene_type_val,
            backend,
            f"{cp_val:.0f}s {cp_bar}",
            deps,
            scene.description[:80],
        )
    console.print(table)


@app.command()
def plan(
    story_file: Path = typer.Argument(..., help="Path to story text file"),
    scenes: int = typer.Option(6, help="Number of scenes"),
    config: Path = typer.Option(Path("forge.yaml"), help="Path to forge.yaml config"),
):
    """Compile story to ProductionPlan and print enhanced DAG — no video generation."""
    asyncio.run(_plan(story_file, scenes, config))


async def _plan(story_file: Path, num_scenes: int, config_path: Path = Path("forge.yaml")):
    from forge.compiler.vision_compiler import VisionCompiler
    from forge.config import ForgeConfig
    story = Path(story_file).read_text(encoding="utf-8")
    cfg = ForgeConfig(config_path)
    llm_provider = cfg.build_llm_provider()
    if not cfg.llm_api_key:
        console.print("[yellow]No API key — using mock plan[/yellow]")
        plan = _mock_plan(story, num_scenes)
    else:
        compiler = VisionCompiler(llm_provider)
        plan = await compiler.compile(story, num_scenes)
    _print_dag_enhanced(plan, cfg.routing, cfg)


@app.command()
def webui(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(7860, help="Port to listen on"),
    share: bool = typer.Option(False, "--share", help="Create a public Gradio share link"),
):
    """Launch the Gradio Web UI for Forge."""
    from forge.webui.app import launch
    launch(host=host, port=port, share=share)


@app.command()
def benchmark(
    scenes: int = typer.Option(8, help="Number of scenes"),
    workers: int = typer.Option(4, help="Worker count"),
):
    """Benchmark Forge DAG scheduling vs serial execution."""
    asyncio.run(_benchmark(scenes, workers))


async def _benchmark(num_scenes: int, workers: int):
    from benchmarks.mock_runner import run_benchmark
    await run_benchmark(num_scenes, workers)
