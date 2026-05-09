"""
External Sort — TPMMS (Two-Pass Multiway Merge Sort)
Adaptado al PageManager del proyecto BD2-Proyecto.

Optimizado para contar I/O a nivel de página (no de registro),
lo que refleja el costo real de acceso a disco.

Uso:
    from dbms.utils.external_sort import external_sort

    sorted_records, stats = external_sort(db, "hire_date")
"""

import os
import struct
import heapq
import time
import tempfile
import shutil


# ─────────────────────────────────────────────────────────────────────────────
#  I/O DE PÁGINAS — escritura y lectura directa sin PageManager
# ─────────────────────────────────────────────────────────────────────────────

def _write_records_to_file(records, path, record_format, page_size):
    """
    Escribe una lista de registros en un archivo .bin por páginas completas.
    Cada página contiene tantos registros como quepan.
    Retorna el número de páginas escritas.
    """
    s = struct.Struct(record_format)
    record_size = s.size + 1          # +1 por deleted flag
    records_per_page = page_size // record_size
    pages_written = 0

    with open(path, 'wb') as f:
        for i in range(0, len(records), records_per_page):
            page = bytearray(page_size)
            batch = records[i: i + records_per_page]
            for j, rec in enumerate(batch):
                offset = j * record_size
                page[offset] = 0                              # active flag
                page[offset + 1: offset + record_size] = s.pack(*rec)
            f.write(page)
            pages_written += 1

    return pages_written


def _read_records_from_file(path, record_format, page_size):
    """
    Lee todos los registros activos de un archivo .bin por páginas completas.
    Retorna (lista_de_registros, páginas_leídas).
    """
    s = struct.Struct(record_format)
    record_size = s.size + 1
    records_per_page = page_size // record_size
    records = []
    pages_read = 0

    file_size = os.path.getsize(path)
    num_pages = file_size // page_size

    with open(path, 'rb') as f:
        for _ in range(num_pages):
            page = f.read(page_size)
            pages_read += 1
            for j in range(records_per_page):
                offset = j * record_size
                if offset + record_size > len(page):
                    break
                flag = page[offset]
                if flag == 0:   # active
                    data = page[offset + 1: offset + record_size]
                    records.append(s.unpack(data))

    return records, pages_read


# ─────────────────────────────────────────────────────────────────────────────
#  FASE 1 — Generación de runs
# ─────────────────────────────────────────────────────────────────────────────

