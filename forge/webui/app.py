import asyncio
import os
import time
import tempfile
from pathlib import Path

import gradio as gr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


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


def _build_dag_figure(plan):
    """Return a matplotlib Figure visualizing the DAG."""
    fig, ax = plt.subplots(figsize=(max(6, len(plan.scenes) * 1.2), 4))
    ax.set_xlim(0, len(plan.scenes) + 1)
    ax.set_ylim(-1, 2)
    ax.axis("off")
    ax.set_title(f"{plan.title} — DAG", fontsize=13, fontweight="bold")

    scene_ids = [s.id for s in plan.scenes]
    x_pos = {sid: i + 1 for i, sid in enumerate(scene_ids)}
    y_pos = 0.5

    # Draw edges
    for src, dsts in plan.dag.items():
        for dst in dsts:
            if src in x_pos and dst in x_pos:
                ax.annotate(
                    "",
                    xy=(x_pos[dst], y_pos),
                    xytext=(x_pos[src], y_pos),
                    arrowprops=dict(arrowstyle="->", color="#555", lw=1.5),
                )

    # Draw nodes
    for s in plan.scenes:
        x = x_pos[s.id]
        color = plt.cm.RdYlGn(1.0 - (s.complexity - 1) / 9.0)
        circle = plt.Circle((x, y_pos), 0.35, color=color, zorder=3)
        ax.add_patch(circle)
        ax.text(x, y_pos, s.id, ha="center", va="center", fontsize=8, fontweight="bold", zorder=4)
        ax.text(x, y_pos - 0.6, f"c={s.complexity}", ha="center", va="center", fontsize=7, color="#333")

    legend = [
        mpatches.Patch(color=plt.cm.RdYlGn(0.9), label="Low complexity"),
        mpatches.Patch(color=plt.cm.RdYlGn(0.5), label="Medium"),
        mpatches.Patch(color=plt.cm.RdYlGn(0.1), label="High complexity"),
    ]
    ax.legend(handles=legend, loc="upper right", fontsize=7)
    fig.tight_layout()
    return fig


async def _run_pipeline(
    story: str,
    num_scenes: int,
    workers: int,
    backend: str,
    skip_vlm: bool,
    output_dir: str,
    log_fn,
    progress: gr.Progress,
):
    from forge.assets.cache import AssetCache
    from forge.assets.foundry import AssetFoundry
    from forge.generation.mock_pipeline import MockPipeline
    from forge.generation.light_pipeline import LightPipeline
    from forge.generation.heavy_pipeline import HeavyPipeline
    from forge.generation.router import PipelineRouter
    from forge.scheduler.scheduler import ForgeScheduler
    from forge.assembler.stream_assembler import StreamAssembler
    from rich.console import Console

    console = Console()
    t_start = time.monotonic()

    # Step 1: Compile
    progress(0.05, desc="Compiling story...")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        import openai
        client = openai.AsyncOpenAI(api_key=openai_key)
        from forge.compiler.vision_compiler import VisionCompiler
        compiler = VisionCompiler(client)
        log_fn("Using OpenAI to compile story...")
        plan = await compiler.compile(story, num_scenes)
    else:
        log_fn("WARNING: No OPENAI_API_KEY found — using mock plan")
        plan = _mock_plan(story, num_scenes)

    log_fn(f"Plan: {plan.title} ({len(plan.scenes)} scenes)")
    progress(0.15, desc="Building DAG...")

    # Step 2: Build assets
    progress(0.2, desc="Building assets...")
    cache = AssetCache(os.path.join(output_dir, "assets"))

    async def mock_image_gen(description: str) -> str:
        await asyncio.sleep(0.05)
        return ""

    foundry = AssetFoundry(mock_image_gen, cache)
    asset_map = await foundry.build(plan.assets)
    log_fn(f"Assets built: {len(plan.assets)} asset(s)")

    # Step 3: Pipeline router
    progress(0.25, desc="Setting up pipeline...")
    mock = MockPipeline()
    if backend == "kling":
        light = LightPipeline()
        heavy = HeavyPipeline()
    elif backend == "cogvideo":
        from forge.generation.cogvideo_pipeline import CogVideoPipeline
        cogvideo = CogVideoPipeline()
        light = cogvideo
        heavy = cogvideo
    else:
        light = mock
        heavy = mock
    router = PipelineRouter(
        backends={"mock": mock, "kling_light": light, "kling_heavy": heavy},
    )

    async def generate_fn(scene, assets, prev_frame=None):
        return await router.generate(scene, asset_map, output_dir, prev_frame=prev_frame)

    # Step 4: Validation setup
    if not skip_vlm and openai_key:
        from forge.validation.vlm_validator import VLMValidator
        from forge.providers.vlm import OpenAIVLMProvider
        validator = VLMValidator(OpenAIVLMProvider(api_key=openai_key))

        async def validated_generate_fn(scene, assets, prev_frame=None):
            async def _gen(s, a):
                return await router.generate(s, a, output_dir, prev_frame=prev_frame)
            return await validator.validate_with_retry(scene, asset_map, _gen)

        _generate_fn = validated_generate_fn
        log_fn("VLM validation enabled")
    else:
        _generate_fn = generate_fn
        log_fn("VLM validation skipped")

    # Step 5: Schedule
    progress(0.3, desc="Scheduling scenes...")
    log_fn(f"Scheduling {len(plan.scenes)} scenes with {workers} workers...")

    completed_count = [0]
    total = len(plan.scenes)

    original_generate = _generate_fn

    async def tracked_generate(scene, assets, prev_frame=None):
        result = await original_generate(scene, assets, prev_frame=prev_frame)
        completed_count[0] += 1
        frac = 0.3 + 0.5 * (completed_count[0] / total)
        progress(frac, desc=f"Scene {scene.id} done ({completed_count[0]}/{total})")
        log_fn(f"Scene {scene.id} complete")
        return result

    from forge.continuity.color_calibration import ColorCalibrator
    from forge.scheduler.cpm import compute_critical_path_with_routing
    default_routing = {
        "dialogue": "kling_light", "action": "kling_heavy",
        "landscape": "cogvideo", "product": "kling_heavy",
        "transition": "cogvideo", "default": "mock",
    }
    cp = compute_critical_path_with_routing(plan.dag, plan.scenes, default_routing)
    scheduler = ForgeScheduler(
        plan,
        tracked_generate,
        num_workers=workers,
        console=console,
        color_calibrator=ColorCalibrator(),
    )
    results, failed_scenes = await scheduler.run(asset_map, output_dir=output_dir, critical_path=cp)

    # Step 6: Assemble
    progress(0.85, desc="Assembling final video...")
    log_fn("Assembling video...")
    timeline = [s.id for s in plan.scenes]
    assembler = StreamAssembler(
        output_path=os.path.join(output_dir, "final.mp4"),
        timeline=timeline,
    )
    for sid, vpath in results.items():
        assembler.on_scene_complete(sid, vpath)
    final_path = assembler.finalize()

    elapsed = time.monotonic() - t_start
    log_fn(f"Done in {elapsed:.1f}s — {final_path}")
    progress(1.0, desc="Complete!")

    timings = scheduler.timings
    return plan, final_path, timings


