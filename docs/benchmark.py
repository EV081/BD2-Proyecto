import os
import sys
import csv
import json
import time
import random
import shutil
import gc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.api.dbengine import DataBase

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")

SIZES = [1_000, 10_000, 100_000]
CSV_FILES = {
    1_000:   os.path.join(PROJECT_DIR, "uploaded_files", "cities_1k.csv"),
    10_000:  os.path.join(PROJECT_DIR, "uploaded_files", "cities_10k.csv"),
    100_000: os.path.join(PROJECT_DIR, "uploaded_files", "cities_100k.csv"),
}

TECHNIQUES = ["bplus", "sequential", "hash"]
LABELS = {"bplus": "B+ Tree", "sequential": "Sequential File", "hash": "Ext. Hashing"}
COLORS = {"bplus": "#2196F3", "sequential": "#4CAF50", "hash": "#FF9800"}

NUM_QUERIES = 200       # consultas de prueba para promediar
RANGE_SPAN  = 500       # amplitud del rango para range_search
SEED = 42

SCHEMA = {
    "id": "int",
    "country_id": "int",
    "latitude": "float",
    "longitude": "float",
    "name": "char(40)",
}


# Data loading

def load_csv(n):
    path = CSV_FILES[n]
    records = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                records.append({
                    "id":         int(row["id"]),
                    "country_id": int(row["country_id"]),
                    "latitude":   float(row["latitude"]),
                    "longitude":  float(row["longitude"]),
                    "name":       row["name"][:40],
                })
            except (ValueError, KeyError):
                continue
    return records


def cleanup():
    for folder in ["data", "schemas", "indexes"]:
        p = os.path.join(PROJECT_DIR, folder)
        if os.path.isdir(p):
            shutil.rmtree(p)


# Table creation 

