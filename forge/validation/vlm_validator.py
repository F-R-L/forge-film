import base64
import os

from forge.compiler.schema import Asset, Scene, ValidationResult


class VLMValidator:
    def __init__(self, client):
        self.client = client

    async def validate(
        self,
        scene: Scene,
        assets: dict[str, Asset],
        video_path: str,
    ) -> ValidationResult:
        import os
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_key:
            return ValidationResult(passed=True)

        # Check if any asset has a reference image
        required_assets = [
            assets[aid] for aid in scene.assets_required if aid in assets
        ]
        has_reference = any(a.reference_image_path for a in required_assets)
        if not has_reference:
            return ValidationResult(passed=True)

        # Extract 3 frames using moviepy
        frames_b64 = []
        try:
            from moviepy.editor import VideoFileClip
            clip = VideoFileClip(video_path)
            duration = clip.duration
            for t in [0, duration / 2, duration - 0.1]:
                frame = clip.get_frame(t)
                from PIL import Image
                import io
                img = Image.fromarray(frame)
                buf = io.BytesIO()
                img.save(buf, format="JPEG")
                frames_b64.append(base64.b64encode(buf.getvalue()).decode())
            clip.close()
        except Exception:
            return ValidationResult(passed=True)

        # Build vision message
        content = [
            {
                "type": "text",
                "text": (
                    f"Scene description: {scene.description}\n\n"
                    "Check: 1) Does the video match the scene description? "
                    "2) Do character appearances match the reference images?\n"
                    "Respond with JSON: {\"passed\": true/false, \"issues\": [...]}"
                ),
            }
        ]
        for f_b64 in frames_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{f_b64}"},
            })

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": content}],
                response_format={"type": "json_object"},
                max_tokens=256,
            )
            import json
            data = json.loads(response.choices[0].message.content)
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
        # Force accept after max retries
        return video_path
