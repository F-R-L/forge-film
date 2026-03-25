import os

from rich.console import Console


class StreamAssembler:
    def __init__(
        self,
        output_path: str = "./output/final.mp4",
        timeline: list[str] | None = None,
    ):
        self.output_path = output_path
        self.timeline = timeline or []
        self._completed: dict[str, str] = {}  # scene_id -> video_path
        self._assembled_up_to: int = 0  # index into timeline
        self._assembled_clips: list[str] = []  # paths of already-assembled segments
        self.console = Console()

    def on_scene_complete(self, scene_id: str, video_path: str) -> None:
        self._completed[scene_id] = video_path
        self._try_assemble()

    def _try_assemble(self) -> None:
        # Find how many consecutive scenes from assembled_up_to are ready
        i = self._assembled_up_to
        while i < len(self.timeline) and self.timeline[i] in self._completed:
            i += 1
        newly_ready = i - self._assembled_up_to
        if newly_ready < 2:
            return  # not enough to bother assembling yet

        segment_ids = self.timeline[self._assembled_up_to:i]
        paths = [self._completed[sid] for sid in segment_ids]
        self._concatenate(paths, suffix=f"_seg{self._assembled_up_to}")
        self._assembled_up_to = i

    def _concatenate(self, paths: list[str], suffix: str = "") -> str | None:
        valid = [p for p in paths if p and os.path.exists(p) and os.path.getsize(p) > 0]
        if not valid:
            return None
        try:
            from moviepy.editor import VideoFileClip, concatenate_videoclips

            clips = [VideoFileClip(p) for p in valid]
            combined = concatenate_videoclips(clips)
            os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
            out = self.output_path.replace(".mp4", f"{suffix}.mp4") if suffix else self.output_path
            combined.write_videofile(out, codec="libx264", audio=False, logger=None)
            for c in clips:
                c.close()
            combined.close()
            return out
        except Exception as e:
            self.console.print(f"[yellow]Assembly warning:[/yellow] {e}")
            return None

    def finalize(self) -> str:
        # Concatenate all scenes into the final output file
        all_paths = [
            self._completed.get(sid, "") for sid in self.timeline
        ]

        result = self._concatenate(all_paths)
        if result:
            size_kb = os.path.getsize(result) / 1024
            self.console.print(
                f"[green]Final video:[/green] {result} ({size_kb:.1f} KB)"
            )
            return result
        else:
            self.console.print("[yellow]No valid clips to assemble.[/yellow]")
            return self.output_path
