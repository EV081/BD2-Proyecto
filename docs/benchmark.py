"""
Benchmark: B+ Tree vs Sequential File vs Extendible Hashing
Dataset: cities.csv (148,062 registros reales)
Particiones: n = 1,000 / 10,000 / 100,000

Mide accesos a disco (paginas leidas + escritas) y tiempo (ms)
para insercion, busqueda puntual y busqueda por rango.
Indexa por columna 'id' (int, unico).
"""

import os
import sys
import csv
import json
import time
import random
import gc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from dbms.structures.bplus import BPlusTree
from dbms.structures.sequentialfile import SequentialFile
from dbms.structures.Extendible_Hashing import ExtendibleHash

# ── Config ──────────────────────────────────────────────────────────────────
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "uploaded_files", "cities.csv")
SIZES = [1_000, 10_000, 100_000]
TECHNIQUES = ["bplus", "sequential", "hash"]
LABELS = {"bplus": "B+ Tree", "sequential": "Sequential File", "hash": "Ext. Hashing"}
COLORS = {"bplus": "#2196F3", "sequential": "#4CAF50", "hash": "#FF9800"}
NUM_SEARCH_SAMPLES = 200
RANGE_SPAN = 500           # rango de IDs para range_search
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
IDX_DIR = os.path.join(PROJECT_DIR, "indexes")


def load_cities():
    """Lee cities.csv y retorna lista de (id, country_id) como ints."""
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cid = int(row["id"])
                country = int(row["country_id"])
                rows.append((cid, country))
            except (ValueError, KeyError):
                continue
    return rows


def make_index(tech, name):
    """Crea un indice limpio."""
    fname = f"bench_{name}.idx"
    actual = os.path.join(IDX_DIR, fname)
    if os.path.exists(actual):
        os.remove(actual)
    fpath = os.path.join(PROJECT_DIR, fname)
    if tech == "bplus":
        return BPlusTree(fpath, key_format="i", unique=True)
    elif tech == "sequential":
        # max_aux alto para reducir reconstrucciones y hacer benchmark factible
        return SequentialFile(fpath, key_format="i", unique=True, max_aux=20000)
    elif tech == "hash":
        return ExtendibleHash(fpath, key_format="i", unique=True)


def cleanup_index(idx):
    """Remove index file from disk."""
    p = getattr(idx, "index_file", None)
    if p and os.path.exists(p):
        os.remove(p)


def run_benchmark():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IDX_DIR, exist_ok=True)

    print("Cargando cities.csv ...", end=" ", flush=True)
    all_rows = load_cities()
    print(f"{len(all_rows)} registros leidos.")

    # Shuffle determinista para particiones
    random.seed(42)
    random.shuffle(all_rows)

    results = {t: {} for t in TECHNIQUES}

    for n in SIZES:
        partition = all_rows[:n]
        ids_in_partition = [r[0] for r in partition]
        id_min = min(ids_in_partition)
        id_max = max(ids_in_partition)

        for tech in TECHNIQUES:
            label = LABELS[tech]
            print(f"  [{label:>17}] n={n:>6} ...", end=" ", flush=True)

            idx = make_index(tech, f"{tech}_{n}")

            # ── INSERTION ────────────────────────────────────────────
            idx.reset_stats()
            t0 = time.perf_counter()

            for cid, country in partition:
                rid = (cid % 1000, cid % 340)  # simulated RID
                idx.add(cid, rid)

            insert_time = (time.perf_counter() - t0) * 1000
            insert_disk = idx.disk_reads + idx.disk_writes

            # ── POINT SEARCH ─────────────────────────────────────────
            search_keys = random.sample(ids_in_partition, min(NUM_SEARCH_SAMPLES, n))

            idx.reset_stats()
            t0 = time.perf_counter()

            for k in search_keys:
                idx.search(k)

            search_time = (time.perf_counter() - t0) * 1000
            search_disk = idx.disk_reads + idx.disk_writes
            avg_search_disk = search_disk / len(search_keys)
            avg_search_time = search_time / len(search_keys)

            # ── RANGE SEARCH ─────────────────────────────────────────
            if tech == "hash":
                avg_range_disk = float("nan")
                avg_range_time = float("nan")
            else:
                # Generar rangos validos dentro de los IDs del partition
                sorted_ids = sorted(ids_in_partition)
                range_starts = random.sample(
                    sorted_ids[:max(1, len(sorted_ids) - RANGE_SPAN)],
                    min(NUM_SEARCH_SAMPLES, len(sorted_ids))
                )

                idx.reset_stats()
                t0 = time.perf_counter()

                for rs in range_starts:
                    idx.range_search(rs, rs + RANGE_SPAN)

                range_time = (time.perf_counter() - t0) * 1000
                range_disk = idx.disk_reads + idx.disk_writes
                avg_range_disk = range_disk / len(range_starts)
                avg_range_time = range_time / len(range_starts)

            results[tech][n] = {
                "insert_disk": insert_disk,
                "insert_time_ms": round(insert_time, 2),
                "search_disk_avg": round(avg_search_disk, 2),
                "search_time_avg_ms": round(avg_search_time, 4),
                "range_disk_avg": round(avg_range_disk, 2) if avg_range_disk == avg_range_disk else float("nan"),
                "range_time_avg_ms": round(avg_range_time, 4) if avg_range_time == avg_range_time else float("nan"),
            }

            print(f"insert={insert_time:.0f}ms  "
                  f"search_avg={avg_search_time:.3f}ms  "
                  f"range_avg={'N/A' if avg_range_time != avg_range_time else f'{avg_range_time:.3f}'}ms  "
                  f"insert_io={insert_disk}")

            cleanup_index(idx)
            del idx
            gc.collect()

    return results


