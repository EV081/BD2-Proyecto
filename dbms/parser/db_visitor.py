"""
DBVisitor — Ejecuta sentencias SQL sobre el motor de base de datos (dbengine).

Conecta el parser SQL con el DBMS:
  CREATE TABLE  → DataBase(...) + create_index(...)
  SELECT        → select / select_range / select_radius / select_knn
  INSERT        → insert
  DELETE        → delete
"""

import os
import csv
import time

from dbms.dbengine import DataBase
from .ast_nodes import (
    CreateTableStmt, SelectStmt, InsertStmt, DeleteStmt,
    ComparisonCond, BetweenCond, SpatialPointCond, InSpatialCond,
)
from .visitor import Visitor


# Mapeo de tipos del parser a tipos del dbengine
TYPE_MAP = {
    "INT":   "int",
    "FLOAT": "float",
}

# Mapeo de tecnicas de indexacion del parser al dbengine
INDEX_MAP = {
    "BTREE":      "bplus",
    "RTREE":      "rtree",
    "HASH":       "hash",
    "SEQUENTIAL": "sequential",
}


def _map_type(parser_type):
    """Convierte tipo del parser a tipo del dbengine."""
    upper = parser_type.upper()
    if upper in TYPE_MAP:
        return TYPE_MAP[upper]
    if upper.startswith("VARCHAR"):
        # VARCHAR(100) → char(100), VARCHAR → char(255)
        if "(" in parser_type:
            size = parser_type.split("(")[1].split(")")[0]
            return f"char({size})"
        return "char(255)"
    return parser_type.lower()


