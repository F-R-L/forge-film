import asyncio
import os
import random
import time

from forge.compiler.schema import Asset, Scene
from forge.generation.base import BasePipeline


class MockPipeline(BasePipeline):
    async def generate(
        self,
        scene: Scene,
        assets: dict[str, Asset],
        output_dir: str,
        prev_frame: str | None = None,
    ) -> str:
        delay = scene.estimated_duration_sec * 0.1
        t0 = time.monotonic()
        await asyncio.sleep(delay)
        elapsed = time.monotonic() - t0

        os.makedirs(os.path.join(output_dir, "scenes"), exist_ok=True)
        out_path = os.path.join(output_dir, "scenes", f"{scene.id}.mp4")

        # Generate a solid-color 3-second mp4 using Pillow + moviepy
        try:
            from PIL import Image
            from moviepy.editor import ImageClip

            color = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )
            img = Image.new("RGB", (640, 360), color=color)
            tmp_img = out_path.replace(".mp4", "_frame.png")
            img.save(tmp_img)
            clip = ImageClip(tmp_img, duration=3)
            clip.write_videofile(
                out_path, fps=24, codec="libx264", audio=False, logger=None
            )
            clip.close()
            os.remove(tmp_img)
        except Exception:
            # Fallback: write empty file so downstream works
            with open(out_path, "wb") as f:
                f.write(b"")

        print(f"[MockPipeline] Scene {scene.id} generated in {elapsed:.1f}s")
        return out_path
