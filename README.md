# Forge

**The AI film generation system that generates scenes in parallel, not one by one.**
把影视生成的执行图从串行拓扑序升级为关键路径最优调度——同样的故事，更短的等待时间。

All existing systems (FilmAgent, MovieAgent, CoAgent) generate scenes serially — one after another.
Forge maps scenes as a Directed Acyclic Graph, computes the Critical Path, and dispatches scenes to parallel workers in priority order. Speedup scales with scene independence — the more parallel branches in your story's DAG, the faster Forge runs.

```
Serial:   S1──S2──S3──S4──S5──S6
Forge:    S1──S3──S5
          S2──S4──S6
```

---

## Quickstart | 快速开始

```bash
pip install forge-film
cp .env.example .env  # add your API keys / 填入你的 API Key
forge run examples/detective.txt --backend mock --workers 4
```

## Installation from source | 源码安装

```bash
git clone https://github.com/F-R-L/forge-film
cd forge-film
pip install -e .
```

---

## CLI Commands | 命令行

### `forge run` — Generate a film | 生成影片

```
forge run STORY_FILE [OPTIONS]

Options:
  --scenes    INTEGER  Number of scenes [default: 6]
  --workers   INTEGER  Parallel workers [default: 4]
  --backend   TEXT     mock | kling [default: mock]
  --output    PATH     Output directory [default: ./output]
  --no-validate        Skip VLM validation
```

### `forge plan` — Preview DAG without generating | 预览 DAG 结构

```bash
forge plan examples/romance.txt --scenes 6
```

### `forge benchmark` — Measure speedup | 测速对比

```bash
forge benchmark --scenes 8 --workers 4
```

---

## Architecture | 系统架构

```
Story Text / 故事文本
    │
    ▼
[Vision Compiler]  ← GPT-4o
    │ ProductionPlan (scenes + DAG)
    │ 场景结构 + 有向无环图
    ▼
[Asset Foundry]    ← parallel image generation / 并行图像生成
    │ {asset_id: Asset}
    ▼
[Forge Scheduler]  ← DAG + CPM priority queue / 关键路径优先调度
    │  ┌─────────────────────────┐
    │  │  Worker 1  Worker 2  ...│
    │  │  [S2]      [S1]         │
    │  └─────────────────────────┘
    ▼
[Stream Assembler] ← moviepy concatenation / 流式拼接
    │
    ▼
  final.mp4
```

### Key Modules | 核心模块

| Module | Description |
|--------|-------------|
| `forge/compiler/` | GPT-4o converts story → structured ProductionPlan |
| `forge/scheduler/dag.py` | Kahn topological sort + cycle detection / Kahn 拓扑排序 + 环检测 |
| `forge/scheduler/cpm.py` | Critical Path Method — forward/backward pass / 关键路径前向后向传递 |
| `forge/scheduler/scheduler.py` | Async priority-queue dispatcher / 异步优先队列调度器 |
| `forge/assets/foundry.py` | Parallel asset image generation with caching / 并行资产生成 + 缓存 |
| `forge/generation/` | Mock / Kling light / Kling heavy pipelines |
| `forge/validation/` | GPT-4o Vision consistency checker / 视觉一致性验证 |
| `forge/assembler/` | Streaming moviepy concatenation / 流式视频拼接 |

---

## Environment Variables | 环境变量

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Required for story compilation & VLM validation / 故事编译和视觉验证必填 |
| `KLING_API_KEY` | Required for Kling video generation backend |
| `KLING_API_SECRET` | Kling API secret |
| `FORGE_WORKERS` | Default worker count (default: 4) |
| `FORGE_VIDEO_BACKEND` | Default backend: mock / kling |

---

## Running Tests | 运行测试

```bash
pip install -e .[dev]
pytest tests/ -v
```

---

## License

MIT — see [LICENSE](LICENSE)
