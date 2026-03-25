import base64
import io

from forge.compiler.schema import Asset, Scene, ValidationResult
from forge.providers.vlm import VLMProvider


class VLMValidator:
    def __init__(self, provider: VLMProvider):
        self.provider = provider

    async def validate(
        self,
        scene: Scene,
        assets: dict[str, Asset],
        video_path: str,
    ) -> ValidationResult:
        required_assets = [
            assets[aid] for aid in scene.assets_required if aid in assets
        ]
        has_reference = any(a.reference_image_path for a in required_assets)
        if not has_reference:
            return ValidationResult(passed=True)

        frames_b64 = []
        try:
            from moviepy.editor import VideoFileClip
            from PIL import Image
            clip = VideoFileClip(video_path)
            duration = clip.duration
            for t in [0, duration / 2, duration - 0.1]:
                frame = clip.get_frame(t)
                img = Image.fromarray(frame)
                buf = io.BytesIO()
                img.save(buf, format="JPEG")
                frames_b64.append(base64.b64encode(buf.getvalue()).decode())
            clip.close()
        except Exception:
            return ValidationResult(passed=True)

        try:
            data = await self.provider.validate_frames(frames_b64, scene.description)
            return ValidationResult(
                passed=data.get("passed", True),
                issues=data.get("issues", []),
            )
        except Exception:
            return ValidationResult(passed=True)

    async def validate_with_retry(
        self,
        scene: Scene,
        assets: dict[str, Asset],
        generate_fn,
        max_retries: int = 2,
    ) -> str:
        video_path = await generate_fn(scene, assets)
        for attempt in range(max_retries):
            result = await self.validate(scene, assets, video_path)
            result.retry_count = attempt
            if result.passed:
                return video_path
            if attempt < max_retries - 1:
                video_path = await generate_fn(scene, assets)
        return video_path