def generate_runs(pm, buffer_size, sort_key_idx, record_format, tmp_dir):
    """
    Lee el heap en bloques de B páginas, ordena en memoria y escribe runs.

    Args:
        pm:            PageManager de la tabla origen.
        buffer_size:   Tamaño del buffer en bytes.
        sort_key_idx:  Índice (0-based) de la columna de ordenamiento.
        record_format: Formato struct de los registros.
        tmp_dir:       Directorio temporal para los runs.

    Returns:
        (run_paths, pages_read, pages_written)
    """
    s = struct.Struct(record_format)
    record_size      = s.size + 1
    page_size        = pm.page_size
    records_per_page = page_size // record_size
    B                = max(1, buffer_size // page_size)
    total_pages      = pm.num_pages()

    run_paths     = []
    pages_read    = 0
    pages_written = 0

    for i in range(0, max(total_pages, 1), B):
        temp_buffer = []

        # Leer B páginas directamente del heap
        for p in range(i, min(i + B, total_pages)):
            page = pm.read_page(p)
            pages_read += 1
            for slot in range(records_per_page):
                offset = slot * record_size
                if page[offset] == 0:   # active
                    data = page[offset + 1: offset + record_size]
                    temp_buffer.append(s.unpack(data))

        if not temp_buffer:
            continue

        # Ordenar en memoria
        temp_buffer.sort(key=lambda x: x[sort_key_idx])

        # Escribir run como páginas completas
        run_path = os.path.join(tmp_dir, f"run_{len(run_paths)}.bin")
        w = _write_records_to_file(temp_buffer, run_path, record_format, page_size)
        pages_written += w
        run_paths.append(run_path)

    return run_paths, pages_read, pages_written


# ─────────────────────────────────────────────────────────────────────────────
#  MERGE de un lote de runs
# ─────────────────────────────────────────────────────────────────────────────

def _merge_runs(run_paths, output_path, record_format, page_size, sort_key_idx):
    """
    Merge de un lote de runs hacia output_path usando un min-heap.
    Lee y escribe por páginas completas.

    Returns:
        (pages_read, pages_written)
    """
    pages_read    = 0
    pages_written = 0

    # Cargar cada run completo
    run_iters = []
    for path in run_paths:
        records, r = _read_records_from_file(path, record_format, page_size)
        pages_read += r
        run_iters.append(iter(records))

    # Inicializar min-heap
    # (clave, índice_run, registro) — índice_run rompe empates entre claves iguales
    min_heap = []
    for i, it in enumerate(run_iters):
        rec = next(it, None)
        if rec is not None:
            heapq.heappush(min_heap, (rec[sort_key_idx], i, rec))

    # Merge
    merged = []
    while min_heap:
        val, run_idx, rec = heapq.heappop(min_heap)
        merged.append(rec)
        next_rec = next(run_iters[run_idx], None)
        if next_rec is not None:
            heapq.heappush(min_heap, (next_rec[sort_key_idx], run_idx, next_rec))

    # Escribir resultado por páginas completas
    w = _write_records_to_file(merged, output_path, record_format, page_size)
    pages_written += w

    return pages_read, pages_written


# ─────────────────────────────────────────────────────────────────────────────
#  FASE 2 — Multiway merge respetando límite de buffer
# ─────────────────────────────────────────────────────────────────────────────

def multiway_merge(run_paths, output_path, record_format, page_size,
                   buffer_size, sort_key_idx, tmp_dir):
    """
    Reduce los runs en pasadas intermedias hasta que quepan en una sola
    pasada final (máximo B-1 runs simultáneos).

    Returns:
        (pages_read, pages_written)
    """
    B             = max(2, buffer_size // page_size)
    max_streams   = B - 1
    pages_read    = 0
    pages_written = 0
    current_runs  = list(run_paths)
    round_num     = 0

    # Pasadas intermedias
    while len(current_runs) > max_streams:
        next_round = []

        for i in range(0, len(current_runs), max_streams):
            batch    = current_runs[i: i + max_streams]
            temp_out = os.path.join(tmp_dir, f"round{round_num}_batch{i}.bin")

            r, w = _merge_runs(batch, temp_out, record_format, page_size, sort_key_idx)
            pages_read    += r
            pages_written += w
            next_round.append(temp_out)

            # Limpiar temporales de rondas anteriores
            if round_num > 0:
                for p in batch:
                    if os.path.exists(p):
                        os.remove(p)

        current_runs = next_round
        round_num   += 1

    # Pasada final
    r, w = _merge_runs(current_runs, output_path, record_format, page_size, sort_key_idx)
    pages_read    += r
    pages_written += w

    if round_num > 0:
        for p in current_runs:
            if os.path.exists(p):
                os.remove(p)

    return pages_read, pages_written


# ─────────────────────────────────────────────────────────────────────────────
#  PUNTO DE ENTRADA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def external_sort(db, sort_column, buffer_size=64 * 1024):
    """
    Ejecuta TPMMS sobre la tabla del DataBase dado.

    Args:
        db:           Instancia de DataBase.
        sort_column:  Nombre de la columna por la que ordenar.
        buffer_size:  Tamaño del buffer en bytes (default: 64 KB).

    Returns:
        (sorted_records, stats)
        - sorted_records: lista de tuplas ordenadas y limpias
        - stats: dict con métricas detalladas por fase

    Raises:
        ValueError: si sort_column no existe en el schema.
    """
    col_names = list(db.schema.keys())
    if sort_column not in col_names:
        raise ValueError(
            f"Columna '{sort_column}' no existe en '{db.table_name}'. "
            f"Disponibles: {col_names}"
        )

    sort_key_idx  = col_names.index(sort_column)
    record_format = db.pm.struct.format
    page_size     = db.pm.page_size

    tmp_dir = tempfile.mkdtemp(prefix="esort_")

    try:
        start_total = time.perf_counter()

        # ── Fase 1: generación de runs ────────────────────────────────────
        t1 = time.perf_counter()
        run_paths, r1, w1 = generate_runs(
            db.pm, buffer_size, sort_key_idx, record_format, tmp_dir
        )
        time_p1 = time.perf_counter() - t1

        if not run_paths:
            return [], {
                "runs_generated":   0,
                "pages_read_p1":    0,
                "pages_written_p1": 0,
                "pages_read_p2":    0,
                "pages_written_p2": 0,
                "pages_read":       0,
                "pages_written":    0,
                "io_total":         0,
                "time_phase1_sec":  0.0,
                "time_phase2_sec":  0.0,
                "time_total_sec":   0.0,
            }

        # ── Fase 2: multiway merge ────────────────────────────────────────
        t2 = time.perf_counter()
        output_path = os.path.join(tmp_dir, "sorted_output.bin")
        r2, w2 = multiway_merge(
            run_paths, output_path, record_format,
            page_size, buffer_size, sort_key_idx, tmp_dir
        )
        time_p2 = time.perf_counter() - t2

        # ── Leer resultado final ──────────────────────────────────────────
        raw_records, _ = _read_records_from_file(output_path, record_format, page_size)
        sorted_records  = [db._clean_record(r) for r in raw_records]

        stats = {
            "runs_generated":   len(run_paths),
            # Métricas por fase
            "pages_read_p1":    r1,
            "pages_written_p1": w1,
            "pages_read_p2":    r2,
            "pages_written_p2": w2,
            # Totales
            "pages_read":       r1 + r2,
            "pages_written":    w1 + w2,
            "io_total":         r1 + r2 + w1 + w2,
            # Tiempos
            "time_phase1_sec":  round(time_p1, 4),
            "time_phase2_sec":  round(time_p2, 4),
            "time_total_sec":   round(time.perf_counter() - start_total, 4),
        }

        return sorted_records, stats

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)