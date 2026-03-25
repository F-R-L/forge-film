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
from forge.continuity.color_calibration import ColorCalibrator, extract_first_frame


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
        generate_fn: Callable[[Scene, dict[str, Asset]], Awaitable[str]],
        num_workers: int = 4,
        console: Console | None = None,
        max_retries: int = 2,
        on_scene_complete: Callable[[str, str], None] | None = None,
        color_calibrator: ColorCalibrator | None = None,
        # backend_used_fn: optional callable that returns the backend name for a scene
        backend_used_fn: Callable[[str], str] | None = None,
    ):
        self.plan = plan
        self.generate_fn = generate_fn
        self.num_workers = num_workers
        self.console = console or Console()
        self.max_retries = max_retries
        self.on_scene_complete = on_scene_complete
        self.color_calibrator = color_calibrator or ColorCalibrator()
        self.backend_used_fn = backend_used_fn  # scene_id -> backend name
        self._scene_map: dict[str, Scene] = {s.id: s for s in plan.scenes}
        self._timings: dict[str, float] = {}
        self._last_frames: dict[str, str | None] = {}  # scene_id -> last frame path
        self._backend_used: dict[str, str] = {}  # scene_id -> backend name
        self._failed_scenes: list[str] = []
        self._stats: dict = {}

    async def _generate_with_retry(self, scene: Scene, assets: dict[str, Asset]) -> str:
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await self.generate_fn(scene, assets)
                return result
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    self.console.print(
                        f"[yellow]Retry {attempt + 1}/{self.max_retries}[/yellow] "
                        f"scene {scene.id}: {exc}"
                    )
        raise last_exc

    def _get_prev_frame_with_calibration(
        self,
        scene: Scene,
        reverse_dag: dict[str, list[str]],
        output_dir: str,
    ) -> str | None:
        """Get predecessor last frame, applying color calibration if backends differ."""
        predecessors = reverse_dag.get(scene.id, [])
        if not predecessors:
            return None

        # Use the most recently completed predecessor (highest CPM priority one)
        prev_id = predecessors[0]
        prev_frame = self._last_frames.get(prev_id)
        if not prev_frame or not os.path.exists(prev_frame):
            return None

        # Check if backends differ — if so, apply color calibration
        prev_backend = self._backend_used.get(prev_id, "")
        curr_backend = self.backend_used_fn(scene.id) if self.backend_used_fn else ""
        if prev_backend and curr_backend and prev_backend != curr_backend:
            # Extract first frame of current scene's predecessor output for calibration target
            calibrated_path = os.path.join(
                output_dir,
                f"calibrated_{scene.id}_from_{prev_id}.jpg",
            )
            calibrated = self.color_calibrator.calibrate(
                reference_path=prev_frame,
                target_path=prev_frame,  # calibrate the reference itself as i2v seed
                output_path=calibrated_path,
            )
            self.console.print(
                f"  [cyan]Color calibration:[/cyan] {prev_id}({prev_backend}) "
                f"-> {scene.id}({curr_backend})"
            )
            return calibrated

        return prev_frame

    async def run(
        self,
        assets: dict[str, Asset],
        output_dir: str = "./output",
    ) -> tuple[dict[str, str], list[str]]:
        """Run the CPM-scheduled parallel generation.

        Returns
        -------
        results: dict[scene_id, video_path]
        failed:  list[scene_id]
        """
        os.makedirs(output_dir, exist_ok=True)
        dag = self.plan.dag
        reverse_dag = get_reverse_dag(dag)
        durations = {
            s.id: s.estimated_duration_sec for s in self.plan.scenes
        }
        critical_path = compute_critical_path(dag, durations)
        heap = get_priority_queue_items(critical_path)
        heapq.heapify(heap)

        in_degree = compute_in_degree(dag)
        results: dict[str, str] = {}
        total = len(self.plan.scenes)
        _wall_start = time.monotonic()
        completed = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            prog_task = progress.add_task("Generating scenes…", total=total)

            sem = asyncio.Semaphore(self.num_workers)

            async def run_scene(scene: Scene) -> None:
                scene.status = "generating"
                async with sem:
                    t0 = time.monotonic()
                    prev_frame = self._get_prev_frame_with_calibration(
                        scene, reverse_dag, output_dir
                    )
                    try:
                        video_path = await self._generate_with_retry(scene, assets)
                        scene.output_video_path = video_path
                        scene.status = "done"
                        # Extract last frame for downstream scenes
                        last_frame = _extract_last_frame(video_path)
                        scene.last_frame_path = last_frame
                        self._last_frames[scene.id] = last_frame
                        # Track backend used
                        if self.backend_used_fn:
                            self._backend_used[scene.id] = self.backend_used_fn(scene.id)
                        results[scene.id] = video_path
                        if self.on_scene_complete:
                            self.on_scene_complete(scene.id, video_path)
                    except Exception as exc:
                        scene.status = "failed"
                        self._failed_scenes.append(scene.id)
                        self.console.print(
                            f"[red]Scene {scene.id} failed:[/red] {exc}"
                        )
                    finally:
                        self._timings[scene.id] = time.monotonic() - t0
                        progress.advance(prog_task)
                        # Unlock downstream scenes
                        for downstream_id in dag.get(scene.id, []):
                            in_degree[downstream_id] -= 1
                            if in_degree[downstream_id] == 0:
                                ds = self._scene_map[downstream_id]
                                if ds.status == "pending":
                                    heapq.heappush(
                                        heap,
                                        (-critical_path.get(downstream_id, 0), downstream_id),
                                    )

            pending: set[asyncio.Task] = set()

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