# ── PLOTTING ─────────────────────────────────────────────────────────────────

def _is_valid(v):
    try:
        return not (v != v)
    except TypeError:
        return v is not None


def plot_bar(data, metric_key, title, ylabel, filename, per_record=False):
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(SIZES))
    width = 0.25

    for i, tech in enumerate(TECHNIQUES):
        vals = []
        for n in SIZES:
            v = data[tech][n][metric_key]
            if _is_valid(v):
                if per_record:
                    v = v / n
            else:
                v = 0
            vals.append(v)
        bars = ax.bar(x + i * width, vals, width, label=LABELS[tech],
                      color=COLORS[tech], edgecolor="white")
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f"{val:.1f}", ha="center", va="bottom", fontsize=7)
            else:
                ax.text(bar.get_x() + bar.get_width() / 2, 0,
                        "N/A", ha="center", va="bottom", fontsize=7, color="gray")

    ax.set_xlabel("Numero de registros (n)", fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xticks(x + width)
    ax.set_xticklabels([f"n={n:,}" for n in SIZES])
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, filename), dpi=150)
    plt.close()


def plot_line(data, metric_key, title, ylabel, filename):
    fig, ax = plt.subplots(figsize=(10, 6))

    for tech in TECHNIQUES:
        raw_vals = [data[tech][n][metric_key] for n in SIZES]
        valid = [(s, v) for s, v in zip(SIZES, raw_vals) if _is_valid(v)]
        if not valid:
            continue
        xs, ys = zip(*valid)
        ax.plot(xs, ys, "o-", label=LABELS[tech], color=COLORS[tech],
                linewidth=2, markersize=8)
        for x_val, y_val in zip(xs, ys):
            ax.annotate(f"{y_val:.2f}", (x_val, y_val),
                        textcoords="offset points", xytext=(0, 10),
                        ha="center", fontsize=8)

    ax.set_xlabel("Numero de registros (n)", fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xscale("log")
    ax.set_xticks(SIZES)
    ax.set_xticklabels([f"{n:,}" for n in SIZES])
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, filename), dpi=150)
    plt.close()


