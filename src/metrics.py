import json
import os
from datetime import datetime

from src.config import DATA_DIR


METRICS_FILE = os.path.join(DATA_DIR, "metrics.json")


def save_metrics(metric_data):
    os.makedirs(DATA_DIR, exist_ok=True)
    metric_data["timestamp"] = datetime.now().isoformat()

    existing = []
    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, "r") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing = []

    existing.append(metric_data)

    with open(METRICS_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)


def load_metrics():
    if not os.path.exists(METRICS_FILE):
        return []
    try:
        with open(METRICS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def generate_summary_table():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = load_metrics()
    if not data:
        return None

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # 1: Time vs Number of tasks (for same image size)
    sizes = set(d.get("image_size", "") for d in data)
    for size in sorted(sizes, key=lambda s: int(s.split("x")[0]) * int(s.split("x")[1]) if "x" in s else 0, reverse=True):
        size_data = [d for d in data if d.get("image_size") == size]
        size_data.sort(key=lambda d: d.get("total_tasks", 0))
        x = [d.get("total_tasks", 0) for d in size_data]
        y = [d.get("total_time", 0) for d in size_data]
        axes[0].plot(x, y, marker="o", label=f"{size}")
    axes[0].set_xlabel("Total de Tarefas")
    axes[0].set_ylabel("Tempo Total (s)")
    axes[0].set_title("Tempo x Numero de Tarefas")
    axes[0].legend(fontsize=7)
    axes[0].grid(True)

    # 2: Time vs multiplier (n_parts vs n_parts*10)
    multipliers = {}
    for d in data:
        mult = d.get("multiplier", 1)
        n_parts = d.get("n_parts", 0)
        ntasks = d.get("total_tasks", 0)
        key = f"n={n_parts}"
        if key not in multipliers:
            multipliers[key] = []
        multipliers[key].append({"multiplier": mult, "time": d.get("total_time", 0)})

    for key, vals in multipliers.items():
        vals.sort(key=lambda v: v["multiplier"])
        x = [v["multiplier"] for v in vals]
        y = [v["time"] for v in vals]
        axes[1].bar(
            [f"{key}\nx{int(m)}" for m, v in zip(x, y)],
            y,
            alpha=0.7,
            label=key,
        )
    axes[1].set_ylabel("Tempo Total (s)")
    axes[1].set_title("Multiplicador 1x vs Nx")
    axes[1].grid(True, axis="y")

    # 3: Time vs Image size
    sizes_bars = {}
    for d in data:
        size = d.get("image_size", "")
        if size not in sizes_bars:
            sizes_bars[size] = []
        sizes_bars[size].append(d.get("total_time", 0))
    if sizes_bars:
        x = list(sizes_bars.keys())
        y = [sum(v) / len(v) for v in sizes_bars.values()]
        axes[2].bar(x, y, alpha=0.7)
    axes[2].set_xlabel("Tamanho da Imagem (WxH)")
    axes[2].set_ylabel("Tempo Medio (s)")
    axes[2].set_title("Tempo x Tamanho da Imagem")
    axes[2].grid(True, axis="y")

    plt.tight_layout()
    buf = os.path.join(DATA_DIR, "summary_chart.png")
    fig.savefig(buf, dpi=100)
    plt.close(fig)
    return buf
