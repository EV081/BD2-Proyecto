"""
DataBase Manager
"""

import time

from dbms.utils.pagemanager import PageManager
from dbms.utils.schema import SchemaManager
from dbms.structures.bplus import BPlusTree
from dbms.structures.rtree import RTree


class DataBase:

    PAGE_SIZE = 4096

    TYPE_MAP = {
        "int": "i",
        "float": "f",
        "char": "s"   # ojo: requiere tamaño
    }

    # Tipos de indice soportados (extensible para rtree, sequential, hash)
    INDEX_TYPES = {"bplus", "rtree", "sequential", "hash"}

    def __init__(self, table_name, schema=None, primary_key=None):
        self.table_name = table_name
        self.sm = SchemaManager(table_name)
        self.pm = None
        self.schema = None        # {"col": "type", ...}
        self.primary_key = None   # "col_name" o None

        # {column_or_tuple: {"type": "bplus"|"rtree"|..., "index": <instancia>, "unique": bool}}
        self.indexes = {}

        # Columnas POINT logicas: {"ubicacion": ("ubicacion_x", "ubicacion_y")}
        self.point_columns = {}

        self._load_or_create(schema, primary_key)

    # ------------------------
    # INIT
    # ------------------------
    def _load_or_create(self, schema, primary_key):
        if self.sm.schema_exists():
            raw = self.sm.get_schema()

            # Formato nuevo: {"columns": {...}, "primary_key": ..., "indexes": [...]}
            if isinstance(raw, dict) and "columns" in raw:
                columns = raw["columns"]
                saved_pk = raw.get("primary_key")
                indexes_meta = raw.get("indexes", [])
            else:
                # Formato viejo: {"col": "type", ...} — compatibilidad
                columns = raw
                saved_pk = None
                indexes_meta = []

            if schema is not None and schema != columns:
                raise ValueError(
                    "El schema ya existe. No se puede modificar."
                )

            self.schema = columns
            self.primary_key = saved_pk
            self.point_columns = {
                k: tuple(v) for k, v in raw.get("point_columns", {}).items()
            }

            # Crear PageManager
            record_format = self._build_struct_format(self.schema)
            self.pm = PageManager(self.table_name, record_format)

            # Recrear indices desde la metadata guardada
            for idx_meta in indexes_meta:
                col = idx_meta["column"]
                if isinstance(col, list):
                    col = tuple(col)
                self.create_index(col, index_type=idx_meta["type"],
                                  unique=idx_meta["unique"], _save_meta=False)

        else:
            if schema is None:
                raise ValueError("No existe schema y no se proporcionó uno.")

            if primary_key and primary_key not in schema:
                raise ValueError(f"Primary key '{primary_key}' no existe en el schema.")

            self.schema = schema
            self.primary_key = primary_key

            # Guardar en formato nuevo
            self._save_schema()

            # Crear PageManager
            record_format = self._build_struct_format(self.schema)
            self.pm = PageManager(self.table_name, record_format)

            # Auto-crear indice unico sobre la primary key
            if primary_key:
                self.create_index(primary_key, index_type="bplus", unique=True)

    # ------------------------
    # SCHEMA -> STRUCT
    # ------------------------
    def _build_struct_format(self, schema):
        fmt = ""

        for col, col_type in schema.items():
            if col_type.startswith("char"):
                size = int(col_type.split("(")[1].split(")")[0])
                fmt += f"{size}s"
            else:
                fmt += self.TYPE_MAP[col_type]

        return fmt

    def _col_index(self, column):
        """Retorna la posicion numerica de una columna en el schema."""
        return list(self.schema.keys()).index(column)

    def _col_key_format(self, column):
        """Retorna el formato struct de una columna (para el indice)."""
        col_type = self.schema[column]
        if col_type.startswith("char"):
            size = int(col_type.split("(")[1].split(")")[0])
            return f"{size}s"
        return self.TYPE_MAP[col_type]

    def _clean_record(self, rec):
        """Convierte bytes a str (sin null padding) en columnas char."""
        if rec is None:
            return None
        values = list(rec)
        for i, col in enumerate(self.schema):
            if self.schema[col].startswith("char") and isinstance(values[i], bytes):
                values[i] = values[i].rstrip(b"\x00").decode("utf-8")
        return tuple(values)

    # ================================================================ #
    #  METRICS                                                            #
    # ================================================================ #

    def _reset_all_stats(self):
        """Resetea contadores de I/O del heap y todos los indices."""
        if self.pm:
            self.pm.reset_stats()
        for info in self.indexes.values():
            info["index"].reset_stats()

    def _collect_metrics(self, elapsed_ms):
        """Recolecta metricas de I/O de heap + indices + tiempo."""
        heap_reads = self.pm.disk_reads if self.pm else 0
        heap_writes = self.pm.disk_writes if self.pm else 0

        index_reads = 0
        index_writes = 0
        for info in self.indexes.values():
            idx = info["index"]
            index_reads += idx.disk_reads
            index_writes += idx.disk_writes

        return {
            "time_ms": round(elapsed_ms, 3),
            "heap_reads": heap_reads,
            "heap_writes": heap_writes,
            "index_reads": index_reads,
            "index_writes": index_writes,
            "total_reads": heap_reads + index_reads,
            "total_writes": heap_writes + index_writes,
        }

    # ================================================================ #
    #  SCHEMA PERSISTENCE                                               #
    # ================================================================ #

    def _save_schema(self):
        """Guarda columns + primary_key + indexes en el JSON."""
        indexes_meta = []
        for idx_key, info in self.indexes.items():
            col = list(idx_key) if isinstance(idx_key, tuple) else idx_key
            indexes_meta.append({
                "column": col,
                "type": info["type"],
                "unique": info["unique"],
            })

        self.sm.schema = {
            "columns": self.schema,
            "primary_key": self.primary_key,
            "indexes": indexes_meta,
            "point_columns": {k: list(v) for k, v in self.point_columns.items()},
        }
        self.sm.create_schema()

    # ================================================================ #
    #  INDICES                                                          #
    # ================================================================ #

    def create_index(self, column, index_type="bplus", unique=False, _save_meta=True):
        """
        Crea un indice sobre una columna (o par de columnas para rtree).

        Args:
            column: Nombre de la columna (str) o tupla (col_x, col_y) para rtree.
            index_type: Tipo de indice ("bplus", "rtree", "sequential", "hash").
            unique: Si True, no permite claves duplicadas (solo bplus).

        Retorna el indice creado.
        """
        if index_type not in self.INDEX_TYPES:
            raise ValueError(f"Tipo de indice '{index_type}' no soportado. "
                             f"Opciones: {self.INDEX_TYPES}")

        # ---- R-Tree: indice espacial 2D ----
        if index_type == "rtree":
            if not isinstance(column, (tuple, list)) or len(column) != 2:
                raise ValueError("R-Tree requiere 2 columnas: (col_x, col_y)")

            col_x, col_y = column
            for c in (col_x, col_y):
                if c not in self.schema:
                    raise ValueError(f"Columna '{c}' no existe en el schema.")

            idx_key = (col_x, col_y)
            if idx_key in self.indexes:
                raise ValueError(f"Ya existe un indice sobre {idx_key}.")

            index_file = f"{self.table_name}_{col_x}_{col_y}.idx"
            idx = RTree(index_file)

            # Indexar datos existentes
            self._build_rtree_index(col_x, col_y, idx)

            self.indexes[idx_key] = {
                "type": "rtree",
                "index": idx,
                "unique": False,
            }

            if _save_meta:
                self._save_schema()
            return idx

        # ---- B+Tree y otros indices 1D ----
        if column not in self.schema:
            raise ValueError(f"Columna '{column}' no existe en el schema.")

        if column in self.indexes:
            raise ValueError(f"Ya existe un indice sobre '{column}'.")

        index_file = f"{self.table_name}_{column}.idx"
        key_format = self._col_key_format(column)

        if index_type == "bplus":
            idx = BPlusTree(index_file, key_format=key_format, unique=unique)
        else:
            raise NotImplementedError(f"Indice '{index_type}' aun no implementado.")

        # Si la tabla ya tiene datos, indexar los registros existentes
        self._build_index(column, idx)

        self.indexes[column] = {
            "type": index_type,
            "index": idx,
            "unique": unique,
        }

        if _save_meta:
            self._save_schema()
        return idx

    def _build_index(self, column, idx):
        """Recorre el heap y agrega todas las entradas existentes al indice (B+Tree)."""
        col_pos = self._col_index(column)

        for p in range(self.pm.num_pages()):
            for s in range(self.pm.records_per_page()):
                rec = self.pm.read_record(p, s)
                if rec:
                    key = rec[col_pos]
                    idx.add(key, (p, s))

    def _build_rtree_index(self, col_x, col_y, idx):
        """Recorre el heap y agrega todas las entradas existentes al R-Tree."""
        x_pos = self._col_index(col_x)
        y_pos = self._col_index(col_y)

        for p in range(self.pm.num_pages()):
            for s in range(self.pm.records_per_page()):
                rec = self.pm.read_record(p, s)
                if rec:
                    idx.add(float(rec[x_pos]), float(rec[y_pos]), (p, s))

    def drop_index(self, column):
        """Elimina un indice. column puede ser str o tuple para rtree."""
        if column not in self.indexes:
            raise ValueError(f"No existe indice sobre '{column}'.")
        del self.indexes[column]
        self._save_schema()

    def has_index(self, column):
        return column in self.indexes

    # ================================================================ #
    #  INSERT                                                           #
    # ================================================================ #

    def insert(self, record_dict, metrics=False):
        self._reset_all_stats()
        t0 = time.perf_counter()

        values = []

        for col in self.schema:
            val = record_dict[col]
            if isinstance(val, str):
                val = val.encode("utf-8")
            values.append(val)

        # Insertar en heap
        rid = self.pm.add_record(tuple(values))

        # Actualizar todos los indices
        for idx_key, info in self.indexes.items():
            if info["type"] == "rtree":
                col_x, col_y = idx_key
                info["index"].add(float(record_dict[col_x]), float(record_dict[col_y]), rid)
            else:
                key = record_dict[idx_key]
                if isinstance(key, str):
                    key = key.encode("utf-8")
                info["index"].add(key, rid)

        elapsed = (time.perf_counter() - t0) * 1000
        if metrics:
            return rid, self._collect_metrics(elapsed)
        return rid

    # ================================================================ #
    #  SELECT                                                           #
    # ================================================================ #

    def select_all(self, metrics=False):
        """Full scan — retorna todos los registros."""
        self._reset_all_stats()
        t0 = time.perf_counter()

        results = []

        for p in range(self.pm.num_pages()):
            for s in range(self.pm.records_per_page()):
                rec = self.pm.read_record(p, s)
                if rec:
                    results.append(self._clean_record(rec))

        elapsed = (time.perf_counter() - t0) * 1000
        if metrics:
            return results, self._collect_metrics(elapsed)
        return results

    def select(self, column, value, metrics=False):
        """
        Busca registros donde column == value.
        Si hay indice, lo usa. Si no, hace full scan.
        """
        self._reset_all_stats()
        t0 = time.perf_counter()

        if isinstance(value, str):
            value_key = value.encode("utf-8")
        else:
            value_key = value

        # Ruta con indice
        if column in self.indexes:
            idx = self.indexes[column]["index"]
            unique = self.indexes[column]["unique"]

            if unique:
                rid = idx.search(value_key)
                if rid is None:
                    results = []
                else:
                    rec = self.pm.read_record(rid[0], rid[1])
                    results = [self._clean_record(rec)] if rec else []
            else:
                rids = idx.search_all(value_key)
                results = []
                for page, slot in rids:
                    rec = self.pm.read_record(page, slot)
                    if rec:
                        results.append(self._clean_record(rec))
        else:
            # Ruta sin indice: full scan
            col_pos = self._col_index(column)
            results = []

            for p in range(self.pm.num_pages()):
                for s in range(self.pm.records_per_page()):
                    rec = self.pm.read_record(p, s)
                    if rec and rec[col_pos] == value_key:
                        results.append(self._clean_record(rec))

        elapsed = (time.perf_counter() - t0) * 1000
        if metrics:
            return results, self._collect_metrics(elapsed)
        return results

    def select_range(self, column, begin, end, metrics=False):
        """
        Busca registros donde begin <= column <= end.
        Si hay indice, lo usa. Si no, hace full scan.
        """
        self._reset_all_stats()
        t0 = time.perf_counter()

        if isinstance(begin, str):
            begin = begin.encode("utf-8")
        if isinstance(end, str):
            end = end.encode("utf-8")

        # Ruta con indice
        if column in self.indexes:
            idx = self.indexes[column]["index"]
            rids = idx.range_search(begin, end)
            results = []
            for page, slot in rids:
                rec = self.pm.read_record(page, slot)
                if rec:
                    results.append(self._clean_record(rec))
        else:
            # Ruta sin indice: full scan
            col_pos = self._col_index(column)
            results = []

            for p in range(self.pm.num_pages()):
                for s in range(self.pm.records_per_page()):
                    rec = self.pm.read_record(p, s)
                    if rec and begin <= rec[col_pos] <= end:
                        results.append(self._clean_record(rec))

        elapsed = (time.perf_counter() - t0) * 1000
        if metrics:
            return results, self._collect_metrics(elapsed)
        return results

    # ================================================================ #
    #  DELETE                                                           #
    # ================================================================ #

    def delete(self, column, value, metrics=False):
        """
        Elimina registros donde column == value.
        Si hay indice, lo usa. Si no, hace full scan.
        Actualiza todos los indices afectados.
        """
        self._reset_all_stats()
        t0 = time.perf_counter()

        if isinstance(value, str):
            value_key = value.encode("utf-8")
        else:
            value_key = value

        deleted = 0

        # Encontrar los RIDs a eliminar
        if column in self.indexes:
            idx = self.indexes[column]["index"]
            unique = self.indexes[column]["unique"]

            if unique:
                rid = idx.search(value_key)
                rids_to_delete = [rid] if rid else []
            else:
                rids_to_delete = idx.search_all(value_key)
        else:
            # Full scan para encontrar RIDs
            col_pos = self._col_index(column)
            rids_to_delete = []

            for p in range(self.pm.num_pages()):
                for s in range(self.pm.records_per_page()):
                    rec = self.pm.read_record(p, s)
                    if rec and rec[col_pos] == value_key:
                        rids_to_delete.append((p, s))

        # Eliminar cada registro
        for page, slot in rids_to_delete:
            rec = self.pm.read_record(page, slot)
            if rec is None:
                continue

            # Eliminar del heap
            self.pm.delete_record(page, slot)

            # Eliminar de todos los indices
            for idx_key, info in self.indexes.items():
                if info["type"] == "rtree":
                    col_x, col_y = idx_key
                    x_pos = self._col_index(col_x)
                    y_pos = self._col_index(col_y)
                    info["index"].remove(float(rec[x_pos]), float(rec[y_pos]),
                                         rid=(page, slot))
                else:
                    col_pos = self._col_index(idx_key)
                    key = rec[col_pos]
                    info["index"].remove(key, value=(page, slot))

            deleted += 1

        elapsed = (time.perf_counter() - t0) * 1000
        if metrics:
            return deleted, self._collect_metrics(elapsed)
        return deleted

    # ================================================================ #
    #  SPATIAL QUERIES (R-Tree)                                         #
    # ================================================================ #

    def _get_rtree(self, col_x, col_y):
        """Obtiene el indice R-Tree para (col_x, col_y)."""
        idx_key = (col_x, col_y)
        if idx_key not in self.indexes or self.indexes[idx_key]["type"] != "rtree":
            raise ValueError(f"No existe indice R-Tree sobre ({col_x}, {col_y}).")
        return self.indexes[idx_key]["index"]

    def _fetch_records(self, rtree_results):
        """Convierte resultados del R-Tree (x, y, rid, dist) a registros completos."""
        records = []
        for x, y, rid, dist in rtree_results:
            rec = self.pm.read_record(rid[0], rid[1])
            if rec:
                records.append(self._clean_record(rec))
        return records

    def select_radius(self, col_x, col_y, cx, cy, radius, limit=0, offset=0, metrics=False):
        """
        Busca registros dentro de distancia `radius` desde (cx, cy).
        Requiere indice R-Tree sobre (col_x, col_y).
        """
        self._reset_all_stats()
        t0 = time.perf_counter()

        idx = self._get_rtree(col_x, col_y)
        results = idx.radius_search(cx, cy, radius, limit=limit, offset=offset)
        records = self._fetch_records(results)

        elapsed = (time.perf_counter() - t0) * 1000
        if metrics:
            return records, self._collect_metrics(elapsed)
        return records

    def select_knn(self, col_x, col_y, qx, qy, k, limit=0, offset=0, metrics=False):
        """
        Busca los k registros mas cercanos a (qx, qy).
        Requiere indice R-Tree sobre (col_x, col_y).
        """
        self._reset_all_stats()
        t0 = time.perf_counter()

        idx = self._get_rtree(col_x, col_y)
        results = idx.knn_search(qx, qy, k, limit=limit, offset=offset)
        records = self._fetch_records(results)

        elapsed = (time.perf_counter() - t0) * 1000
        if metrics:
            return records, self._collect_metrics(elapsed)
        return records

    def select_radius_json(self, col_x, col_y, cx, cy, radius, limit=0, offset=0):
        """Busqueda circular con JSON para visualizacion frontend."""
        self._reset_all_stats()
        t0 = time.perf_counter()

        idx = self._get_rtree(col_x, col_y)
        result = idx.radius_search_json(cx, cy, radius, limit=limit, offset=offset)

        elapsed = (time.perf_counter() - t0) * 1000
        result["metrics"] = self._collect_metrics(elapsed)
        return result

    def select_knn_json(self, col_x, col_y, qx, qy, k, limit=0, offset=0):
        """k-NN con JSON para visualizacion frontend."""
        self._reset_all_stats()
        t0 = time.perf_counter()

        idx = self._get_rtree(col_x, col_y)
        result = idx.knn_search_json(qx, qy, k, limit=limit, offset=offset)

        elapsed = (time.perf_counter() - t0) * 1000
        result["metrics"] = self._collect_metrics(elapsed)
        return result
