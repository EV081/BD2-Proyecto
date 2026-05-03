"""
DataBase Manager
"""

from dbms.utils.pagemanager import PageManager
from dbms.utils.schema import SchemaManager


class DataBase:

    PAGE_SIZE = 4096

    TYPE_MAP = {
        "int": "i",
        "float": "f",
        "char": "s"   # ojo: requiere tamaño
    }

    def __init__(self, table_name, schema=None):
        self.table_name = table_name
        self.sm = SchemaManager(table_name, schema=schema)
        self.pm = None
        self.schema = None

        self._load_or_create(schema)

    # ------------------------
    # INIT
    # ------------------------
    def _load_or_create(self, schema):
        # Caso 1: ya existe schema -> cargar
        if self.sm.schema_exists():
            existing = self.sm.get_schema()

            if schema is not None and schema != existing:
                raise ValueError(
                    "El schema ya existe. No se puede modificar."
                )
            
            self.schema = existing

        # Caso 2: no existe -> crear
        else:
            if schema is None:
                raise ValueError("No existe schema y no se proporcionó uno.")
            
            self.sm.schema = schema
            self.sm.create_schema()
            self.schema = schema

        # Crear PageManager
        record_format = self._build_struct_format(self.schema)
        self.pm = PageManager(self.table_name, record_format)

    # ------------------------
    # SCHEMA -> STRUCT
    # ------------------------
    def _build_struct_format(self, schema):
        fmt = ""

        for col, col_type in schema.items():
            if col_type.startswith("char"):
                # ejemplo: char(10)
                size = int(col_type.split("(")[1].split(")")[0])
                fmt += f"{size}s"
            else:
                fmt += self.TYPE_MAP[col_type]

        return fmt

    # ------------------------
    # INSERT
    # ------------------------
    def insert(self, record_dict):
        values = []

        for col in self.schema:
            val = record_dict[col]

            # strings -> bytes
            if isinstance(val, str):
                val = val.encode("utf-8")

            values.append(val)

        return self.pm.add_record(tuple(values))

    # ------------------------
    # SELECT (full scan por ahora)
    # ------------------------
    def select_all(self):
        results = []

        for p in range(self.pm.num_pages()):
            for s in range(self.pm.records_per_page()):
                rec = self.pm.read_record(p, s)
                if rec:
                    results.append(rec)

        return results

    # ------------------------
    # DELETE (scan simple)
    # ------------------------
    def delete(self, column, value):
        col_index = list(self.schema.keys()).index(column)

        for p in range(self.pm.num_pages()):
            for s in range(self.pm.records_per_page()):
                rec = self.pm.read_record(p, s)

                if rec and rec[col_index] == value:
                    self.pm.delete_record(p, s)