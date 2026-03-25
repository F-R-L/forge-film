"""CogVideoX local video generation pipeline.

Requires the 'local' extras:
    pip install forge-film[local]

Falls back to MockPipeline gracefully if diffusers is not installed.
"""
from __future__ import annotations

import asyncio
import os

from forge.compiler.schema import Asset, Scene
from forge.generation.base import BasePipeline

_DEFAULT_MODEL = "THUDM/CogVideoX-2b"
_NUM_FRAMES = 49   # ~6 s at 8 fps
_FPS = 8


class CogVideoPipeline(BasePipeline):
    """Local CogVideoX text-to-video / image-to-video pipeline.

    Args:
        model_id: HuggingFace model ID.  Defaults to CogVideoX-2b (smallest).
        device:   'auto' lets accelerate pick the best device.
        dtype:    'float16' or 'bfloat16'.
    """

    def __init__(
        self,
        model_id: str = _DEFAULT_MODEL,
        device: str = "auto",
        dtype: str = "float16",
    ):
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self._t2v_pipe = None
        self._i2v_pipe = None
        self._available: bool | None = None  # None = not yet checked

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import diffusers  # noqa: F401
            import torch  # noqa: F401
            import imageio  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def _load_t2v(self):
        if self._t2v_pipe is not None:
            return self._t2v_pipe
        import torch
        from diffusers import CogVideoXPipeline

        dtype = torch.float16 if self.dtype == "float16" else torch.bfloat16
        pipe = CogVideoXPipeline.from_pretrained(self.model_id, torch_dtype=dtype)
        if self.device == "auto":
            pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to(self.device)
        pipe.enable_sequential_cpu_offload()
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()
        self._t2v_pipe = pipe
        return pipe

    def _load_i2v(self):
        if self._i2v_pipe is not None:
            return self._i2v_pipe
        import torch
        from diffusers import CogVideoXImageToVideoPipeline

        i2v_model = self.model_id.replace("-2b", "-2b-I2V").replace("-5b", "-5b-I2V")
        dtype = torch.float16 if self.dtype == "float16" else torch.bfloat16
        try:
            pipe = CogVideoXImageToVideoPipeline.from_pretrained(i2v_model, torch_dtype=dtype)
        except Exception:
            # Fall back to t2v if i2v variant not found
            return None
        if self.device == "auto":
            pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to(self.device)
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()
        self._i2v_pipe = pipe
        return pipe

    def _save_video(self, frames, out_path: str) -> None:
        import imageio
        import numpy as np

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        writer = imageio.get_writer(out_path, fps=_FPS, codec="libx264", quality=8)
        for frame in frames:
            if hasattr(frame, "numpy"):
                frame = frame.numpy()
            writer.append_data(np.array(frame))
        writer.close()

    async def generate(
        self,
        scene: Scene,
        assets: dict[str, Asset],
        output_dir: str,
        prev_frame: str | None = None,
    ) -> str:
        if not self._check_available():
            import warnings
            warnings.warn(
                "diffusers/torch/imageio not installed — falling back to MockPipeline. "
                "Install with: pip install forge-film[local]",
                stacklevel=2,
            )
            from forge.generation.mock_pipeline import MockPipeline
            return await MockPipeline().generate(scene, assets, output_dir, prev_frame=prev_frame)

        os.makedirs(os.path.join(output_dir, "scenes"), exist_ok=True)
        out_path = os.path.join(output_dir, "scenes", f"{scene.id}.mp4")

        loop = asyncio.get_event_loop()

        if prev_frame and os.path.exists(prev_frame):
            video_path = await loop.run_in_executor(
                None, self._run_i2v, scene.description, prev_frame, out_path
            )
        else:
            video_path = await loop.run_in_executor(
                None, self._run_t2v, scene.description, out_path
            )

        return video_path

    def _run_t2v(self, prompt: str, out_path: str) -> str:
        pipe = self._load_t2v()
        result = pipe(
            prompt=prompt,
            num_frames=_NUM_FRAMES,
            guidance_scale=6.0,
            num_inference_steps=50,
        )
        frames = result.frames[0]
        self._save_video(frames, out_path)
        return out_path

    def _run_i2v(self, prompt: str, image_path: str, out_path: str) -> str:
        from PIL import Image
        pipe = self._load_i2v()
        if pipe is None:
            return self._run_t2v(prompt, out_path)
        image = Image.open(image_path).convert("RGB")
        result = pipe(
            prompt=prompt,
            image=image,
            num_frames=_NUM_FRAMES,
            guidance_scale=6.0,
            num_inference_steps=50,
        )
        frames = result.frames[0]
        self._save_video(frames, out_path)
        return out_path