def generate_film(
    story: str,
    num_scenes: int,
    workers: int,
    backend: str,
    skip_vlm: bool,
    progress=gr.Progress(track_tqdm=True),
):
    """Gradio-facing synchronous wrapper around the async pipeline."""
    if not story.strip():
        raise gr.Error("Please enter a story.")

    logs = []

    def log_fn(msg: str):
        logs.append(msg)

    output_dir = tempfile.mkdtemp(prefix="forge_webui_")

    plan, final_path, timings = asyncio.run(
        _run_pipeline(
            story=story,
            num_scenes=int(num_scenes),
            workers=int(workers),
            backend=backend,
            skip_vlm=skip_vlm,
            output_dir=output_dir,
            log_fn=log_fn,
            progress=progress,
        )
    )

    # DAG figure
    fig = _build_dag_figure(plan)

    # Timing table: list of [scene_id, seconds]
    timing_rows = [[sid, f"{t:.2f}s"] for sid, t in sorted(timings.items())]

    # Video path (may not exist if no real clips were generated)
    video_out = final_path if os.path.exists(final_path) else None

    log_text = "\n".join(logs)

    return fig, log_text, video_out, timing_rows


EXAMPLE_STORY = """A lone astronaut discovers a derelict space station orbiting Europa.
She enters cautiously, finding signs of a vanished crew.
Deep inside, an alien signal pulses from the ice-covered ocean below.
She must decide: transmit the signal to Earth, or bury it forever."""


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Forge Film Generator", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# Forge Film Generator\nDAG-driven parallel AI film generation")

        with gr.Row():
            with gr.Column(scale=2):
                story_input = gr.Textbox(
                    label="Story",
                    placeholder=EXAMPLE_STORY,
                    lines=6,
                    value=EXAMPLE_STORY,
                )
                with gr.Row():
                    num_scenes = gr.Slider(
                        minimum=3, maximum=12, value=6, step=1, label="Number of Scenes"
                    )
                    workers = gr.Slider(
                        minimum=1, maximum=8, value=4, step=1, label="Workers"
                    )
                with gr.Row():
                    backend = gr.Dropdown(
                        choices=["mock", "kling", "cogvideo"],
                        value="mock",
                        label="Backend",
                    )
                    skip_vlm = gr.Checkbox(
                        value=True, label="Skip VLM Validation"
                    )
                generate_btn = gr.Button("Generate Film", variant="primary")

            with gr.Column(scale=3):
                dag_plot = gr.Plot(label="DAG Visualization")
                log_output = gr.Textbox(
                    label="Progress Log", lines=10, interactive=False
                )
                video_output = gr.Video(label="Final Video")
                timing_table = gr.Dataframe(
                    headers=["Scene", "Time"],
                    label="Per-Scene Timing",
                    interactive=False,
                )

        generate_btn.click(
            fn=generate_film,
            inputs=[story_input, num_scenes, workers, backend, skip_vlm],
            outputs=[dag_plot, log_output, video_output, timing_table],
        )

    return demo


def launch(host: str = "0.0.0.0", port: int = 7860, share: bool = False):
    demo = build_ui()
    demo.launch(server_name=host, server_port=port, share=share)


if __name__ == "__main__":
    launch()
