"""Abstract VLM Provider layer.

Supports: OpenAI GPT-4o Vision, Anthropic Claude Vision, Mock.
All providers expose a common validate_frames interface.
"""
from __future__ import annotations

import base64
import json
from abc import ABC, abstractmethod


class VLMProvider(ABC):
    """Abstract base for Vision-Language Model providers used by VLMValidator."""

    @abstractmethod
    async def validate_frames(
        self,
        frames_b64: list[str],
        scene_description: str,
    ) -> dict:
        """Validate video frames against scene description.
        Returns dict with 'passed' (bool) and 'issues' (list[str]).
        """
        ...


class OpenAIVLMProvider(VLMProvider):
    """GPT-4o Vision validation."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self._model = model
        import openai
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def validate_frames(
        self,
        frames_b64: list[str],
        scene_description: str,
    ) -> dict:
        content = [
            {
                "type": "text",
                "text": (
                    f"Scene description: {scene_description}\n\n"
                    "Check: 1) Does the video match the scene description? "
                    "2) Do character appearances match the reference images?\n"
                    'Respond with JSON: {"passed": true/false, "issues": [...]}'
                ),
            }
        ]
        for f_b64 in frames_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{f_b64}"},
            })
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=256,
        )
        return json.loads(response.choices[0].message.content)


class AnthropicVLMProvider(VLMProvider):
    """Claude Vision validation."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-6"):
        self._model = model
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def validate_frames(
        self,
        frames_b64: list[str],
        scene_description: str,
    ) -> dict:
        content = []
        for f_b64 in frames_b64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": f_b64,
                },
            })
        content.append({
            "type": "text",
            "text": (
                f"Scene description: {scene_description}\n\n"
                "Check: 1) Does the video match the scene description? "
                "2) Do character appearances match the reference images?\n"
                'Respond with JSON only: {"passed": true/false, "issues": [...]}'
            ),
        })
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=256,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        return json.loads(raw)


class MockVLMProvider(VLMProvider):
    """Mock VLM — always passes (no API calls)."""

    async def validate_frames(
        self,
        frames_b64: list[str],
        scene_description: str,
    ) -> dict:
        return {"passed": True, "issues": []}