def generate_plots(results):
    # Insertion
    plot_bar(results, "insert_disk",
             "Insercion: Accesos a disco totales (cities.csv)",
             "Paginas leidas + escritas", "insert_disk_total.png")

    plot_bar(results, "insert_disk",
             "Insercion: Accesos a disco por registro (cities.csv)",
             "Paginas leidas + escritas / registro", "insert_disk_per_record.png",
             per_record=True)

    plot_line(results, "insert_time_ms",
              "Insercion: Tiempo total (cities.csv)",
              "Tiempo (ms)", "insert_time.png")

    # Point search
    plot_bar(results, "search_disk_avg",
             "Busqueda puntual: Accesos a disco promedio (cities.csv)",
             "Paginas leidas + escritas (promedio)", "search_disk.png")

    plot_line(results, "search_time_avg_ms",
              "Busqueda puntual: Tiempo promedio por consulta (cities.csv)",
              "Tiempo (ms)", "search_time.png")

    # Range search
    plot_bar(results, "range_disk_avg",
             "Busqueda por rango: Accesos a disco promedio (cities.csv, rango=500)",
             "Paginas leidas + escritas (promedio)", "range_disk.png")

    plot_line(results, "range_time_avg_ms",
              "Busqueda por rango: Tiempo promedio (cities.csv, rango=500)",
              "Tiempo (ms)", "range_time.png")


def print_tables(results):
    print("\n\n### Tablas de resultados (Dataset: cities.csv)\n")

    print("#### Insercion (total para n registros)\n")
    print("| Tecnica | n=1,000 disk | n=10,000 disk | n=100,000 disk | n=1,000 ms | n=10,000 ms | n=100,000 ms |")
    print("|---|---|---|---|---|---|---|")
    for tech in TECHNIQUES:
        d = results[tech]
        print(f"| {LABELS[tech]} | {d[1000]['insert_disk']:,} | {d[10000]['insert_disk']:,} | {d[100000]['insert_disk']:,} | {d[1000]['insert_time_ms']:.1f} | {d[10000]['insert_time_ms']:.1f} | {d[100000]['insert_time_ms']:.1f} |")

    print("\n#### Busqueda puntual (promedio por consulta)\n")
    print("| Tecnica | n=1,000 disk | n=10,000 disk | n=100,000 disk | n=1,000 ms | n=10,000 ms | n=100,000 ms |")
    print("|---|---|---|---|---|---|---|")
    for tech in TECHNIQUES:
        d = results[tech]
        print(f"| {LABELS[tech]} | {d[1000]['search_disk_avg']:.2f} | {d[10000]['search_disk_avg']:.2f} | {d[100000]['search_disk_avg']:.2f} | {d[1000]['search_time_avg_ms']:.4f} | {d[10000]['search_time_avg_ms']:.4f} | {d[100000]['search_time_avg_ms']:.4f} |")

    def _fmt(v, fmt_str):
        return "N/A" if not _is_valid(v) else format(v, fmt_str)

    print("\n#### Busqueda por rango (promedio por consulta, rango=500 IDs)\n")
    print("| Tecnica | n=1,000 disk | n=10,000 disk | n=100,000 disk | n=1,000 ms | n=10,000 ms | n=100,000 ms |")
    print("|---|---|---|---|---|---|---|")
    for tech in TECHNIQUES:
        d = results[tech]
        rd1 = _fmt(d[1000]['range_disk_avg'], '.2f')
        rd2 = _fmt(d[10000]['range_disk_avg'], '.2f')
        rd3 = _fmt(d[100000]['range_disk_avg'], '.2f')
        rt1 = _fmt(d[1000]['range_time_avg_ms'], '.4f')
        rt2 = _fmt(d[10000]['range_time_avg_ms'], '.4f')
        rt3 = _fmt(d[100000]['range_time_avg_ms'], '.4f')
        print(f"| {LABELS[tech]} | {rd1} | {rd2} | {rd3} | {rt1} | {rt2} | {rt3} |")


if __name__ == "__main__":
    print("=" * 60)
    print("  BENCHMARK: B+ Tree vs Sequential File vs Ext. Hashing")
    print("  Dataset: cities.csv (148,062 registros)")
    print("=" * 60)

    results = run_benchmark()

    print("\nGenerando graficos...")
    generate_plots(results)
    print(f"Graficos guardados en: {OUTPUT_DIR}/")

    print_tables(results)

    def sanitize(obj):
        if isinstance(obj, float) and obj != obj:
            return None
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        return obj

    with open(os.path.join(OUTPUT_DIR, "benchmark_results.json"), "w") as f:
        json.dump(sanitize(results), f, indent=2)
    print(f"\nDatos crudos en: {OUTPUT_DIR}/benchmark_results.json")
