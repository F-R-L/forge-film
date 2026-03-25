import asyncio
import os
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.tree import Tree

app = typer.Typer(help="Forge — DAG-driven parallel AI film generation")
console = Console()


@app.command()
def run(
    story_file: Path = typer.Argument(..., help="Path to story text file"),
    scenes: int = typer.Option(6, help="Number of scenes"),
    workers: int = typer.Option(4, help="Parallel worker count"),
    backend: str = typer.Option("mock", help="Video backend: mock|kling"),
    output: Path = typer.Option(Path("./output"), help="Output directory"),
    no_validate: bool = typer.Option(False, "--no-validate", help="Skip VLM validation"),
):
    """Generate a film from a story file using DAG + CPM scheduling."""
    asyncio.run(_run(story_file, scenes, workers, backend, str(output), no_validate))


async def _run(
    story_file: Path,
    num_scenes: int,
    workers: int,
    backend: str,
    output_dir: str,
    no_validate: bool,
):
    from forge.compiler.vision_compiler import VisionCompiler
    from forge.assets.cache import AssetCache
    from forge.assets.foundry import AssetFoundry
    from forge.generation.mock_pipeline import MockPipeline
    from forge.generation.light_pipeline import LightPipeline
    from forge.generation.heavy_pipeline import HeavyPipeline
    from forge.generation.router import PipelineRouter
    from forge.scheduler.scheduler import ForgeScheduler
    from forge.assembler.stream_assembler import StreamAssembler

    story = Path(story_file).read_text(encoding="utf-8")
    t_start = time.monotonic()

    # Step 1: Compile
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        import openai
        client = openai.AsyncOpenAI(api_key=openai_key)
        compiler = VisionCompiler(client)
        plan = await compiler.compile(story, num_scenes)
    else:
        console.print("[yellow]No OPENAI_API_KEY — using mock plan[/yellow]")
        plan = _mock_plan(story, num_scenes)

    # Step 2: Print DAG
    _print_dag(plan)

    # Step 3: Build assets
    cache = AssetCache(os.path.join(output_dir, "assets"))

    async def mock_image_gen(description: str) -> str:
        await asyncio.sleep(0.05)
        return ""

    foundry = AssetFoundry(mock_image_gen, cache)
    asset_map = await foundry.build(plan.assets)

    # Step 4: Pipeline router
    mock = MockPipeline()
    if backend == "kling":
        light = LightPipeline()
        heavy = HeavyPipeline()
    else:
        light = mock
        heavy = mock
    router = PipelineRouter(light=light, heavy=heavy, medium=mock)

    async def generate_fn(scene, assets, prev_frame=None):
        return await router.generate(scene, asset_map, output_dir, prev_frame=prev_frame)

    # Step 5: Schedule
    if not no_validate and openai_key:
        from forge.validation.vlm_validator import VLMValidator
        import openai as _openai
        _client = _openai.AsyncOpenAI(api_key=openai_key)
        validator = VLMValidator(_client)

        async def validated_generate_fn(scene, assets, prev_frame=None):
            async def _gen(s, a):
                return await router.generate(s, a, output_dir, prev_frame=prev_frame)
            return await validator.validate_with_retry(scene, asset_map, _gen)

        _generate_fn = validated_generate_fn
    else:
        _generate_fn = generate_fn

    scheduler = ForgeScheduler(plan, _generate_fn, num_workers=workers, console=console)
    results = await scheduler.run()

    # Step 6: Assemble
    timeline = [s.id for s in plan.scenes]  # narrative order
    assembler = StreamAssembler(
        output_path=os.path.join(output_dir, "final.mp4"),
        timeline=timeline,
    )
    for sid, vpath in results.items():
        assembler.on_scene_complete(sid, vpath)
    final_path = assembler.finalize()

    elapsed = time.monotonic() - t_start
    console.print(f"\n[bold green]Done in {elapsed:.1f}s[/bold green] — {final_path}")
    for sid, t in scheduler.timings.items():
        console.print(f"  {sid}: {t:.1f}s")


def _mock_plan(story: str, num_scenes: int):
    from forge.compiler.schema import ProductionPlan, Scene
    scenes = [
        Scene(
            id=f"S{i+1}",
            description=f"Scene {i+1} from story",
            complexity=3,
            estimated_duration_sec=5.0,
        )
        for i in range(num_scenes)
    ]
    dag = {s.id: [] for s in scenes}
    return ProductionPlan(title="Mock Film", scenes=scenes, assets=[], dag=dag)


def _print_dag(plan):
    tree = Tree(f"[bold]{plan.title}[/bold] — DAG")
    for scene in plan.scenes:
        node = tree.add(f"[cyan]{scene.id}[/cyan] (complexity={scene.complexity})")
        for dep in plan.dag.get(scene.id, []):
            node.add(f"→ {dep}")
    console.print(tree)


@app.command()
def plan(
    story_file: Path = typer.Argument(..., help="Path to story text file"),
    scenes: int = typer.Option(6, help="Number of scenes"),
):
    """Compile story to ProductionPlan and print DAG — no video generation."""
    asyncio.run(_plan(story_file, scenes))


async def _plan(story_file: Path, num_scenes: int):
    from forge.compiler.vision_compiler import VisionCompiler
    import openai
    story = Path(story_file).read_text(encoding="utf-8")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        console.print("[red]OPENAI_API_KEY required for forge plan[/red]")
        raise typer.Exit(1)
    client = openai.AsyncOpenAI(api_key=openai_key)
    compiler = VisionCompiler(client)
    plan = await compiler.compile(story, num_scenes)
    _print_dag(plan)


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