class DBVisitor(Visitor):

    def __init__(self):
        # Cache de tablas abiertas en la sesion
        self.tables = {}
        # Metricas de la ultima operacion
        self.last_metrics = None

    @staticmethod
    def _print_metrics(m):
        """Imprime metricas de I/O y tiempo."""
        print(f"  Metricas: {m['time_ms']:.3f} ms | "
              f"Reads: {m['total_reads']} (heap={m['heap_reads']}, idx={m['index_reads']}) | "
              f"Writes: {m['total_writes']} (heap={m['heap_writes']}, idx={m['index_writes']})")

    def _get_table(self, name):
        """Retorna la instancia DataBase para una tabla (carga si es necesario)."""
        if name not in self.tables:
            try:
                db = DataBase(name)
                self.tables[name] = db
            except ValueError:
                raise RuntimeError(f"La tabla '{name}' no existe.")
        return self.tables[name]

    def _col_names(self, db):
        """Retorna lista de nombres de columnas."""
        return list(db.schema.keys())

    def _format_results(self, db, records, columns=None):
        """Formatea registros para impresion."""
        col_names = self._col_names(db)

        # Filtrar columnas si se especificaron
        if columns and columns != ["*"]:
            col_indices = []
            for c in columns:
                if c in col_names:
                    col_indices.append(col_names.index(c))
                # Para columnas POINT logicas, incluir ambas fisicas
                elif c in db.point_columns:
                    cx, cy = db.point_columns[c]
                    col_indices.append(col_names.index(cx))
                    col_indices.append(col_names.index(cy))
            col_names = [col_names[i] for i in col_indices]
            records = [tuple(r[i] for i in col_indices) for r in records]

        return col_names, records

    # ================================================================ #
    #  CREATE TABLE                                                     #
    # ================================================================ #

    def visit_create_table(self, node: CreateTableStmt):
        schema = {}
        point_cols = {}       # logico → (col_x, col_y)
        indexes_to_create = []

        for col in node.columns:
            if col.data_type.upper() == "POINT":
                # POINT se expande a dos columnas float
                col_x = f"{col.name}_x"
                col_y = f"{col.name}_y"
                schema[col_x] = "float"
                schema[col_y] = "float"
                point_cols[col.name] = (col_x, col_y)

                if col.index:
                    idx_type = INDEX_MAP.get(col.index.upper(), col.index.lower())
                    indexes_to_create.append({
                        "column": (col_x, col_y),
                        "type": idx_type,
                        "unique": False,
                    })
            else:
                db_type = _map_type(col.data_type)
                schema[col.name] = db_type

                if col.index:
                    idx_type = INDEX_MAP.get(col.index.upper(), col.index.lower())
                    indexes_to_create.append({
                        "column": col.name,
                        "type": idx_type,
                        "unique": False,
                    })

        db = DataBase(node.name, schema=schema)
        db.point_columns = point_cols
        db._save_schema()

        # Crear indices
        for idx_info in indexes_to_create:
            db.create_index(idx_info["column"], index_type=idx_info["type"],
                            unique=idx_info["unique"])

        self.tables[node.name] = db

        col_info = ", ".join(
            f"{c.name} {c.data_type}" + (f" INDEX {c.index}" if c.index else "")
            for c in node.columns
        )
        print(f"Tabla '{node.name}' creada ({col_info})")

        # Cargar datos desde archivo CSV
        if node.file_path:
            self._load_from_file(db, node)

        return db

    def _load_from_file(self, db, node):
        """Carga datos desde un archivo CSV."""
        file_path = node.file_path

        # Buscar el archivo relativo al directorio del proyecto
        if not os.path.isabs(file_path):
            project_root = os.path.join(os.path.dirname(__file__), "..")
            file_path = os.path.join(project_root, file_path)

        if not os.path.exists(file_path):
            print(f"  Advertencia: archivo '{node.file_path}' no encontrado.")
            return

        col_names = self._col_names(db)
        point_cols = db.point_columns
        count = 0

        db._reset_all_stats()
        t0 = time.perf_counter()

        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)

            # Detectar header
            first_row = next(reader, None)
            if first_row is None:
                return

            # Si la primera fila parece ser un header, saltarla
            rows = []
            is_header = any(cell.strip().isalpha() for cell in first_row[:2])
            if not is_header:
                rows.append(first_row)

            for row in reader:
                rows.append(row)

            for row in rows:
                if len(row) != len(col_names):
                    continue
                record = {}
                for i, col in enumerate(col_names):
                    col_type = db.schema[col]
                    val = row[i].strip().strip('"').strip("'")
                    if col_type == "int":
                        record[col] = int(val)
                    elif col_type == "float":
                        record[col] = float(val)
                    else:
                        record[col] = val
                db.insert(record)
                count += 1

        elapsed = (time.perf_counter() - t0) * 1000
        m = db._collect_metrics(elapsed)
        print(f"  {count} registros cargados desde '{node.file_path}'")
        self._print_metrics(m)

    # ================================================================ #
    #  SELECT                                                           #
    # ================================================================ #

    def visit_select(self, node: SelectStmt):
        db = self._get_table(node.table)

        if node.where is None:
            records, m = db.select_all(metrics=True)
        else:
            records, m = node.where.accept(self._SelectExecutor(db))

        self.last_metrics = m
        col_names, records = self._format_results(db, records, node.columns)

        # Imprimir resultados
        print(f"Resultados ({len(records)} registros):")
        if records:
            print(f"  {col_names}")
            for r in records[:50]:
                print(f"  {r}")
            if len(records) > 50:
                print(f"  ... ({len(records) - 50} mas)")
        self._print_metrics(m)

        return {
            "columns": col_names,
            "rows": records,
        }

    class _SelectExecutor:
        """Ejecutor interno para condiciones WHERE de SELECT. Retorna (records, metrics)."""
        def __init__(self, db):
            self.db = db

        def visit_comparison_cond(self, node):
            if node.operator == "=":
                return self.db.select(node.left, node.right, metrics=True)
            # Para otros operadores: full scan + filtro
            col_pos = list(self.db.schema.keys()).index(node.left)
            all_recs, m = self.db.select_all(metrics=True)
            filtered = [r for r in all_recs if self._compare(r[col_pos], node.operator, node.right)]
            return filtered, m

        def visit_between_cond(self, node):
            return self.db.select_range(node.left, node.lower, node.upper, metrics=True)

        def visit_in_spatial_cond(self, node):
            sp = node.spatial_condition
            col_name = node.left

            # Resolver columna POINT a columnas fisicas
            if col_name in self.db.point_columns:
                col_x, col_y = self.db.point_columns[col_name]
            else:
                col_x, col_y = col_name, col_name

            if sp.search_type == "radius":
                return self.db.select_radius(col_x, col_y, sp.x, sp.y, sp.search_value, metrics=True)
            elif sp.search_type == "k":
                return self.db.select_knn(col_x, col_y, sp.x, sp.y, sp.search_value, metrics=True)

        def visit_spatial_point_cond(self, node):
            return [], {"time_ms": 0, "heap_reads": 0, "heap_writes": 0,
                        "index_reads": 0, "index_writes": 0,
                        "total_reads": 0, "total_writes": 0}

        @staticmethod
        def _compare(val, op, target):
            # Normalizar tipos para comparacion
            if isinstance(val, bytes):
                val = val.rstrip(b"\x00").decode("utf-8")
            if isinstance(target, str) and isinstance(val, str):
                pass
            elif isinstance(val, (int, float)) and isinstance(target, (int, float)):
                pass
            else:
                return False
            ops = {
                "=": lambda a, b: a == b,
                "!=": lambda a, b: a != b,
                "<": lambda a, b: a < b,
                ">": lambda a, b: a > b,
                "<=": lambda a, b: a <= b,
                ">=": lambda a, b: a >= b,
            }
            return ops.get(op, lambda a, b: False)(val, target)

    # ================================================================ #
    #  INSERT                                                           #
    # ================================================================ #

    def visit_insert(self, node: InsertStmt):
        db = self._get_table(node.table)
        col_names = self._col_names(db)

        if len(node.values) != len(col_names):
            raise RuntimeError(
                f"INSERT: se esperaban {len(col_names)} valores, "
                f"se recibieron {len(node.values)}"
            )

        record = {}
        for col, val in zip(col_names, node.values):
            col_type = db.schema[col]
            if col_type == "int":
                record[col] = int(val)
            elif col_type == "float":
                record[col] = float(val)
            else:
                record[col] = str(val)

        rid, m = db.insert(record, metrics=True)
        self.last_metrics = m
        print(f"Insertado en '{node.table}': {tuple(node.values)} -> RID {rid}")
        self._print_metrics(m)
        return rid

    # ================================================================ #
    #  DELETE                                                           #
    # ================================================================ #

    def visit_delete(self, node: DeleteStmt):
        db = self._get_table(node.table)
        cond = node.where

        if cond.operator != "=":
            raise RuntimeError(
                f"DELETE solo soporta operador '=', se recibio '{cond.operator}'"
            )

        deleted, m = db.delete(cond.left, cond.right, metrics=True)
        self.last_metrics = m
        print(f"Eliminados {deleted} registros de '{node.table}' donde {cond.left} = {cond.right!r}")
        self._print_metrics(m)
        return deleted

    # ================================================================ #
    #  Condition visitors (dispatch directo — no usados en SELECT)      #
    # ================================================================ #

    def visit_comparison_cond(self, node):
        pass

    def visit_between_cond(self, node):
        pass

    def visit_spatial_point_cond(self, node):
        pass

    def visit_in_spatial_cond(self, node):
        pass
