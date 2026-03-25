import os

from rich.console import Console

# Target output spec — all clips are normalized to this before concatenation
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
        self._completed: dict[str, str] = {}  # scene_id -> video_path
        self._assembled_up_to: int = 0
        self._assembled_clips: list[str] = []
        self.console = Console()

    def on_scene_complete(self, scene_id: str, video_path: str) -> None:
        self._completed[scene_id] = video_path
        self._try_assemble()

    def _try_assemble(self) -> None:
        i = self._assembled_up_to
        while i < len(self.timeline) and self.timeline[i] in self._completed:
            i += 1
        newly_ready = i - self._assembled_up_to
        if newly_ready < 2:
            return

        segment_ids = self.timeline[self._assembled_up_to:i]
        paths = [self._completed[sid] for sid in segment_ids]
        self._concatenate(paths, suffix=f"_seg{self._assembled_up_to}")
        self._assembled_up_to = i

    def _normalize_clip(self, clip, path: str):
        """Normalize a clip's resolution and fps to target spec."""
        from moviepy.editor import VideoFileClip
        needs_resize = (clip.w, clip.h) != (self.target_width, self.target_height)
        needs_fps = abs(clip.fps - self.target_fps) > 0.5 if clip.fps else True

        if needs_resize:
            clip = clip.resize((self.target_width, self.target_height))
        if needs_fps:
            clip = clip.set_fps(self.target_fps)
        return clip

    def _concatenate(self, paths: list[str], suffix: str = "") -> str | None:
        valid = [p for p in paths if p and os.path.exists(p) and os.path.getsize(p) > 0]
        if not valid:
            return None
        try:
            from moviepy.editor import VideoFileClip, concatenate_videoclips

            clips = []
            for p in valid:
                c = VideoFileClip(p)
                c = self._normalize_clip(c, p)
                clips.append(c)

            combined = concatenate_videoclips(clips, method="compose")
            os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
            out = self.output_path.replace(".mp4", f"{suffix}.mp4") if suffix else self.output_path
            combined.write_videofile(
                out,
                codec="libx264",
                fps=self.target_fps,
                audio=False,
                logger=None,
            )
            for c in clips:
                c.close()
            combined.close()
            return out
        except Exception as e:
            self.console.print(f"[yellow]Assembly warning:[/yellow] {e}")
            return None

    def finalize(self) -> str:
        all_paths = [
            self._completed.get(sid, "") for sid in self.timeline
        ]
        result = self._concatenate(all_paths)
        if result:
            size_kb = os.path.getsize(result) / 1024
            self.console.print(
                f"[green]Final video:[/green] {result} ({size_kb:.1f} KB) "
                f"[{self.target_width}x{self.target_height} @ {self.target_fps}fps]"
            )
            return result
        else:
            self.console.print("[yellow]No valid clips to assemble.[/yellow]")
            return self.output_path