def create_table(technique, table_name="bench", n=None):
    if technique == "bplus":
        return DataBase(table_name, schema=SCHEMA,
                        primary_key="id", pk_index_type="bplus")

    elif technique == "sequential":
        # Balance: 10 reconstrucciones totales, aux area pequeña
        max_aux = max(62, n // 10) if n else None
        return DataBase(table_name, schema=SCHEMA,
                        primary_key="id", pk_index_type="sequential",
                        max_aux=max_aux)

    elif technique == "hash":
        # Crear con bplus auto, reemplazar por hash
        db = DataBase(table_name, schema=SCHEMA, primary_key="id", pk_index_type="bplus")
        db.drop_index("id")
        db.create_index("id", index_type="hash", unique=True)
        return db


# Benchmarks 

def _empty_metrics():
    return {"time_ms": 0, "total_reads": 0, "total_writes": 0,
            "heap_reads": 0, "heap_writes": 0,
            "index_reads": 0, "index_writes": 0}


def _add_metrics(acc, m):
    for k in acc:
        acc[k] += m[k]


def benchmark_insert(db, records):
    total = _empty_metrics()
    for rec in records:
        _, m = db.insert(rec, metrics=True)
        _add_metrics(total, m)
    return total


def benchmark_point_search(db, keys):
    total = _empty_metrics()
    for key in keys:
        _, m = db.select("id", key, metrics=True)
        _add_metrics(total, m)
    n = len(keys)
    return {k: v / n for k, v in total.items()}


def benchmark_range_search(db, ranges):
    total = _empty_metrics()
    for begin, end in ranges:
        _, m = db.select_range("id", begin, end, metrics=True)
        _add_metrics(total, m)
    n = len(ranges)
    return {k: v / n for k, v in total.items()}


# Main run

def run_benchmark():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = {t: {} for t in TECHNIQUES}

    for n in SIZES:
        print(f"\n{'='*65}")
        print(f"  Dataset: N = {n:,} registros")
        print(f"{'='*65}")

        records = load_csv(n)
        ids = sorted(set(r["id"] for r in records))

        # Generar claves de busqueda deterministas
        rng = random.Random(SEED)
        search_keys = rng.sample(ids, min(NUM_QUERIES, len(ids)))

        # Generar rangos: seleccionar inicio aleatorio, amplitud fija
        valid_starts = [x for x in ids if x + RANGE_SPAN <= ids[-1]]
        range_starts = rng.sample(valid_starts, min(NUM_QUERIES, len(valid_starts)))
        ranges = [(s, s + RANGE_SPAN) for s in range_starts]

        for tech in TECHNIQUES:
            label = LABELS[tech]
            print(f"\n  --- {label} ---")
            cleanup()

            db = create_table(tech, f"bench_{tech}", n=n)

            # INSERT 
            print(f"    Insertando {n:,} registros ...", end=" ", flush=True)
            m_ins = benchmark_insert(db, records)
            ins_disk = m_ins["total_reads"] + m_ins["total_writes"]
            print(f"{m_ins['time_ms']:.0f} ms | accesos={ins_disk:,}")

            # POINT SEARCH
            print(f"    Busqueda puntual ({len(search_keys)} consultas) ...", end=" ", flush=True)
            m_pt = benchmark_point_search(db, search_keys)
            pt_disk = m_pt["total_reads"] + m_pt["total_writes"]
            print(f"{m_pt['time_ms']:.4f} ms/q | accesos={pt_disk:.2f}/q")

            # RANGE SEARCH
            if tech == "hash":
                # Hash no soporta range_search -> full scan
                print(f"    Busqueda por rango: N/A (hash no soporta rango, cae a full scan)")
                m_rg = benchmark_range_search(db, ranges)
                rg_disk = m_rg["total_reads"] + m_rg["total_writes"]
                print(f"      (full scan: {m_rg['time_ms']:.4f} ms/q | accesos={rg_disk:.2f}/q)")
            else:
                print(f"    Busqueda por rango ({len(ranges)} consultas, span={RANGE_SPAN}) ...", end=" ", flush=True)
                m_rg = benchmark_range_search(db, ranges)
                rg_disk = m_rg["total_reads"] + m_rg["total_writes"]
                print(f"{m_rg['time_ms']:.4f} ms/q | accesos={rg_disk:.2f}/q")

            results[tech][n] = {
                "insert_disk":        int(ins_disk),
                "insert_time_ms":     round(m_ins["time_ms"], 2),
                "insert_disk_per_rec": round(ins_disk / n, 4),
                "search_disk_avg":    round(pt_disk, 2),
                "search_time_avg_ms": round(m_pt["time_ms"], 4),
                "range_disk_avg":     round(rg_disk, 2),
                "range_time_avg_ms":  round(m_rg["time_ms"], 4),
                "range_is_fullscan":  tech == "hash",
            }

            del db
            gc.collect()

    cleanup()
    return results


# Plotting 

def plot_grouped_bar(data, metric_key, title, ylabel, filename, skip_hash=False, use_log=False):
    techs = [t for t in TECHNIQUES if not (skip_hash and t == "hash")]
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(SIZES))
    width = 0.8 / len(techs)

    for i, tech in enumerate(techs):
        vals = [data[tech][n][metric_key] for n in SIZES]
        offset = (i - len(techs) / 2 + 0.5) * width
        bars = ax.bar(x + offset, vals, width, label=LABELS[tech],
                    color=COLORS[tech], edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, vals):
            if val > 0:
                label_text = f"{val:,.0f}" if val >= 100 else f"{val:.2f}"
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height(), label_text,
                        ha="center", va="bottom", fontsize=7)

    ax.set_xlabel("Numero de registros (N)", fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([f"N={n:,}" for n in SIZES])
    if use_log:
        ax.set_yscale("log")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, filename), dpi=150)
    plt.close()


def plot_line(data, metric_key, title, ylabel, filename, skip_hash=False):
    techs = [t for t in TECHNIQUES if not (skip_hash and t == "hash")]
    fig, ax = plt.subplots(figsize=(10, 6))

    for tech in techs:
        vals = [data[tech][n][metric_key] for n in SIZES]
        ax.plot(SIZES, vals, "o-", label=LABELS[tech], color=COLORS[tech],
                linewidth=2, markersize=8)
        for xv, yv in zip(SIZES, vals):
            label_text = f"{yv:,.0f}" if yv >= 100 else f"{yv:.2f}"
            ax.annotate(label_text, (xv, yv),
                        textcoords="offset points", xytext=(0, 12),
                        ha="center", fontsize=8)

    ax.set_xlabel("Numero de registros (N)", fontsize=12)
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
    print("\nGenerando graficos ...", flush=True)

    # Insercion 
    plot_grouped_bar(results, "insert_disk",
                    "Insercion: Accesos a disco totales",
                    "Paginas (read + write)", "insert_disk_total.png",
                    use_log=True)

    plot_grouped_bar(results, "insert_disk_per_rec",
                    "Insercion: Accesos a disco por registro",
                    "Paginas / registro", "insert_disk_per_record.png")

    plot_line(results, "insert_time_ms",
              "Insercion: Tiempo total",
              "Tiempo (ms)", "insert_time.png")

    # Busqueda puntual 
    plot_grouped_bar(results, "search_disk_avg",
                    "Busqueda puntual: Accesos a disco promedio",
                    "Paginas / consulta", "search_disk.png")

    plot_line(results, "search_time_avg_ms",
            "Busqueda puntual: Tiempo promedio por consulta",
            "Tiempo (ms)", "search_time.png")

    # Busqueda por rango (sin hash)
    plot_grouped_bar(results, "range_disk_avg",
                    "Busqueda por rango: Accesos a disco promedio (span=500)",
                    "Paginas / consulta", "range_disk.png",
                    skip_hash=True)

    plot_line(results, "range_time_avg_ms",
            "Busqueda por rango: Tiempo promedio (span=500)",
            "Tiempo (ms)", "range_time.png",
            skip_hash=True)

    print(f"  Graficos guardados en: {OUTPUT_DIR}/")


