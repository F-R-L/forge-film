import asyncio
import pytest
from forge.compiler.schema import ProductionPlan, Scene, Asset
from forge.scheduler.scheduler import ForgeScheduler


def make_plan(scenes_def: list[dict], dag: dict[str, list[str]]) -> ProductionPlan:
    scenes = [
        Scene(
            id=s["id"],
            description=s.get("description", "test scene"),
            complexity=s.get("complexity", 1),
            estimated_duration_sec=s.get("dur", 1.0),
            dependencies=s.get("deps", []),
        )
        for s in scenes_def
    ]
    return ProductionPlan(title="test", scenes=scenes, assets=[], dag=dag)


async def fast_generate(scene: Scene, assets: dict, prev_frame=None) -> str:
    await asyncio.sleep(0.01)
    return f"output/{scene.id}.mp4"


def test_scheduler_respects_dependencies():
    order = []

    async def tracked_generate(scene: Scene, assets: dict, prev_frame=None) -> str:
        order.append(scene.id)
        await asyncio.sleep(0.01)
        return f"output/{scene.id}.mp4"

    plan = make_plan(
        [{"id": "S1", "dur": 0.01}, {"id": "S2", "dur": 0.01}],
        {"S1": ["S2"], "S2": []},
    )
    scheduler = ForgeScheduler(plan, tracked_generate, num_workers=4)
    results, failed = asyncio.run(scheduler.run())
    assert "S1" in results
    assert "S2" in results
    # S1 must be started before S2 completes
    assert order.index("S1") < order.index("S2")


def test_scheduler_parallelism():
    start_times = {}

    async def timed_generate(scene: Scene, assets: dict, prev_frame=None) -> str:
        start_times[scene.id] = asyncio.get_event_loop().time()
        await asyncio.sleep(0.05)
        return f"output/{scene.id}.mp4"

    plan = make_plan(
        [{"id": "S1", "dur": 1.0}, {"id": "S2", "dur": 1.0}, {"id": "S3", "dur": 1.0}],
        {"S1": [], "S2": [], "S3": []},
    )
    scheduler = ForgeScheduler(plan, timed_generate, num_workers=4)
    asyncio.run(scheduler.run())
    # All three should start nearly simultaneously (within 0.04s)
    times = list(start_times.values())
    assert max(times) - min(times) < 0.04


def test_scheduler_critical_path_priority():
    """Critical path scene should be dispatched first."""
    dispatch_order = []

    async def ordered_generate(scene: Scene, assets: dict, prev_frame=None) -> str:
        dispatch_order.append(scene.id)
        await asyncio.sleep(0.01)
        return f"output/{scene.id}.mp4"

    # S1(dur=1) -> S3, S2(dur=10) -> S3
    # S2 has longer critical path: should be dispatched first
    plan = make_plan(
        [
            {"id": "S1", "dur": 1.0},
            {"id": "S2", "dur": 10.0},
            {"id": "S3", "dur": 1.0},
        ],
        {"S1": ["S3"], "S2": ["S3"], "S3": []},
    )
    scheduler = ForgeScheduler(plan, ordered_generate, num_workers=1)
    asyncio.run(scheduler.run())
    # With 1 worker and critical path priority, S2 should run before S1
    assert dispatch_order.index("S2") < dispatch_order.index("S1")
