"""
Patrón Visitor para el parser SQL

Estructura

  Visitor (ABC)           -> interfaz base
  TraceVisitor(Visitor)   -> imprime SQL + descripcion de operaciones (debug/testing)

DBVisitor (en db_visitor.py) es el visitor que ejecuta contra la BD.
"""

from abc import ABC, abstractmethod
from .ast_nodes import (
    CreateTableStmt, SelectStmt, InsertStmt, DeleteStmt,
    ComparisonCond, BetweenCond, SpatialPointCond, InSpatialCond,
)


# ---------------------------------------------------------------------------
# Interfaz Visitor (clase abstracta)
# ---------------------------------------------------------------------------

class Visitor(ABC):
    """Interfaz base del visitor — un método por cada nodo del AST."""

    @abstractmethod
    def visit_create_table(self, node: CreateTableStmt):
        ...

    @abstractmethod
    def visit_select(self, node: SelectStmt):
        ...

    @abstractmethod
    def visit_insert(self, node: InsertStmt):
        ...

    @abstractmethod
    def visit_delete(self, node: DeleteStmt):
        ...

    @abstractmethod
    def visit_comparison_cond(self, node: ComparisonCond):
        ...

    @abstractmethod
    def visit_between_cond(self, node: BetweenCond):
        ...

    @abstractmethod
    def visit_spatial_point_cond(self, node: SpatialPointCond):
        ...

    @abstractmethod
    def visit_in_spatial_cond(self, node: InSpatialCond):
        ...


# ---------------------------------------------------------------------------
# TraceVisitor — traza de debug: SQL reconstruido + descripcion de operacion
# ---------------------------------------------------------------------------

class TraceVisitor(Visitor):
    """Imprime el SQL original y la descripcion de la operacion.

    Util para debugging y testing: muestra que se va a ejecutar
    sin tocar la base de datos.
    """

    def visit_create_table(self, node: CreateTableStmt):
        # SQL
        cols = []
        for c in node.columns:
            part = f"{c.name} {c.data_type}"
            if c.is_primary_key:
                part += " PRIMARY KEY"
            if c.index:
                part += f" INDEX {c.index}"
            cols.append(part)
        stmt = f"CREATE TABLE {node.name} ({', '.join(cols)})"
        if node.file_path:
            stmt += f" FROM FILE \"{node.file_path}\""
        print(f"[SQL]  {stmt}")

        # Traza
        cols_info = ", ".join(
            f"{c.name}:{c.data_type}"
            + (" PK" if c.is_primary_key else "")
            + (f"[{c.index}]" if c.index else "")
            for c in node.columns
        )
        file_info = f", cargando desde '{node.file_path}'" if node.file_path else ""
        print(f"[EXEC] Crear tabla '{node.name}' con columnas [{cols_info}]{file_info}")

    def visit_select(self, node: SelectStmt):
        cols = ", ".join(node.columns)
        # SQL
        stmt = f"SELECT {cols} FROM {node.table}"
        if node.where is not None:
            stmt += f" WHERE {self._fmt_sql(node.where)}"
        print(f"[SQL]  {stmt}")

        # Traza
        if node.where is None:
            print(f"[EXEC] Buscar todos los registros de '{node.table}' -> columnas [{cols}]")
        else:
            print(f"[EXEC] Buscar en '{node.table}' con condicion [{self._fmt_desc(node.where)}] -> columnas [{cols}]")

    def visit_insert(self, node: InsertStmt):
        def fmt_val(v):
            if isinstance(v, str):
                return f'"{v}"'
            return str(v)
        vals_sql = ", ".join(fmt_val(v) for v in node.values)
        vals_desc = ", ".join(repr(v) for v in node.values)
        print(f"[SQL]  INSERT INTO {node.table} VALUES ({vals_sql})")
        print(f"[EXEC] Insertar en '{node.table}' los valores ({vals_desc})")

    def visit_delete(self, node: DeleteStmt):
        print(f"[SQL]  DELETE FROM {node.table} WHERE {self._fmt_sql(node.where)}")
        print(f"[EXEC] Eliminar de '{node.table}' donde {self._fmt_desc(node.where)}")

    def visit_comparison_cond(self, node: ComparisonCond):
        print(f"[SQL]  {node.left} {node.operator} {node.right}")
        print(f"[EXEC] Condicion: {node.left} {node.operator} {node.right!r}")

    def visit_between_cond(self, node: BetweenCond):
        print(f"[SQL]  {node.left} BETWEEN {node.lower} AND {node.upper}")
        print(f"[EXEC] Condicion: {node.left} entre {node.lower!r} y {node.upper!r}")

    def visit_spatial_point_cond(self, node: SpatialPointCond):
        print(f"[SQL]  POINT({node.x}, {node.y}), {node.search_type.upper()} {node.search_value}")
        print(f"[EXEC] Condicion espacial: POINT({node.x}, {node.y}) {node.search_type.upper()} {node.search_value}")

    def visit_in_spatial_cond(self, node: InSpatialCond):
        sp = node.spatial_condition
        print(f"[SQL]  {node.left} IN (POINT({sp.x}, {sp.y}), {sp.search_type.upper()} {sp.search_value})")
        print(f"[EXEC] Condicion espacial: {node.left} IN POINT({sp.x}, {sp.y}) {sp.search_type.upper()} {sp.search_value}")

    # --- helpers ---

    def _fmt_sql(self, cond) -> str:
        """Formatea condicion como SQL."""
        if isinstance(cond, ComparisonCond):
            return f"{cond.left} {cond.operator} {cond.right}"
        if isinstance(cond, BetweenCond):
            return f"{cond.left} BETWEEN {cond.lower} AND {cond.upper}"
        if isinstance(cond, InSpatialCond):
            sp = cond.spatial_condition
            return (f"{cond.left} IN (POINT({sp.x}, {sp.y}),"
                    f" {sp.search_type.upper()} {sp.search_value})")
        return str(cond)

    def _fmt_desc(self, cond) -> str:
        """Formatea condicion como descripcion legible."""
        if isinstance(cond, ComparisonCond):
            return f"{cond.left} {cond.operator} {cond.right!r}"
        if isinstance(cond, BetweenCond):
            return f"{cond.left} BETWEEN {cond.lower!r} AND {cond.upper!r}"
        if isinstance(cond, InSpatialCond):
            sp = cond.spatial_condition
            return (f"{cond.left} IN POINT({sp.x}, {sp.y})"
                    f" {sp.search_type.upper()} {sp.search_value}")
        return str(cond)