# Tables 

def print_tables(results):
    sep = "-" * 100

    # Insercion 
    print(f"\n{sep}")
    print("  INSERCION (total para N registros)")
    print(sep)
    print(f"  {'Tecnica':<20} | {'N=1,000':>18} | {'N=10,000':>18} | {'N=100,000':>18}")
    print(f"  {'':<20} | {'disk':>8} {'ms':>8} | {'disk':>8} {'ms':>8} | {'disk':>8} {'ms':>8}")
    print(f"  {'-'*20}-+-{'-'*18}-+-{'-'*18}-+-{'-'*18}")
    for tech in TECHNIQUES:
        d = results[tech]
        print(f"  {LABELS[tech]:<20} "
            f"| {d[1000]['insert_disk']:>8,} {d[1000]['insert_time_ms']:>8.1f} "
            f"| {d[10000]['insert_disk']:>8,} {d[10000]['insert_time_ms']:>8.1f} "
            f"| {d[100000]['insert_disk']:>8,} {d[100000]['insert_time_ms']:>8.1f}")

    # Busqueda puntual
    print(f"\n{sep}")
    print("  BUSQUEDA PUNTUAL (promedio por consulta)")
    print(sep)
    print(f"  {'Tecnica':<20} | {'N=1,000':>18} | {'N=10,000':>18} | {'N=100,000':>18}")
    print(f"  {'':<20} | {'disk':>8} {'ms':>8} | {'disk':>8} {'ms':>8} | {'disk':>8} {'ms':>8}")
    print(f"  {'-'*20}-+-{'-'*18}-+-{'-'*18}-+-{'-'*18}")
    for tech in TECHNIQUES:
        d = results[tech]
        print(f"  {LABELS[tech]:<20} "
            f"| {d[1000]['search_disk_avg']:>8.2f} {d[1000]['search_time_avg_ms']:>8.4f} "
            f"| {d[10000]['search_disk_avg']:>8.2f} {d[10000]['search_time_avg_ms']:>8.4f} "
            f"| {d[100000]['search_disk_avg']:>8.2f} {d[100000]['search_time_avg_ms']:>8.4f}")

    # Busqueda por rango 
    print(f"\n{sep}")
    print(f"  BUSQUEDA POR RANGO (promedio por consulta, span={RANGE_SPAN})")
    print(sep)
    print(f"  {'Tecnica':<20} | {'N=1,000':>18} | {'N=10,000':>18} | {'N=100,000':>18}")
    print(f"  {'':<20} | {'disk':>8} {'ms':>8} | {'disk':>8} {'ms':>8} | {'disk':>8} {'ms':>8}")
    print(f"  {'-'*20}-+-{'-'*18}-+-{'-'*18}-+-{'-'*18}")
    for tech in TECHNIQUES:
        d = results[tech]
        suffix = " *" if tech == "hash" else ""
        print(f"  {LABELS[tech]:<20} "
            f"| {d[1000]['range_disk_avg']:>8.2f} {d[1000]['range_time_avg_ms']:>8.4f} "
            f"| {d[10000]['range_disk_avg']:>8.2f} {d[10000]['range_time_avg_ms']:>8.4f} "
            f"| {d[100000]['range_disk_avg']:>8.2f} {d[100000]['range_time_avg_ms']:>8.4f}{suffix}")
    print("  * Ext. Hashing no soporta rango → cae a full scan")


# Entry point 

if __name__ == "__main__":
    print()
    print("=" * 65)
    print("  BENCHMARK: B+ Tree vs Sequential File vs Ext. Hashing")
    print("  Dataset: cities.csv | N = 1k / 10k / 100k")
    print("  Metricas: accesos a disco (pags) + tiempo (ms)")
    print("=" * 65)

    results = run_benchmark()

    generate_plots(results)
    print_tables(results)

    # Guardar JSON
    json_path = os.path.join(OUTPUT_DIR, "benchmark_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Datos crudos: {json_path}")
    print()
