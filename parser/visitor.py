"""
Patrón Visitor para el parser SQL

Estructura

  Visitor (ABC)           -> interfaz base
  PrintVisitor(Visitor)   -> imprime el SQL reconstruido
  ExecuteVisitor(Visitor) -> gatilla la ejecucion en la BD
"""

from abc import ABC, abstractmethod
from ast_nodes import (
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
# PrintVisitor — muestra la sentencia SQL original
# ---------------------------------------------------------------------------

class PrintVisitor(Visitor):

    def visit_create_table(self, node: CreateTableStmt):
        cols = []
        for c in node.columns:
            part = f"{c.name} {c.data_type}"
            if c.index:
                part += f" INDEX {c.index}"
            cols.append(part)
        stmt = f"CREATE TABLE {node.name} ({', '.join(cols)})"
        if node.file_path:
            stmt += f" FROM FILE \"{node.file_path}\""
        print(stmt)

    def visit_select(self, node: SelectStmt):
        cols = ", ".join(node.columns)
        stmt = f"SELECT {cols} FROM {node.table}"
        if node.where is not None:
            stmt += f" WHERE {self._fmt_cond(node.where)}"
        print(stmt)

    def visit_insert(self, node: InsertStmt):
        def fmt_val(v):
            if isinstance(v, str):
                return f'"{v}"'
            return str(v)
        vals = ", ".join(fmt_val(v) for v in node.values)
        print(f"INSERT INTO {node.table} VALUES ({vals})")

    def visit_delete(self, node: DeleteStmt):
        print(f"DELETE FROM {node.table} WHERE {self._fmt_cond(node.where)}")

    def visit_comparison_cond(self, node: ComparisonCond):
        print(f"{node.left} {node.operator} {node.right}")

    def visit_between_cond(self, node: BetweenCond):
        print(f"{node.left} BETWEEN {node.lower} AND {node.upper}")

    def visit_spatial_point_cond(self, node: SpatialPointCond):
        print(f"POINT({node.x}, {node.y}), {node.search_type.upper()} {node.search_value}")

    def visit_in_spatial_cond(self, node: InSpatialCond):
        sp = node.spatial_condition
        print(f"{node.left} IN (POINT({sp.x}, {sp.y}), {sp.search_type.upper()} {sp.search_value})")

    def _fmt_cond(self, cond) -> str:
        if isinstance(cond, ComparisonCond):
            return f"{cond.left} {cond.operator} {cond.right}"
        if isinstance(cond, BetweenCond):
            return f"{cond.left} BETWEEN {cond.lower} AND {cond.upper}"
        if isinstance(cond, InSpatialCond):
            sp = cond.spatial_condition
            return (f"{cond.left} IN (POINT({sp.x}, {sp.y}),"
                    f" {sp.search_type.upper()} {sp.search_value})")
        return str(cond)


# ---------------------------------------------------------------------------
# ExecuteVisitor — stub de ejecución
# ---------------------------------------------------------------------------

class ExecuteVisitor(Visitor):

    def visit_create_table(self, node: CreateTableStmt):
        cols_info = ", ".join(
            f"{c.name}:{c.data_type}" + (f"[{c.index}]" if c.index else "")
            for c in node.columns
        )
        file_info = f", cargando desde '{node.file_path}'" if node.file_path else ""
        print(f"Crear tabla '{node.name}' con columnas [{cols_info}]{file_info}")

    def visit_select(self, node: SelectStmt):
        cols = ", ".join(node.columns)
        if node.where is None:
            print(f"Buscar todos los registros de '{node.table}' -> columnas [{cols}]")
        else:
            print(f"Buscar en '{node.table}' con condicion [{self._fmt_exec_cond(node.where)}] -> columnas [{cols}]")

    def visit_insert(self, node: InsertStmt):
        vals = ", ".join(repr(v) for v in node.values)
        print(f"Insertar en '{node.table}' los valores ({vals})")

    def visit_delete(self, node: DeleteStmt):
        print(f"Eliminar de '{node.table}' donde {self._fmt_exec_cond(node.where)}")

    # --- condiciones (para dispatch directo) ---

    def visit_comparison_cond(self, node: ComparisonCond):
        print(f"  Condicion: {node.left} {node.operator} {node.right!r}")

    def visit_between_cond(self, node: BetweenCond):
        print(f"  Condicion: {node.left} entre {node.lower!r} y {node.upper!r}")

    def visit_spatial_point_cond(self, node: SpatialPointCond):
        print(f"  Condicion espacial: POINT({node.x}, {node.y}) {node.search_type.upper()} {node.search_value}")

    def visit_in_spatial_cond(self, node: InSpatialCond):
        sp = node.spatial_condition
        print(f"  Condicion espacial: {node.left} IN POINT({sp.x}, {sp.y}) {sp.search_type.upper()} {sp.search_value}")

    def _fmt_exec_cond(self, cond) -> str:
        if isinstance(cond, ComparisonCond):
            return f"{cond.left} {cond.operator} {cond.right!r}"
        if isinstance(cond, BetweenCond):
            return f"{cond.left} BETWEEN {cond.lower!r} AND {cond.upper!r}"
        if isinstance(cond, InSpatialCond):
            sp = cond.spatial_condition
            return (f"{cond.left} IN POINT({sp.x}, {sp.y})"
                    f" {sp.search_type.upper()} {sp.search_value}")
        return str(cond)
