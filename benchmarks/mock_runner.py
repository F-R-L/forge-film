import asyncio
import time
from forge.compiler.schema import ProductionPlan, Scene
from forge.generation.mock_pipeline import MockPipeline
from forge.scheduler.scheduler import ForgeScheduler


def make_mock_plan(num_scenes: int) -> ProductionPlan:
    scenes = [
        Scene(
            id=f"S{i+1}",
            description=f"Scene {i+1}",
            complexity=(i % 10) + 1,
            estimated_duration_sec=float((i % 5 + 1) * 10),
        )
        for i in range(num_scenes)
    ]
    # Parallel-branch DAG: first half runs in parallel, converges at the end
    # e.g. 8 scenes: S1->S5, S2->S6, S3->S7, S4->S8, S5->S8, S6->S8, S7->S8
    half = num_scenes // 2
    dag = {}
    for i, s in enumerate(scenes):
        if i < half:
            # First half: each feeds its counterpart in second half
            dag[s.id] = [scenes[i + half].id]
        elif i < num_scenes - 1:
            # Second half (except last): all feed into the final scene
            dag[s.id] = [scenes[-1].id]
        else:
            dag[s.id] = []
    return ProductionPlan(title="Benchmark Film", scenes=scenes, assets=[], dag=dag)


async def run_serial(plan: ProductionPlan) -> float:
    pipeline = MockPipeline()
    t0 = time.monotonic()
    for scene in plan.scenes:
        await pipeline.generate(scene, {}, "./output/benchmark")
    return time.monotonic() - t0


async def run_parallel(plan: ProductionPlan, workers: int) -> float:
    pipeline = MockPipeline()

    async def gen_fn(scene, assets, prev_frame=None):
        return await pipeline.generate(scene, assets, "./output/benchmark")

    scheduler = ForgeScheduler(plan, gen_fn, num_workers=workers)
    t0 = time.monotonic()
    await scheduler.run({}, output_dir="./output/benchmark")
    return time.monotonic() - t0


async def run_benchmark(num_scenes: int = 8, workers: int = 4):
    from rich.console import Console
    from rich.table import Table

    console = Console()
    plan = make_mock_plan(num_scenes)

    console.print(f"[bold]Running benchmark: {num_scenes} scenes, {workers} workers[/bold]")
    serial_time = await run_serial(plan)
    parallel_time = await run_parallel(plan, workers)
    speedup = serial_time / parallel_time if parallel_time > 0 else 0

    table = Table(title="Forge Benchmark Results")
    table.add_column("Mode", style="cyan")
    table.add_column("Time (s)", justify="right")
    table.add_column("Speedup", justify="right")
    table.add_row("Serial", f"{serial_time:.2f}", "1.0x")
    table.add_row("Forge DAG", f"{parallel_time:.2f}", f"{speedup:.1f}x")
    console.print(table)
    return serial_time, parallel_time, speedup


if __name__ == "__main__":
    asyncio.run(run_benchmark())
