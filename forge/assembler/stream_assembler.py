import os
import subprocess

from rich.console import Console

TARGET_FPS = 24
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720


class StreamAssembler:
    def __init__(
        self,
        output_path: str = "./output/final.mp4",
        timeline: list[str] | None = None,
        target_fps: int = TARGET_FPS,
        target_width: int = TARGET_WIDTH,
        target_height: int = TARGET_HEIGHT,
    ):
        self.output_path = output_path
        self.timeline = timeline or []
        self.target_fps = target_fps
        self.target_width = target_width
        self.target_height = target_height
        self._completed: dict[str, str] = {}
        self._assembled_up_to: int = 0
        self.console = Console()

    def on_scene_complete(self, scene_id: str, video_path: str) -> None:
        self._completed[scene_id] = video_path
        self._try_assemble()

    def _try_assemble(self) -> None:
        i = self._assembled_up_to
        while i < len(self.timeline) and self.timeline[i] in self._completed:
            i += 1
        if i - self._assembled_up_to < 2:
            return
        paths = [self._completed[sid] for sid in self.timeline[self._assembled_up_to:i]]
        self._ffmpeg_concat(paths, suffix=f"_seg{self._assembled_up_to}")
        self._assembled_up_to = i

    def _ffmpeg_concat(self, paths: list[str], suffix: str = "") -> str | None:
        valid = [p for p in paths if p and os.path.exists(p) and os.path.getsize(p) > 0]
        if not valid:
            return None

        out = self.output_path.replace(".mp4", f"{suffix}.mp4") if suffix else self.output_path
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

        # Build filter_complex: normalize each input, then concat
        inputs = []
        filter_parts = []
        w, h, fps = self.target_width, self.target_height, self.target_fps
        for i, p in enumerate(valid):
            inputs += ["-i", p]
            filter_parts.append(f"[{i}:v]scale={w}:{h},fps={fps},setsar=1[v{i}]")
        concat_in = "".join(f"[v{i}]" for i in range(len(valid)))
        filter_parts.append(f"{concat_in}concat=n={len(valid)}:v=1:a=0[out]")

        cmd = (
            ["ffmpeg", "-y"]
            + inputs
            + ["-filter_complex", ";".join(filter_parts)]
            + ["-map", "[out]", "-c:v", "libx264", "-an", out]
        )
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return out
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.console.print(f"[yellow]Assembly warning:[/yellow] {e}")
            return None

    def finalize(self) -> str:
        all_paths = [self._completed.get(sid, "") for sid in self.timeline]
        result = self._ffmpeg_concat(all_paths)
        if result:
            size_kb = os.path.getsize(result) / 1024
            self.console.print(
                f"[green]Final video:[/green] {result} ({size_kb:.1f} KB) "
                f"[{self.target_width}x{self.target_height} @ {self.target_fps}fps]"
            )
            return result
        self.console.print("[yellow]No valid clips to assemble.[/yellow]")
        return self.output_path
