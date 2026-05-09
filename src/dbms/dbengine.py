"""
DataBase Manager
"""

import os
import time

from src.storage.heapfile import HeapFile
from src.storage.schema import SchemaManager
from src.structures.bplus import BPlusTree
from src.structures.rtree import RTree
from src.structures.sequentialfile import SequentialFile
from src.structures.Extendible_Hashing import ExtendibleHash


class DataBase:

    PAGE_SIZE = 4096

    TYPE_MAP = {
        "int": "i",
        "float": "f",
        "char": "s"   # ojo: requiere tamaño
    }

    # Tipos de indice soportados (extensible para rtree, sequential, hash)
    INDEX_TYPES = {"bplus", "rtree", "sequential", "hash"}

    def __init__(self, table_name, schema=None, primary_key=None,
                 pk_index_type="bplus", max_aux=None):
        self.table_name = table_name
        self.sm = SchemaManager(table_name)
        self.pm = None
        self.schema = None        # {"col": "type", ...}
        self.primary_key = None   # "col_name" o None
        self.record_count = 0
        self.pk_index_type = pk_index_type
        self._max_aux = max_aux

        # True cuando el almacenamiento primario es un SequentialFile clustered
        self.uses_clustered_seq = False

        # {column_or_tuple: {"type": "bplus"|"rtree"|..., "index": <instancia>, "unique": bool}}
        self.indexes = {}

        # Columnas POINT logicas: {"ubicacion": ("ubicacion_x", "ubicacion_y")}
        self.point_columns = {}

        self._load_or_create(schema, primary_key)

    @staticmethod
    def build_struct_format(schema):
        """Construye el formato struct a partir del schema de columnas."""
        fmt = ""

        for col, col_type in schema.items():
            if col_type.startswith("char"):
                size = int(col_type.split("(")[1].split(")")[0])
                fmt += f"{size}s"
            else:
                fmt += DataBase.TYPE_MAP[col_type]

        return fmt

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
            self.record_count = raw.get("record_count", 0) if isinstance(raw, dict) else 0
            self.point_columns = {
                k: tuple(v) for k, v in raw.get("point_columns", {}).items()
            }

            # Detectar si la PK usa sequential (clustered)
            saved_pk_type = raw.get("pk_index_type", "bplus") if isinstance(raw, dict) else "bplus"
            self.pk_index_type = saved_pk_type

            record_format = self.build_struct_format(self.schema)

            if saved_pk_type == "sequential" and saved_pk:
                self.uses_clustered_seq = True
                key_format = self._col_key_format(saved_pk)
                key_pos = self._col_index(saved_pk)
                self.pm = SequentialFile(
                    f"{self.table_name}_{saved_pk}.idx",
                    key_format=key_format,
                    record_format=record_format,
                    key_position=key_pos,
                    unique=True,
                )
                # Registrar el SF como indice de la PK
                self.indexes[saved_pk] = {
                    "type": "sequential",
                    "index": self.pm,
                    "unique": True,
                }
            else:
                self.pm = HeapFile(self.table_name, record_format)

            # Recrear indices secundarios desde la metadata guardada
            for idx_meta in indexes_meta:
                col = idx_meta["column"]
                if isinstance(col, list):
                    col = tuple(col)
                # Saltar el indice PK sequential (ya creado arriba como self.pm)
                if self.uses_clustered_seq and col == self.primary_key:
                    continue
                self.create_index(col, index_type=idx_meta["type"],
                                  unique=idx_meta["unique"], _save_meta=False)

            # Configurar callback de reconstruccion
            if self.uses_clustered_seq:
                self._setup_reconstruct_callback()

            if not isinstance(raw, dict) or "record_count" not in raw:
                self.record_count = self._count_all_records(record_format)
                self._save_schema()

        else:
            if schema is None:
                raise ValueError("No existe schema y no se proporcionó uno.")

            if primary_key and primary_key not in schema:
                raise ValueError(f"Primary key '{primary_key}' no existe en el schema.")

            self.schema = schema
            self.primary_key = primary_key
            self.record_count = 0

            # Guardar en formato nuevo
            self._save_schema()

            record_format = self.build_struct_format(self.schema)

            if self.pk_index_type == "sequential" and primary_key:
                self.uses_clustered_seq = True
                key_format = self._col_key_format(primary_key)
                key_pos = self._col_index(primary_key)
                self.pm = SequentialFile(
                    f"{self.table_name}_{primary_key}.idx",
                    key_format=key_format,
                    record_format=record_format,
                    key_position=key_pos,
                    unique=True,
                    max_aux=self._max_aux,
                )
                # Registrar como indice PK
                self.indexes[primary_key] = {
                    "type": "sequential",
                    "index": self.pm,
                    "unique": True,
                }
                self._save_schema()
            else:
                self.pm = HeapFile(self.table_name, record_format)
                # Auto-crear indice unico sobre la primary key
                if primary_key:
                    self.create_index(primary_key, index_type="bplus", unique=True)

    def _count_all_records(self, record_format):
        """Cuenta registros activos segun el modo de almacenamiento."""
        if self.uses_clustered_seq:
            count = 0
            for _ in self.pm.iter_all_records():
                count += 1
            return count
        else:
            return HeapFile.count_records(
                self.pm.path, record_format, self.PAGE_SIZE)

    # ------------------------
    # SCHEMA -> STRUCT
    # ------------------------
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
                values[i] = values[i].rstrip(b"\x00").decode("utf-8", errors="replace")
        return tuple(values)

    # ================================================================ #
    #  METRICS                                                            #
    # ================================================================ #

    def _reset_all_stats(self):
        """Resetea contadores de I/O del heap y todos los indices."""
        if self.pm:
            self.pm.reset_stats()
        for info in self.indexes.values():
            idx = info["index"]
            # En modo clustered, self.pm == self.indexes[pk]["index"], no resetear doble
            if idx is not self.pm:
                idx.reset_stats()

    def _collect_metrics(self, elapsed_ms):
        """Recolecta metricas de I/O de heap + indices + tiempo."""
        heap_reads = self.pm.disk_reads if self.pm else 0
        heap_writes = self.pm.disk_writes if self.pm else 0

        index_reads = 0
        index_writes = 0
        for info in self.indexes.values():
            idx = info["index"]
            if idx is self.pm:
                continue  # Ya contado como heap
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
            "pk_index_type": self.pk_index_type,
            "indexes": indexes_meta,
            "point_columns": {k: list(v) for k, v in self.point_columns.items()},
            "record_count": self.record_count,
        }
        self.sm.create_schema()

    # ================================================================ #
    #  RECONSTRUCTION CALLBACK                                          #
    # ================================================================ #

    def _setup_reconstruct_callback(self):
        """Configura callback para reconstruir indices secundarios
        cuando el SequentialFile hace reconstruct."""
        def on_reconstruct():
            for idx_key, info in self.indexes.items():
                if idx_key == self.primary_key:
                    continue  # Es el propio SequentialFile
                idx = info["index"]
                # Recrear el indice: borrar archivo y reinicializar
                if hasattr(idx, 'index_file') and os.path.exists(idx.index_file):
                    os.remove(idx.index_file)
                # Reinicializar
                if info["type"] == "rtree":
                    col_x, col_y = idx_key
                    new_idx = RTree(os.path.basename(idx.index_file))
                    self._build_rtree_index_from_storage(col_x, col_y, new_idx)
                    info["index"] = new_idx
                else:
                    key_format = self._col_key_format(idx_key)
                    if info["type"] == "bplus":
                        new_idx = BPlusTree(os.path.basename(idx.index_file),
                                            key_format=key_format,
                                            unique=info["unique"])
                    elif info["type"] == "hash":
                        new_idx = ExtendibleHash(os.path.basename(idx.index_file),
                                                 key_format=key_format,
                                                 unique=info["unique"])
                    else:
                        continue
                    self._build_index_from_storage(idx_key, new_idx)
                    info["index"] = new_idx

        self.pm.on_reconstruct = on_reconstruct

    def _build_index_from_storage(self, column, idx):
        """Construye un indice secundario iterando el almacenamiento primario."""
        col_pos = self._col_index(column)
        if self.uses_clustered_seq:
            for page_id, slot, rec in self.pm.iter_all_records():
                key = rec[col_pos]
                idx.add(key, (page_id, slot))
        else:
            for p in range(self.pm.num_pages()):
                for s in range(self.pm.records_per_page()):
                    rec = self.pm.read_record(p, s)
                    if rec:
                        idx.add(rec[col_pos], (p, s))

    def _build_rtree_index_from_storage(self, col_x, col_y, idx):
        """Construye un R-Tree iterando el almacenamiento primario."""
        x_pos = self._col_index(col_x)
        y_pos = self._col_index(col_y)
        if self.uses_clustered_seq:
            for page_id, slot, rec in self.pm.iter_all_records():
                idx.add(float(rec[x_pos]), float(rec[y_pos]), (page_id, slot))
        else:
            for p in range(self.pm.num_pages()):
                for s in range(self.pm.records_per_page()):
                    rec = self.pm.read_record(p, s)
                    if rec:
                        idx.add(float(rec[x_pos]), float(rec[y_pos]), (p, s))

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

        # Si es sequential y ya se uso como PK clustered, retornar el existente
        if index_type == "sequential" and self.uses_clustered_seq and column == self.primary_key:
            return self.indexes[self.primary_key]["index"]

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

            # Solo reconstruir si es un indice nuevo
            if _save_meta:
                self._build_rtree_index_from_storage(col_x, col_y, idx)

            self.indexes[idx_key] = {
                "type": "rtree",
                "index": idx,
                "unique": False,
            }

            if _save_meta:
                self._save_schema()
            return idx

        # ---- B+Tree, Sequential (secundario), Hash ----
        if column not in self.schema:
            raise ValueError(f"Columna '{column}' no existe en el schema.")

        if column in self.indexes:
            raise ValueError(f"Ya existe un indice sobre '{column}'.")

        index_file = f"{self.table_name}_{column}.idx"
        key_format = self._col_key_format(column)

        if index_type == "bplus":
            idx = BPlusTree(index_file, key_format=key_format, unique=unique)
        elif index_type == "sequential":
            # Sequential como indice secundario (no clustered)
            idx = SequentialFile(index_file, key_format=key_format, unique=unique)
        elif index_type == "hash":
            idx = ExtendibleHash(index_file, key_format=key_format, unique=unique)
        else:
            raise NotImplementedError(f"Indice '{index_type}' aun no implementado.")

        # Solo reconstruir el indice si es nuevo (no cuando se carga desde disco)
        if _save_meta:
            self._build_index_from_storage(column, idx)

        self.indexes[column] = {
            "type": index_type,
            "index": idx,
            "unique": unique,
        }

        if _save_meta:
            self._save_schema()
            # Si hay clustered seq, actualizar el callback con el nuevo indice
            if self.uses_clustered_seq:
                self._setup_reconstruct_callback()
        return idx

    # Mantener compatibilidad con codigo existente
    def _build_index(self, column, idx):
        self._build_index_from_storage(column, idx)

    def _build_rtree_index(self, col_x, col_y, idx):
        self._build_rtree_index_from_storage(col_x, col_y, idx)

    def drop_index(self, column):
        """Elimina un indice. column puede ser str o tuple para rtree."""
        if column not in self.indexes:
            raise ValueError(f"No existe indice sobre '{column}'.")

        # No permitir eliminar el indice PK clustered
        if self.uses_clustered_seq and column == self.primary_key:
            raise ValueError("No se puede eliminar el indice PK clustered (es el almacenamiento).")

        # Delete index file(s) from disk
        idx = self.indexes[column]["index"]
        for attr in ("index_file", "main_file", "aux_file"):
            path = getattr(idx, attr, None)
            if path and os.path.exists(path):
                os.remove(path)

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

        # Insertar en almacenamiento primario
        rid = self.pm.add_record(tuple(values))

        # Si hubo reconstruccion, los indices secundarios ya fueron rebuild
        # con TODOS los registros (incluyendo el recien insertado). No agregar doble.
        skip_secondary = (self.uses_clustered_seq and self.pm._just_reconstructed)
        if skip_secondary:
            self.pm._just_reconstructed = False
        else:
            # Actualizar indices secundarios (saltar PK si es clustered)
            for idx_key, info in self.indexes.items():
                if self.uses_clustered_seq and idx_key == self.primary_key:
                    continue  # Ya insertado en self.pm
                if info["type"] == "rtree":
                    col_x, col_y = idx_key
                    info["index"].add(float(record_dict[col_x]), float(record_dict[col_y]), rid)
                else:
                    key = record_dict[idx_key]
                    if isinstance(key, str):
                        key = key.encode("utf-8")
                    info["index"].add(key, rid)

        self.record_count += 1
        self._save_schema()

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

        if self.uses_clustered_seq:
            for _p, _s, rec in self.pm.iter_all_records():
                results.append(self._clean_record(rec))
        else:
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

            if self.uses_clustered_seq and column == self.primary_key:
                # Busqueda directa en el SequentialFile clustered
                rec = idx.search(value_key)
                results = [self._clean_record(rec)] if rec else []
            elif unique:
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

            if self.uses_clustered_seq:
                for _p, _s, rec in self.pm.iter_all_records():
                    if rec[col_pos] == value_key:
                        results.append(self._clean_record(rec))
            else:
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
        if column in self.indexes and self.indexes[column]["type"] != "hash":
            idx = self.indexes[column]["index"]

            if self.uses_clustered_seq and column == self.primary_key:
                # range_search en clustered retorna registros completos
                records = idx.range_search(begin, end)
                results = [self._clean_record(r) for r in records]
            else:
                rids = idx.range_search(begin, end)
                results = []
                for page, slot in rids:
                    rec = self.pm.read_record(page, slot)
                    if rec:
                        results.append(self._clean_record(rec))
        else:
            # Full scan (sin indice o indice hash)
            col_pos = self._col_index(column)
            results = []

            if self.uses_clustered_seq:
                for _p, _s, rec in self.pm.iter_all_records():
                    if begin <= rec[col_pos] <= end:
                        results.append(self._clean_record(rec))
            else:
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

        if self.uses_clustered_seq:
            deleted = self._delete_clustered(column, value_key)
        else:
            deleted = self._delete_heap(column, value_key)

        if deleted:
            self.record_count = max(0, self.record_count - deleted)
            self._save_schema()

        elapsed = (time.perf_counter() - t0) * 1000
        if metrics:
            return deleted, self._collect_metrics(elapsed)
        return deleted

    def _delete_heap(self, column, value_key):
        """Elimina registros del HeapFile (modo no-clustered)."""
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

        return deleted

    def _delete_clustered(self, column, value_key):
        """Elimina registros del SequentialFile clustered usando soft delete.
        Los slots no se desplazan, asi que los RIDs de indices secundarios
        permanecen validos. Se elimina de cada indice secundario individualmente."""
        deleted = 0

        if column == self.primary_key:
            # Buscar ubicacion y registro antes de eliminar
            loc = self.pm._find_location(value_key)
            if loc == (-1, -1):
                return 0
            rec = self.pm.read_record(loc[0], loc[1])
            if rec is None:
                return 0

            # Soft delete en el SF
            self.pm.delete_record(loc[0], loc[1])

            # Eliminar de cada indice secundario individualmente
            self._remove_from_secondary_indexes(rec, loc)
            deleted = 1

        elif column in self.indexes:
            idx = self.indexes[column]["index"]
            unique = self.indexes[column]["unique"]

            if unique:
                rid = idx.search(value_key)
                rids = [rid] if rid else []
            else:
                rids = list(idx.search_all(value_key))

            for page, slot in rids:
                rec = self.pm.read_record(page, slot)
                if rec is None:
                    continue

                # Soft delete en el SF
                self.pm.delete_record(page, slot)

                # Eliminar de cada indice secundario individualmente
                self._remove_from_secondary_indexes(rec, (page, slot))
                deleted += 1

        else:
            # Full scan
            col_pos = self._col_index(column)
            to_delete = []
            for _p, _s, rec in self.pm.iter_all_records():
                if rec[col_pos] == value_key:
                    to_delete.append((_p, _s, rec))

            for page, slot, rec in to_delete:
                self.pm.delete_record(page, slot)
                self._remove_from_secondary_indexes(rec, (page, slot))
                deleted += 1

        # NO rebuild: soft delete mantiene slots estables
        return deleted

    def _remove_from_secondary_indexes(self, rec, rid):
        """Elimina un registro de todos los indices secundarios por clave+RID."""
        for idx_key, info in self.indexes.items():
            if idx_key == self.primary_key:
                continue
            if info["type"] == "rtree":
                col_x, col_y = idx_key
                x_pos = self._col_index(col_x)
                y_pos = self._col_index(col_y)
                info["index"].remove(float(rec[x_pos]), float(rec[y_pos]),
                                     rid=rid)
            else:
                col_pos = self._col_index(idx_key)
                key = rec[col_pos]
                info["index"].remove(key, value=rid)

    def _rebuild_secondary_indexes(self):
        """Reconstruye todos los indices secundarios desde el almacenamiento."""
        for idx_key, info in self.indexes.items():
            if idx_key == self.primary_key:
                continue
            idx = info["index"]
            # Borrar y recrear
            if hasattr(idx, 'index_file') and os.path.exists(idx.index_file):
                os.remove(idx.index_file)
            if info["type"] == "rtree":
                col_x, col_y = idx_key
                new_idx = RTree(os.path.basename(idx.index_file))
                self._build_rtree_index_from_storage(col_x, col_y, new_idx)
                info["index"] = new_idx
            else:
                key_format = self._col_key_format(idx_key)
                if info["type"] == "bplus":
                    new_idx = BPlusTree(os.path.basename(idx.index_file),
                                        key_format=key_format,
                                        unique=info["unique"])
                elif info["type"] == "hash":
                    new_idx = ExtendibleHash(os.path.basename(idx.index_file),
                                             key_format=key_format,
                                             unique=info["unique"])
                else:
                    new_idx = SequentialFile(os.path.basename(idx.index_file),
                                             key_format=key_format,
                                             unique=info["unique"])
                self._build_index_from_storage(idx_key, new_idx)
                info["index"] = new_idx

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


def execute_sql(query, input_path="input.sql", output_dir=None, persist_ast=False):
    """Ejecuta el parser SQL desde la capa de utilidades del dbengine."""
    from src.parser.main import execute_parser
    from src.parser.scanner import Scanner

    scanner = Scanner(query)
    return execute_parser(scanner, input_path, output_dir, persist_ast=persist_ast)
