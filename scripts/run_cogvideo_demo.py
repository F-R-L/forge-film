"""CogVideoX demo runner — optimized for 8GB VRAM.

Runs the multi_backend_demo story with CogVideoX-2b locally.
Model is downloaded automatically on first run (~15GB).

Usage:
    python scripts/run_cogvideo_demo.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forge.compiler.schema import ProductionPlan, Scene, SceneType
from forge.generation.cogvideo_pipeline import CogVideoPipeline
from forge.generation.router import PipelineRouter
from forge.scheduler.scheduler import ForgeScheduler
from forge.assembler.stream_assembler import StreamAssembler
from forge.continuity.color_calibration import ColorCalibrator

OUTPUT_DIR = "./output/cogvideo_demo"


def make_demo_plan() -> ProductionPlan:
    """4-scene demo — short enough to finish in reasonable time on 8GB VRAM."""
    scenes = [
        Scene(
            id="S1",
            description="A detective sits alone in a dimly lit office at night, neon signs flickering outside the rain-streaked window, shuffling through photographs on his desk",
            scene_type=SceneType.DIALOGUE,
            complexity=3,
            estimated_duration_sec=6.0,
            dependencies=[],
            assets_required=[],
        ),
        Scene(
            id="S2",
            description="Aerial view of a rainy Shanghai skyline at night, glowing skyscrapers reflected in the wet streets far below, fog rolling in from the river",
            scene_type=SceneType.LANDSCAPE,
            complexity=2,
            estimated_duration_sec=6.0,
            dependencies=[],
            assets_required=[],
        ),
        Scene(
            id="S3",
            description="The detective runs through a narrow alley in heavy rain, splashing through puddles, coat flapping, pursued by shadows behind him",
            scene_type=SceneType.ACTION,
            complexity=7,
            estimated_duration_sec=6.0,
            dependencies=["S1"],
            assets_required=[],
        ),
        Scene(
            id="S4",
            description="Close-up of a trembling hand picking up a ringing phone in a dark room, the caller ID glowing ominously in the darkness",
            scene_type=SceneType.DIALOGUE,
            complexity=3,
            estimated_duration_sec=6.0,
            dependencies=["S2", "S3"],
            assets_required=[],
        ),
    ]
    dag = {
        "S1": ["S3"],
        "S2": ["S4"],
        "S3": ["S4"],
        "S4": [],
    }
    return ProductionPlan(title="双城追踪 Demo", scenes=scenes, assets=[], dag=dag)


async def main():
    from rich.console import Console
    console = Console()

    console.print("[bold green]Forge CogVideoX Demo[/bold green]")
    console.print(f"Output: {OUTPUT_DIR}")
    console.print("[yellow]First run will download CogVideoX-2b (~15GB). Please wait...[/yellow]\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # CogVideoX pipeline with 8GB VRAM optimizations
    pipe = CogVideoPipeline(
        model_id="THUDM/CogVideoX-2b",
        device="auto",   # enables CPU offload
        dtype="float16",
    )

    # All scene types route to cogvideo for this demo
    routing = {t.value: "cogvideo" for t in SceneType.__members__.values()}
    routing["default"] = "cogvideo"
    router = PipelineRouter(backends={"cogvideo": pipe}, routing=routing)

    plan = make_demo_plan()
    console.print(f"Plan: {len(plan.scenes)} scenes, DAG: {plan.dag}\n")

    async def generate_fn(scene, assets, prev_frame=None):
        return await router.generate(scene, assets, OUTPUT_DIR, prev_frame=prev_frame)

    assembler = StreamAssembler(
        output_path=os.path.join(OUTPUT_DIR, "final.mp4"),
        timeline=[s.id for s in plan.scenes],
    )

    scheduler = ForgeScheduler(
        plan,
        generate_fn,
        num_workers=1,   # 1 worker — GPU can only run one inference at a time
        console=console,
        color_calibrator=ColorCalibrator(),
        on_scene_complete=assembler.on_scene_complete,
    )

    t0 = time.monotonic()
    results, failed = await scheduler.run({}, output_dir=OUTPUT_DIR)
    elapsed = time.monotonic() - t0

    assembler.finalize()

    console.print(f"\n[bold]Done in {elapsed:.0f}s[/bold]")
    if failed:
        console.print(f"[red]Failed: {failed}[/red]")
    console.print(f"Results: {results}")


if __name__ == "__main__":
    asyncio.run(main())
