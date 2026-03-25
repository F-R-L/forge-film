import asyncio
import heapq
import os
import time
from collections.abc import Awaitable, Callable

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from forge.compiler.schema import Asset, ProductionPlan, Scene
from forge.scheduler.cpm import compute_critical_path, get_priority_queue_items
from forge.scheduler.dag import compute_in_degree, get_reverse_dag


def _extract_last_frame(video_path: str) -> str | None:
    """Extract the last frame of a video, save as JPEG next to it. Returns path or None."""
    if not video_path or not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
        return None
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(video_path)
        frame = clip.get_frame(max(0.0, clip.duration - 0.05))
        clip.close()
        from PIL import Image
        img = Image.fromarray(frame)
        out = video_path.replace(".mp4", "_last_frame.jpg")
        img.save(out, format="JPEG", quality=92)
        return out
    except Exception:
        return None


class ForgeScheduler:
    def __init__(
        self,
        plan: ProductionPlan,
        generate_fn: Callable[[Scene, dict[str, Asset]], Awaitable[str]],  # signature: (scene, assets, prev_frame=None) -> str
        num_workers: int = 4,
        console: Console | None = None,
        max_retries: int = 2,
        on_scene_complete: Callable[[str, str], None] | None = None,
    ):
        self.plan = plan
        self.generate_fn = generate_fn
        self.num_workers = num_workers
        self.console = console or Console()
        self.max_retries = max_retries
        self.on_scene_complete = on_scene_complete
        self._scene_map: dict[str, Scene] = {s.id: s for s in plan.scenes}
        self._timings: dict[str, float] = {}
        self._last_frames: dict[str, str | None] = {}  # scene_id -> last frame path
        self._failed_scenes: list[str] = []
        self._stats: dict = {}

    async def run(self) -> tuple[dict[str, str], list[str]]:  # ({scene_id -> video_path}, failed_scene_ids)
        _wall_start = time.monotonic()
        dag = self.plan.dag
        durations = {
            s.id: s.estimated_duration_sec for s in self.plan.scenes
        }
        cp = compute_critical_path(dag, durations)
        in_degree = compute_in_degree(dict(dag))  # mutable copy

        # Priority queue: (neg_priority, scene_id)
        heap = [
            item
            for item in get_priority_queue_items(cp)
            if in_degree.get(item[1], 0) == 0
        ]
        heapq.heapify(heap)

        results: dict[str, str] = {}
        semaphore = asyncio.Semaphore(self.num_workers)
        pending: set[asyncio.Task] = set()
        lock = asyncio.Lock()

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            overall = progress.add_task(
                "Scheduling scenes…", total=len(self.plan.scenes)
            )

            async def run_scene(scene: Scene) -> None:
                async with semaphore:
                    scene.status = "generating"
                    t0 = time.monotonic()

                    # Find prev_frame: last frame of the highest-priority predecessor
                    reverse = get_reverse_dag(dag)
                    predecessors = reverse.get(scene.id, [])
                    prev_frame: str | None = None
                    if predecessors:
                        # Pick the predecessor with the longest CP (most critical)
                        best_pred = max(predecessors, key=lambda p: cp.get(p, 0))
                        prev_frame = self._last_frames.get(best_pred)

                    video_path: str | None = None
                    last_exc: Exception | None = None
                    for attempt in range(self.max_retries + 1):
                        try:
                            video_path = await self.generate_fn(scene, {}, prev_frame=prev_frame)
                            last_exc = None
                            break
                        except Exception as exc:
                            last_exc = exc
                            if attempt < self.max_retries:
                                await asyncio.sleep(2 ** attempt)  # 1s, 2s

                    elapsed = time.monotonic() - t0
                    self._timings[scene.id] = elapsed

                    if last_exc is not None:
                        scene.status = "failed"
                        async with lock:
                            self._failed_scenes.append(scene.id)
                            progress.advance(overall)
                            for downstream_id in dag.get(scene.id, []):
                                in_degree[downstream_id] -= 1
                                if in_degree[downstream_id] == 0:
                                    heapq.heappush(heap, (-cp[downstream_id], downstream_id))
                        return

                    scene.output_video_path = video_path
                    scene.status = "done"

                    # Extract last frame for downstream scenes
                    last_frame = _extract_last_frame(video_path)
                    scene.last_frame_path = last_frame

                    async with lock:
                        results[scene.id] = video_path
                        self._last_frames[scene.id] = last_frame
                        progress.advance(overall)
                        # Unlock downstream scenes
                        for downstream_id in dag.get(scene.id, []):
                            in_degree[downstream_id] -= 1
                            if in_degree[downstream_id] == 0:
                                heapq.heappush(
                                    heap,
                                    (-cp[downstream_id], downstream_id),
                                )

                    if self.on_scene_complete is not None:
                        self.on_scene_complete(scene.id, video_path)

            completed = 0
            total = len(self.plan.scenes)

            while completed < total:
                # Drain heap: launch all ready scenes (up to worker slots)
                while heap:
                    _, scene_id = heapq.heappop(heap)
                    scene = self._scene_map[scene_id]
                    if scene.status == "pending":
                        task = asyncio.create_task(run_scene(scene))
                        pending.add(task)

                if not pending:
                    break

                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                completed += len(done)

        wall_time = time.monotonic() - _wall_start
        serial_equivalent = sum(self._timings.values())
        self._stats = {
            "total_wall_time": wall_time,
            "parallelism_efficiency": serial_equivalent / wall_time if wall_time > 0 else 0.0,
            "scenes_failed": len(self._failed_scenes),
            "scenes_completed": len(results),
        }

        self.console.print(
            f"[green]Scheduling complete.[/green] "
            f"Scenes: {total}, Workers: {self.num_workers}"
        )
        return results, self._failed_scenes

    @property
    def timings(self) -> dict[str, float]:
        return self._timings

    @property
    def stats(self) -> dict:
        return self._stats
