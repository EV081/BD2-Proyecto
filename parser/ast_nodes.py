"""
ast.py — Nodos del AST para el parser SQL del proyecto BD2.

Cada clase corresponde a una producción de la gramática EBNF y expone:
  - accept(visitor) : delega en el método visit_* correspondiente del visitor
  - to_dict()       : devuelve el mismo dict que producía el parser original
                      (permite seguir generando el JSON de salida sin cambios)
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visitor import Visitor


# ---------------------------------------------------------------------------
# Nodos de condición WHERE
# ---------------------------------------------------------------------------

class ComparisonCond:
    """Id RelOp Value"""
    def __init__(self, left: str, operator: str, right):
        self.left = left
        self.operator = operator
        self.right = right

    def accept(self, visitor: "Visitor"):
        return visitor.visit_comparison_cond(self)

    def to_dict(self):
        return {
            "type": "comparison",
            "left": self.left,
            "operator": self.operator,
            "right": self.right,
        }


class BetweenCond:
    """Id BETWEEN Value AND Value"""
    def __init__(self, left: str, lower, upper):
        self.left = left
        self.lower = lower
        self.upper = upper

    def accept(self, visitor: "Visitor"):
        return visitor.visit_between_cond(self)

    def to_dict(self):
        return {
            "type": "between",
            "left": self.left,
            "lower": self.lower,
            "upper": self.upper,
        }


class SpatialPointCond:
    """POINT ( Number , Number ) , ( RADIUS Number | K Number )"""
    def __init__(self, x: float, y: float, search_type: str, search_value):
        self.x = x
        self.y = y
        self.search_type = search_type   # "radius" | "k"
        self.search_value = search_value

    def accept(self, visitor: "Visitor"):
        return visitor.visit_spatial_point_cond(self)

    def to_dict(self):
        return {
            "type": "spatial_point",
            "x": self.x,
            "y": self.y,
            "search_type": self.search_type,
            "search_value": self.search_value,
        }


class InSpatialCond:
    """Id IN ( SpatialCond )"""
    def __init__(self, left: str, spatial_condition: SpatialPointCond):
        self.left = left
        self.spatial_condition = spatial_condition

    def accept(self, visitor: "Visitor"):
        return visitor.visit_in_spatial_cond(self)

    def to_dict(self):
        return {
            "type": "in_spatial",
            "left": self.left,
            "spatial_condition": self.spatial_condition.to_dict(),
        }


# ---------------------------------------------------------------------------
# Nodo auxiliar: definición de columna
# ---------------------------------------------------------------------------

class ColDef:
    """Id Type [ INDEX IndexTech ]"""
    def __init__(self, name: str, data_type: str, index: str | None):
        self.name = name
        self.data_type = data_type
        self.index = index          # None si no tiene índice

    def to_dict(self):
        return {
            "name": self.name,
            "data_type": self.data_type,
            "index": self.index,
        }


# ---------------------------------------------------------------------------
# Nodos de sentencia
# ---------------------------------------------------------------------------

class CreateTableStmt:
    """CREATE TABLE Id ( ColDef { , ColDef }* ) [ FROM FILE Path ]"""
    def __init__(self, name: str, columns: list[ColDef], file_path: str | None):
        self.name = name
        self.columns = columns
        self.file_path = file_path

    def accept(self, visitor: "Visitor"):
        return visitor.visit_create_table(self)

    def to_dict(self):
        return {
            "type": "create_table",
            "name": self.name,
            "columns": [c.to_dict() for c in self.columns],
            "file": self.file_path,
        }


class SelectStmt:
    """SELECT Cols FROM Id [ WHERE Condition ]"""
    def __init__(self, columns: list[str], table: str, where=None):
        self.columns = columns
        self.table = table
        self.where = where   # None | ComparisonCond | BetweenCond | InSpatialCond

    def accept(self, visitor: "Visitor"):
        return visitor.visit_select(self)

    def to_dict(self):
        return {
            "type": "select",
            "columns": self.columns,
            "table": self.table,
            "where": self.where.to_dict() if self.where is not None else None,
        }


class InsertStmt:
    """INSERT INTO Id VALUES ( Value { , Value }* )"""
    def __init__(self, table: str, values: list):
        self.table = table
        self.values = values

    def accept(self, visitor: "Visitor"):
        return visitor.visit_insert(self)

    def to_dict(self):
        return {
            "type": "insert",
            "table": self.table,
            "values": self.values,
        }


class DeleteStmt:
    """DELETE FROM Id WHERE Id RelOp Value"""
    def __init__(self, table: str, where: ComparisonCond):
        self.table = table
        self.where = where

    def accept(self, visitor: "Visitor"):
        return visitor.visit_delete(self)

    def to_dict(self):
        return {
            "type": "delete",
            "table": self.table,
            "where": self.where.to_dict(),
        }
