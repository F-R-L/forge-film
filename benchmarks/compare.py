import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


async def compare(num_scenes: int = 8, workers_list: list[int] = None):
    import matplotlib.pyplot as plt
    from benchmarks.mock_runner import make_mock_plan, run_serial, run_parallel
    from rich.console import Console

    console = Console()
    workers_list = workers_list or [1, 2, 4, 8]
    plan = make_mock_plan(num_scenes)

    serial_time = await run_serial(plan)
    results = {"Serial": serial_time}

    for w in workers_list:
        t = await run_parallel(plan, w)
        results[f"{w} workers"] = t
        console.print(f"Workers={w}: {t:.2f}s (speedup {serial_time/t:.1f}x)")

    # Plot
    labels = list(results.keys())
    times = list(results.values())
    colors = ["#e74c3c"] + ["#2ecc71"] * len(workers_list)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, times, color=colors)
    ax.set_ylabel("Time (seconds)")
    ax.set_title(f"Forge DAG Scheduling vs Serial ({num_scenes} scenes)")
    for bar, t in zip(bars, times):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.1,
            f"{t:.1f}s",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    os.makedirs("./output", exist_ok=True)
    out = "./output/benchmark.png"
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    console.print(f"[green]Chart saved to {out}[/green]")
    plt.close()


if __name__ == "__main__":
    asyncio.run(compare())
