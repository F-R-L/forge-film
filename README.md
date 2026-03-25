<div align="center">

# 🎬 Forge

**One story, multiple AI models, zero manual stitching.**

Forge orchestrates Kling, CogVideoX, Seedance, and any video backend into one coherent film — fully open source.

[![CI](https://github.com/F-R-L/forge-film/actions/workflows/ci.yml/badge.svg)](https://github.com/F-R-L/forge-film/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-green)](https://github.com/F-R-L/forge-film)

[中文文档](README.zh.md) | [Quick Start](#-quickstart)

</div>

---

## ⚡ Why Forge?

In 2026, there are 6+ mainstream video models — Kling 3.0, Seedance 2.0, Sora 2, Veo 3, CogVideoX, Wan 2.6 — each with different strengths. The industry consensus is to mix them by scene type: Kling for dialogue, CogVideoX for landscapes, Seedance for action.

But in practice, creators end up as the "human scheduler":

- Manually decide which model fits each scene
- Log in to different platforms / call different APIs
- Download intermediate frames and pass them to the next scene for i2v
- Manually color-correct (Kling and CogVideoX have naturally different color profiles)
- Manually stitch clips in an editor

**An 8-scene short film can eat half a day just switching between platforms.**

Forge automates the entire pipeline:

1. **Story → DAG** — GPT-4o (or Claude / DeepSeek) compiles your story into a scene dependency graph, identifying causal dependencies and parallelizable scenes
2. **Scene-type routing** — dialogue goes to Kling, landscapes to CogVideoX (free, local), action to Seedance — fully configurable routing rules
3. **CPM priority scheduling** — Critical Path Method finds the longest dependency chain, prioritizes scenes that block the most downstream work, N workers generate in parallel
4. **Cross-model continuity** — when scene B depends on scene A and they use different models, Forge extracts A's last frame, applies color calibration (histogram matching), and passes it to B as the i2v seed image
5. **Streaming assembly** — clips are concatenated as each scene completes, normalized to a common resolution and frame rate, output to `final.mp4`

---

## 🆚 How Forge Compares

| | Forge | OpusClip Agent | Seedance Multi-shot | FilmAgent |
|---|---|---|---|---|
| Open source | ✅ MIT | ❌ Closed SaaS | ❌ | ✅ Research prototype |
| Local deployment | ✅ | ❌ | ❌ | Partial |
| Multi-model mixing | ✅ Cross-model orchestration | ✅ But not configurable | ❌ Single model | ❌ 3D virtual space |
| Cross-model color calibration | ✅ | Unknown | N/A | N/A |
| Pluggable backends | ✅ Full 4-layer stack | ❌ | ❌ | ❌ |
| Data privacy | ✅ Data never leaves your machine | ❌ Third-party | ❌ | Partial |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         forge.yaml                              │
│              (LLM · ImageGen · Routing · Workers)               │
└───────────────────────┬─────────────────────────────────────────┘
                        │
          ┌─────────────▼──────────────┐
          │     VisionCompiler          │  story text → ProductionPlan
          │  (LLM: GPT-4o/Claude/DS)   │  scenes + assets + DAG
          └─────────────┬──────────────┘
                        │
          ┌─────────────▼──────────────┐
          │      AssetFoundry          │  generate reference images
          │  (ImageGen: DALL·E/Flux)   │  per-character, per-location
          └─────────────┬──────────────┘
                        │
          ┌─────────────▼──────────────┐
          │      ForgeScheduler        │  CPM critical path
          │  workers=N, retries=M      │  parallel scene dispatch
          └──┬──────────────────┬──────┘
             │                  │
   ┌─────────▼──────┐  ┌───────▼────────┐
   │ PipelineRouter │  │ ColorCalibrator │  histogram matching
   │ scene_type →   │  │ last-frame i2v  │  cross-model continuity
   │ kling/cogvideo │  └────────────────┘
   │ /seedance/...  │
   └─────────┬──────┘
             │
   ┌─────────▼──────────────────────────┐
   │          Video Backends             │
   │  KlingLight · KlingHeavy           │
   │  CogVideoXPipeline (local GPU)     │
   │  MockPipeline (no API key needed)  │
   └─────────┬──────────────────────────┘
             │
   ┌─────────▼──────────────────────────┐
   │  VLM Validator (GPT-4o/Claude)     │  optional frame check
   └─────────┬──────────────────────────┘
             │
   ┌─────────▼──────────────────────────┐
   │       StreamAssembler              │  ffmpeg concat → final.mp4
   └────────────────────────────────────┘
```

---

## 🚀 Quickstart

> **No API keys?** Run with `--backend mock` for a full end-to-end test with zero external dependencies — no Kling, no OpenAI, nothing.

### Requirements

- Python 3.11+
- ffmpeg (for video assembly — `winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg`)
- GPU optional — CogVideoX local backend requires CUDA 12+; all other backends are API-based

### Install

```bash
git clone https://github.com/F-R-L/forge-film
cd forge-film
pip install -e .
cp .env.example .env
```

### Configure

Edit `forge.yaml` (defaults work out of the box):

```yaml
llm:
  provider: openai      # openai | anthropic | deepseek
  model: gpt-4o

imagegen:
  provider: mock        # mock = no API key needed

validator:
  provider: mock

routing:
  dialogue: kling_light     # dialogue scenes → Kling v1
  action: kling_heavy       # action scenes → Kling v1.5 Pro
  landscape: cogvideo       # landscapes → CogVideoX (free, local)
  product: kling_heavy
  transition: cogvideo
  default: mock
```

Add API keys to `.env`:

```bash
OPENAI_API_KEY=sk-...
KLING_API_KEY=...
KLING_API_SECRET=...
```

### Run

```bash
# End-to-end test with mock backend (no API keys needed)
forge run examples/detective.txt --backend mock --workers 4

# Multi-model orchestration demo
forge run examples/multi_backend_demo.txt --workers 4

# Compile only — inspect DAG and routing without generating video
forge plan examples/detective.txt --scenes 6

# Launch Web UI
forge webui
```

### Use as a Library

```python
from forge.config import ForgeConfig
from forge.compiler.vision_compiler import VisionCompiler
from forge.scheduler.scheduler import ForgeScheduler

cfg = ForgeConfig("forge.yaml")
compiler = VisionCompiler(cfg.build_llm_provider())
plan = await compiler.compile(story_text, num_scenes=6)

# Build your backends dict and router
# Run the scheduler
scheduler = ForgeScheduler(plan, generate_fn, num_workers=cfg.workers)
results, failed = await scheduler.run(asset_map, output_dir="./output")
```

---

## ⚙️ Configuration Reference

| Key | Options | Default |
|---|---|---|
| `llm.provider` | `openai` \| `anthropic` \| `deepseek` | `openai` |
| `imagegen.provider` | `openai` \| `flux` \| `mock` | `mock` |
| `validator.provider` | `openai` \| `anthropic` \| `mock` | `mock` |
| `routing.dialogue` | any backend name | `kling_light` |
| `routing.landscape` | any backend name | `cogvideo` |
| `scheduler.workers` | int | `4` |
| `output.dir` | path | `./output` |

All API keys go in `.env` or environment variables — never in `forge.yaml`.

---

## 📁 Project Structure

```
forge/
  compiler/            # Story → DAG (LLM-driven)
  providers/           # LLM / ImageGen / VLM abstractions
  scheduler/           # DAG topology + CPM scheduling
  generation/          # Video backend pipelines
  continuity/          # Cross-model color calibration
  assets/              # Reference image generation + cache
  validation/          # VLM frame consistency check
  assembler/           # Streaming video concatenation
  cli.py               # forge CLI
  webui/               # Gradio Web UI
forge.yaml             # Config
examples/              # Sample stories
tests/                 # pytest suite (20 tests, no API keys needed)
benchmarks/            # Parallel vs serial speedup charts
```

---

## 🗺️ Roadmap

- [x] Multi-model semantic routing by scene type
- [x] Cross-model color calibration (histogram matching)
- [x] Pluggable LLM providers (OpenAI / Anthropic / DeepSeek)
- [x] Pluggable ImageGen providers (DALL·E / Flux)
- [x] Pluggable VLM validators (GPT-4o / Claude Vision)
- [x] CPM scheduling with backend-aware duration estimates
- [x] forge.yaml unified config
- [x] Gradio Web UI
- [x] CogVideoX local backend
- [ ] Seedance backend
- [ ] Wan 2.x backend
- [ ] GPU-accelerated local video assembly
- [ ] Story template library
- [ ] Real benchmark results with Kling API

---

## 🤝 Contributing

PRs and issues welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT — see [LICENSE](LICENSE)
