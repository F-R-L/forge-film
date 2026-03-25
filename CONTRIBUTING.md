# Contributing to Forge

Forge is an open-source multi-model AI film orchestration engine. Contributions are welcome across all layers of the stack.

## Most Wanted Contributions

- **New video backends** — each new model (Seedance, Wan, Veo, Sora) is an independent PR
- **Color calibration improvements** — better cross-model continuity algorithms
- **New LLM providers** — LocalLLM, Ollama, Gemini, etc.
- **Story templates** — reusable story structures for common film genres
- **Multilingual docs** — README translations
- **Benchmark results** — real timing data with actual API backends

---

## Development Setup

```bash
git clone https://github.com/F-R-L/forge-film.git
cd forge-film
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
cp .env.example .env
# Fill in API keys in .env as needed
```

All tests run without API keys — mock providers are used automatically.

```bash
pytest tests/ -v  # should be 20/20 green
```

---

## Project Layout

```
forge/
  cli.py                  # Typer CLI entry point
  config.py               # ForgeConfig — loads forge.yaml + env vars
  compiler/               # Story → ProductionPlan (LLM-driven)
  providers/              # Pluggable provider abstractions
    llm.py                #   LLMProvider: OpenAI / Anthropic / DeepSeek
    imagegen.py           #   ImageGenProvider: DALL·E / Flux / Mock
    vlm.py                #   VLMProvider: GPT-4o Vision / Claude Vision / Mock
  scheduler/              # DAG topology + CPM priority scheduling
  generation/             # Video backend pipelines
    base.py               #   BasePipeline ABC
    router.py             #   Scene-type semantic router
    mock_pipeline.py      #   Mock (no API, for testing)
    light_pipeline.py     #   Kling v1 5s
    heavy_pipeline.py     #   Kling v1.5 Pro 10s
    cogvideo_pipeline.py  #   CogVideoX local
  continuity/             # Cross-model frame continuity
    color_calibration.py  #   Histogram-matching color calibration
  assets/                 # Reference image generation + disk cache
  validation/             # VLM frame consistency validation
  assembler/              # Streaming moviepy concatenation (normalized fps/res)
forge.yaml                # User-facing config (providers, routing, workers)
tests/                    # pytest test suite
benchmarks/               # Parallel vs serial benchmarks
examples/                 # Sample story files
```

---

## Adding a New Video Backend

Each new video model backend is a self-contained file. Steps:

1. Create `forge/generation/your_backend.py` subclassing `BasePipeline`:

```python
from forge.generation.base import BasePipeline
from forge.compiler.schema import Asset, Scene

class YourBackendPipeline(BasePipeline):
    async def generate(
        self, scene: Scene, assets: dict[str, Asset],
        output_dir: str, prev_frame: str | None = None,
    ) -> str:
        # Call your API / local model here
        # Return path to the generated .mp4 file
        ...
```

2. Add a duration estimate in `forge/scheduler/cpm.py` → `BACKEND_DURATION_ESTIMATES`.

3. Register the backend name in `forge/cli.py` → `_build_backends()`.

4. Add it to `forge.yaml` routing examples and the `.env.example` if it needs an API key.

5. Add a test in `tests/` using the mock pattern from `tests/test_scheduler.py`.

---

## Adding a New LLM Provider

1. Subclass `LLMProvider` in `forge/providers/llm.py`.
2. Implement `async def chat_completion(system, user, *, model, response_json) -> str`.
3. Add `build_llm_provider()` support in `forge/config.py`.
4. Document the provider name in `forge.yaml` comments.

## Adding a New ImageGen Provider

1. Subclass `ImageGenProvider` in `forge/providers/imagegen.py`.
2. Implement `async def generate(prompt, output_dir) -> str` (returns local file path).
3. Add `build_imagegen_provider()` support in `forge/config.py`.

## Improving Color Calibration

The calibration logic lives entirely in `forge/continuity/color_calibration.py`. The current approach is channel-wise histogram matching. Better approaches welcome:

- Neural style transfer for color grading
- Perceptual color matching (CIEDE2000)
- Temporal smoothing across multiple frames
- Scene-adaptive calibration strength

---

## Submitting Changes

1. Fork and branch: `git checkout -b feat/your-feature`
2. Keep each commit focused. One backend = one PR.
3. Ensure `pytest tests/ -v` passes with no failures.
4. Open a PR against `main`. Describe what changed and why, and which video model / provider it targets.

## Code Style

- Python 3.11+, type-annotated.
- Follow the style of surrounding code.
- Avoid adding core dependencies unless strictly necessary (put optional deps in `pyproject.toml` extras).

## Reporting Issues

Open an issue at https://github.com/F-R-L/forge-film/issues with:
- Python version and OS
- `forge.yaml` config (redact API keys)
- Steps to reproduce
- Full traceback
