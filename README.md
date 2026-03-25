<div align="center">

# 🎬 Forge

**One story, multiple AI models, zero manual stitching.**

Forge orchestrates Kling, CogVideoX, Seedance, and any video backend into one coherent film — fully open source.

一个故事，多个 AI 模型，零手动拼接。Forge 将 Kling、CogVideoX、Seedance 及任意视频后端编排成一部连贯影片——完全开源。

[![CI](https://github.com/F-R-L/forge-film/actions/workflows/ci.yml/badge.svg)](https://github.com/F-R-L/forge-film/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-green)](https://github.com/F-R-L/forge-film)

[English](#-why-forge) | [快速开始](#-quickstart--快速开始)

</div>

---

## ⚡ Why Forge?

2026 年有 Kling 3.0、Seedance 2.0、Sora 2、Veo 3、CogVideoX、Wan 2.6 等 6+ 个主流视频模型，各有所长。业界共识是按场景需求混用——对话戏用 Kling、风景空镜用 CogVideoX、动作戏用 Seedance。

但实际操作时，创作者要当"人肉调度器"：

- 自己判断每个场景适合哪个模型
- 分别登录不同平台 / 调用不同 API
- 手动下载中间帧、传给下一个场景做 i2v
- 手动校色（Kling 和 CogVideoX 的色调天然不同）
- 手动用剪辑软件拼接

**一个 8 场景的短片，光是在不同平台之间来回操作就能耗掉大半天。**

Forge 把这整条流程自动化：

1. **Story → DAG** — GPT-4o（或 Claude / DeepSeek）将故事编译为场景有向无环图，识别因果依赖与可并行的场景
2. **Scene-type routing** — 对话戏走 Kling、风景空镜走 CogVideoX（本地免费）、动作戏走 Seedance，路由规则完全可配置
3. **CPM priority scheduling** — 关键路径法找出最长依赖链，优先调度阻塞最多下游的场景，N 个 worker 并行生成
4. **Cross-model continuity** — 当场景 B 依赖场景 A 且两者用了不同模型时，自动提取 A 的最后一帧、做色彩校准（直方图匹配），再传给 B 作为 i2v 起始图像
5. **Streaming assembly** — 场景完成一个拼一个，归一化分辨率和帧率，输出 final.mp4

---

## 🆚 How Forge compares

| | Forge | Agent Opus (OpusClip) | Seedance 原生多镜头 | FilmAgent |
|---|---|---|---|---|
| 开源 | ✅ MIT | ❌ 闭源 SaaS | ❌ | ✅ 学术原型 |
| 本地部署 | ✅ | ❌ | ❌ | 部分 |
| 多模型混用 | ✅ 跨模型编排 | ✅ 但不可控 | ❌ 单模型 | ❌ 3D虚拟空间 |
| 跨模型色彩校准 | ✅ | 未知 | N/A | N/A |
| 可插拔后端 | ✅ 全栈四层 | ❌ | ❌ | ❌ |
| 数据安全 | ✅ 数据不出机器 | ❌ 过第三方 | ❌ | 部分 |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         forge.yaml                              │
│  llm: openai/anthropic/deepseek   → story compiler             │
│  imagegen: openai/flux/mock       → asset reference images      │
│  validator: openai/anthropic/mock → frame consistency check     │
│  routing: {scene_type → backend}  → video generation           │
└──────┬──────────┬──────────┬──────────┬──────────────────────  ┘
       │          │          │          │
       ▼          ▼          ▼          ▼
  LLMProvider  ImageGen   VLMProvider  Video Backends
  OpenAI       DALL·E     GPT-4o       Kling (light/heavy)
  Anthropic    Flux       Claude       CogVideoX
  DeepSeek     Mock       Mock         Seedance / Wan / Mock
       │          │          │          │
       ▼          ▼          │          ▼
  VisionCompiler AssetFoundry│     ForgeScheduler
  (story→DAG)   (ref images) │     (CPM + DAG + N workers)
       │          │          │          │
       └──────────┴──────────┴──────────┘
                         │
              CrossModel Continuity
              (color calibration)
                         │
                         ▼
               StreamAssembler → final.mp4
               (normalized 1280×720 @ 24fps)
```

每一层用户都能独立替换，互不影响。

---

## 🚀 Quickstart | 快速开始

### Install

```bash
git clone https://github.com/F-R-L/forge-film.git
cd forge-film
pip install -e .
cp .env.example .env
```

### Configure

编辑 `forge.yaml`（已有默认值，可按需修改）：

```yaml
llm:
  provider: openai      # openai | anthropic | deepseek
  model: gpt-4o

imagegen:
  provider: mock        # mock = no API key needed

validator:
  provider: mock

routing:
  dialogue: kling_light     # 对话戏 → Kling v1
  action: kling_heavy       # 动作戏 → Kling v1.5 Pro
  landscape: cogvideo       # 风景空镜 → CogVideoX 本地免费
  product: kling_heavy
  transition: cogvideo
  default: mock
```

在 `.env` 填入 API 密钥：

```bash
OPENAI_API_KEY=sk-...
KLING_API_KEY=...
KLING_API_SECRET=...
```

### Run

```bash
# 用 mock 后端端到端测试（无需 API key）
forge run examples/detective.txt --backend mock --workers 4

# 多模型编排演示
forge run examples/multi_backend_demo.txt --workers 4

# 只编译，查看 DAG 和路由分配（不生成视频）
forge plan examples/detective.txt --scenes 6

# 启动 Web UI
forge webui
```

### Use as a library

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

| forge.yaml key | Options | Default |
|---|---|---|
| `llm.provider` | `openai` \| `anthropic` \| `deepseek` | `openai` |
| `imagegen.provider` | `openai` \| `flux` \| `mock` | `mock` |
| `validator.provider` | `openai` \| `anthropic` \| `mock` | `mock` |
| `routing.dialogue` | any backend name | `kling_light` |
| `routing.landscape` | any backend name | `cogvideo` |
| `scheduler.workers` | int | `4` |
| `output.dir` | path | `./output` |

All API keys go in `.env` or environment variables, never in `forge.yaml`.

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
forge.yaml             # User config
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

## 📄 License

MIT — see [LICENSE](LICENSE)
