"""Abstract ImageGen Provider layer.

Supports: OpenAI DALL·E, Flux (via fal.ai), local Stable Diffusion, Mock.
All providers expose a common generate(prompt) -> local_path interface.
"""
from __future__ import annotations

import base64
import os
import uuid
from abc import ABC, abstractmethod


class ImageGenProvider(ABC):
    """Abstract base for image generation providers used by AssetFoundry."""

    @abstractmethod
    async def generate(self, prompt: str, output_dir: str = "./output/assets") -> str:
        """Generate an image from prompt, save locally, return file path."""
        ...


class OpenAIImageGenProvider(ImageGenProvider):
    """OpenAI DALL·E 3 image generation."""

    def __init__(self, api_key: str, model: str = "dall-e-3", size: str = "1024x1024"):
        self._model = model
        self._size = size
        import openai
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def generate(self, prompt: str, output_dir: str = "./output/assets") -> str:
        os.makedirs(output_dir, exist_ok=True)
        response = await self._client.images.generate(
            model=self._model,
            prompt=prompt,
            size=self._size,
            response_format="b64_json",
            n=1,
        )
        img_data = base64.b64decode(response.data[0].b64_json)
        path = os.path.join(output_dir, f"asset_{uuid.uuid4().hex[:8]}.png")
        with open(path, "wb") as f:
            f.write(img_data)
        return path


class FluxImageGenProvider(ImageGenProvider):
    """Flux image generation via fal.ai API."""

    def __init__(self, api_key: str, model: str = "fal-ai/flux/schnell"):
        self._model = model
        self._api_key = api_key

    async def generate(self, prompt: str, output_dir: str = "./output/assets") -> str:
        import httpx
        os.makedirs(output_dir, exist_ok=True)
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"https://fal.run/{self._model}",
                headers={"Authorization": f"Key {self._api_key}"},
                json={"prompt": prompt, "image_size": "square_hd"},
            )
            response.raise_for_status()
            data = response.json()
            image_url = data["images"][0]["url"]
            img_response = await client.get(image_url)
            img_response.raise_for_status()
        path = os.path.join(output_dir, f"asset_{uuid.uuid4().hex[:8]}.png")
        with open(path, "wb") as f:
            f.write(img_response.content)
        return path


class MockImageGenProvider(ImageGenProvider):
    """Mock image gen — creates a tiny placeholder PNG (no API calls)."""

    async def generate(self, prompt: str, output_dir: str = "./output/assets") -> str:
        from PIL import Image, ImageDraw
        os.makedirs(output_dir, exist_ok=True)
        img = Image.new("RGB", (256, 256), color=(60, 60, 80))
        draw = ImageDraw.Draw(img)
        draw.text((10, 120), prompt[:40], fill=(200, 200, 200))
        path = os.path.join(output_dir, f"asset_{uuid.uuid4().hex[:8]}.png")
        img.save(path)
        return path
