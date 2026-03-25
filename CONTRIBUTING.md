# Contributing to Forge

Thank you for your interest in contributing. This document covers how to set up your development environment, run tests, and submit changes.

## Development Setup

```bash
git clone https://github.com/F-R-L/forge-film.git
cd forge-film
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
cp .env.example .env
# Fill in OPENAI_API_KEY / KLING_API_KEY in .env if needed
```

## Running Tests

```bash
pytest tests/ -v
```

All tests run without API keys — mock pipelines are used automatically when keys are absent.

## Project Layout

```
forge/
  cli.py                  # Typer entry point
  compiler/               # GPT-4o story → ProductionPlan
  scheduler/              # DAG + CPM scheduling
  generation/             # Pipeline backends (mock / light / heavy)
  assets/                 # Asset generation + disk cache
  validation/             # VLM frame consistency check
  assembler/              # moviepy stream assembly
tests/                    # pytest test suite
benchmarks/               # Parallel vs serial benchmarks
examples/                 # Sample story files
```

## Submitting Changes

1. Fork the repository and create a branch: `git checkout -b feat/your-feature`
2. Make your changes. Keep each commit focused on one thing.
3. Ensure `pytest tests/ -v` passes with no failures.
4. Open a pull request against `main`. Describe what changed and why.

## Code Style

- Python 3.11+, type-annotated where practical.
- No external linter config is enforced yet — follow the style of the surrounding code.
- Avoid adding dependencies unless strictly necessary.

## Adding a New Video Backend

1. Create `forge/generation/your_backend.py` subclassing `BasePipeline`.
2. Implement `async def generate(self, scene, assets, output_dir, prev_frame=None) -> str`.
3. Register it in `forge/generation/router.py` and wire the CLI `--backend` option in `forge/cli.py`.
4. Add a test in `tests/` using the mock pattern.

## Reporting Issues

Open an issue at https://github.com/F-R-L/forge-film/issues with:
- Python version and OS
- Steps to reproduce
- Full traceback if applicable
