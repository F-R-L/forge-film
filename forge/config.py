from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings


class ForgeSettings(BaseSettings):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    fal_api_key: str = ""
    kling_api_key: str = ""
    kling_api_secret: str = ""
    forge_workers: int = 4
    forge_video_backend: str = "mock"
    output_dir: str = "./output"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = ForgeSettings()


def load_forge_yaml(path: str | Path = "forge.yaml") -> dict[str, Any]:
    """Load forge.yaml if it exists. Returns empty dict if not found."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        import yaml
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}


class ForgeConfig:
    """Merged runtime config from forge.yaml + env vars.

    forge.yaml takes precedence for provider/routing choices;
    env vars are used for API keys (never put keys in forge.yaml).
    """

    def __init__(self, yaml_path: str | Path = "forge.yaml"):
        self._raw = load_forge_yaml(yaml_path)
        self._env = settings

    # ── LLM ────────────────────────────────────────────────────────────────
    @property
    def llm_provider(self) -> str:
        return self._raw.get("llm", {}).get("provider", "openai")

    @property
    def llm_model(self) -> str | None:
        return self._raw.get("llm", {}).get("model", None)

    @property
    def llm_api_key(self) -> str:
        raw_key = self._raw.get("llm", {}).get("api_key", "")
        if raw_key:
            return raw_key
        if self.llm_provider == "anthropic":
            return self._env.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if self.llm_provider == "deepseek":
            return self._env.deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        return self._env.openai_api_key or os.environ.get("OPENAI_API_KEY", "")

    # ── ImageGen ───────────────────────────────────────────────────────────
    @property
    def imagegen_provider(self) -> str:
        return self._raw.get("imagegen", {}).get("provider", "mock")

    @property
    def imagegen_model(self) -> str | None:
        return self._raw.get("imagegen", {}).get("model", None)

    @property
    def imagegen_api_key(self) -> str:
        raw_key = self._raw.get("imagegen", {}).get("api_key", "")
        if raw_key:
            return raw_key
        if self.imagegen_provider == "flux":
            return self._env.fal_api_key or os.environ.get("FAL_API_KEY", "")
        return self._env.openai_api_key or os.environ.get("OPENAI_API_KEY", "")

    # ── VLM ────────────────────────────────────────────────────────────────
    @property
    def vlm_provider(self) -> str:
        return self._raw.get("validator", {}).get("provider", "mock")

    @property
    def vlm_model(self) -> str | None:
        return self._raw.get("validator", {}).get("model", None)

    @property
    def vlm_api_key(self) -> str:
        raw_key = self._raw.get("validator", {}).get("api_key", "")
        if raw_key:
            return raw_key
        if self.vlm_provider == "anthropic":
            return self._env.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        return self._env.openai_api_key or os.environ.get("OPENAI_API_KEY", "")

    # ── Routing ────────────────────────────────────────────────────────────
    @property
    def routing(self) -> dict[str, str]:
        defaults = {
            "dialogue": "kling_light",
            "action": "kling_heavy",
            "landscape": "cogvideo",
            "product": "kling_heavy",
            "transition": "cogvideo",
            "default": "mock",
        }
        defaults.update(self._raw.get("routing", {}))
        return defaults

    # ── Scheduler ──────────────────────────────────────────────────────────
    @property
    def workers(self) -> int:
        return self._raw.get("scheduler", {}).get("workers", self._env.forge_workers)

    @property
    def max_retries(self) -> int:
        return self._raw.get("scheduler", {}).get("max_retries", 2)

    # ── Output ─────────────────────────────────────────────────────────────
    @property
    def output_dir(self) -> str:
        return self._raw.get("output", {}).get("dir", self._env.output_dir)

    # ── Video backend (legacy single-backend override) ─────────────────────
    @property
    def video_backend(self) -> str:
        return self._env.forge_video_backend

    def build_llm_provider(self):
        """Instantiate the configured LLM provider."""
        from forge.providers.llm import OpenAILLMProvider, AnthropicLLMProvider, DeepSeekLLMProvider
        p = self.llm_provider
        key = self.llm_api_key
        model = self.llm_model
        if p == "anthropic":
            return AnthropicLLMProvider(api_key=key, model=model or "claude-opus-4-6")
        if p == "deepseek":
            return DeepSeekLLMProvider(api_key=key, model=model or "deepseek-chat")
        return OpenAILLMProvider(api_key=key, model=model or "gpt-4o")

    def build_imagegen_provider(self):
        """Instantiate the configured ImageGen provider."""
        from forge.providers.imagegen import OpenAIImageGenProvider, FluxImageGenProvider, MockImageGenProvider
        p = self.imagegen_provider
        key = self.imagegen_api_key
        model = self.imagegen_model
        if p == "flux":
            return FluxImageGenProvider(api_key=key, model=model or "fal-ai/flux/schnell")
        if p == "openai":
            return OpenAIImageGenProvider(api_key=key, model=model or "dall-e-3")
        return MockImageGenProvider()

    def build_vlm_provider(self):
        """Instantiate the configured VLM provider."""
        from forge.providers.vlm import OpenAIVLMProvider, AnthropicVLMProvider, MockVLMProvider
        p = self.vlm_provider
        key = self.vlm_api_key
        model = self.vlm_model
        if p == "anthropic":
            return AnthropicVLMProvider(api_key=key, model=model or "claude-opus-4-6")
        if p == "openai" and key:
            return OpenAIVLMProvider(api_key=key, model=model or "gpt-4o")
        return MockVLMProvider()
