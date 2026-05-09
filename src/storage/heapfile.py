"""
HeapFile — Almacenamiento de registros sobre paginas.

Hereda de PageManager el I/O generico de paginas y agrega:
- Serializacion/deserializacion de registros con struct
- Deleted flag por slot (1 byte: 0=activo, 1=borrado)
- Free list para reutilizar slots borrados
- Insercion al final o en huecos libres

Cada pagina contiene N registros de tamanio fijo:
  [flag(1) + record_data(struct.size)] * records_per_page
"""

import os
import struct

from src.storage.pagemanager import PageManager


class HeapFile(PageManager):

    DB_FOLDER = "data"

    def __init__(self, table_name, record_format, page_size=4096):
        """
        Args:
            table_name: nombre de la tabla (se crea data/{table_name}.bin).
            record_format: formato struct de un registro (ej: "i30sf").
            page_size: tamanio de pagina en bytes.
        """
        path = os.path.join(self.DB_FOLDER, table_name + ".bin")
        super().__init__(path, page_size)

        # Record layout
        self.struct = struct.Struct(record_format)
        self.record_size = self.struct.size + 1   # +1 deleted flag

        # Free list y puntero al final
        self.free_slots = []
        self.last_page = 0
        self.last_slot = 0

        # Reconstruir estado desde disco
        if os.path.getsize(self.path) > 0:
            self._init_state()

    # ------------------------------------------------------------------ #
    #  INIT                                                                #
    # ------------------------------------------------------------------ #

    def _init_state(self):
        """Recorre todas las paginas para construir free_slots y last_page/slot."""
        for p in range(self.num_pages()):
            page = self.read_page(p)
            for slot in range(self.records_per_page()):
                offset = slot * self.record_size
                if page[offset] == 1:
                    self.free_slots.append((p, slot))
                else:
                    if p > self.last_page or (p == self.last_page and slot >= self.last_slot):
                        self.last_page = p
                        self.last_slot = slot

    # ------------------------------------------------------------------ #
    #  UTIL                                                                #
    # ------------------------------------------------------------------ #

    def records_per_page(self):
        return self.page_size // self.record_size

    @staticmethod
    def count_records(path, record_format, page_size=4096):
        """Cuenta los registros activos de una tabla sin crear archivos nuevos."""
        if not os.path.exists(path):
            return 0

        struct_obj = struct.Struct(record_format)
        record_size = struct_obj.size + 1
        records_per_page = page_size // record_size

        if records_per_page <= 0:
            return 0

        count = 0
        with open(path, "rb") as f:
            while True:
                page = f.read(page_size)
                if not page:
                    break
                for slot in range(records_per_page):
                    offset = slot * record_size
                    if offset >= len(page):
                        break
                    if page[offset] == 0:
                        count += 1
        return count

    # ------------------------------------------------------------------ #
    #  RECORD I/O                                                          #
    # ------------------------------------------------------------------ #

    def create_empty_page(self):
        """Crea una pagina con todos los slots marcados como borrados."""
        page = bytearray(self.page_size)
        for i in range(self.records_per_page()):
            page[i * self.record_size] = 1   # deleted flag
        return page

    def read_record(self, page_num, slot):
        """Lee un registro. Retorna tupla o None si esta borrado."""
        page = self.read_page(page_num)
        offset = slot * self.record_size
        if page[offset] == 1:
            return None
        data = page[offset + 1: offset + self.record_size]
        return self.struct.unpack(data)

    def write_record(self, page_num, slot, record):
        """Escribe un registro en un slot especifico."""
        page = bytearray(self.read_page(page_num))
        offset = slot * self.record_size
        page[offset] = 0   # active
        page[offset + 1: offset + self.record_size] = self.struct.pack(*record)
        self.write_page(page_num, page)

    # ------------------------------------------------------------------ #
    #  INSERT                                                              #
    # ------------------------------------------------------------------ #

    def add_record(self, record):
        """Inserta un registro. Reutiliza slots borrados o agrega al final.
        Retorna (page_num, slot)."""
        # Caso 1: reutilizar hueco
        if self.free_slots:
            p, slot = self.free_slots.pop()
            page = bytearray(self.read_page(p))
            offset = slot * self.record_size
            page[offset] = 0
            page[offset + 1: offset + self.record_size] = self.struct.pack(*record)
            self.write_page(p, page)
            return (p, slot)

        # Caso 2: agregar al final
        if self.num_pages() == 0:
            page = self.create_empty_page()
            self.write_page(0, page)
            self.last_page = 0
            self.last_slot = 0

        page = bytearray(self.read_page(self.last_page))
        offset = self.last_slot * self.record_size

        if self.last_slot < self.records_per_page():
            page[offset] = 0
            page[offset + 1: offset + self.record_size] = self.struct.pack(*record)
            self.write_page(self.last_page, page)
            self.last_slot += 1
            return (self.last_page, self.last_slot - 1)

        # Nueva pagina
        p = self.num_pages()
        page = self.create_empty_page()
        page[0] = 0
        page[1:self.record_size] = self.struct.pack(*record)
        self.write_page(p, page)
        self.last_page = p
        self.last_slot = 1
        return (p, 0)

    # ------------------------------------------------------------------ #
    #  DELETE                                                              #
    # ------------------------------------------------------------------ #

    def delete_record(self, page_num, slot):
        """Marca un registro como borrado y lo agrega a la free list."""
        page = bytearray(self.read_page(page_num))
        offset = slot * self.record_size
        if offset < len(page):
            page[offset] = 1
        self.write_page(page_num, page)
        self.free_slots.append((page_num, slot))

    # ------------------------------------------------------------------ #
    #  DEBUG                                                               #
    # ------------------------------------------------------------------ #

    def print_page(self, page_num):
        page = self.read_page(page_num)
        print(f"\n--- PAGE {page_num} ---")
        for slot in range(self.records_per_page()):
            offset = slot * self.record_size
            flag = page[offset]
            if flag == 1:
                print(f"Slot {slot}: EMPTY")
            else:
                data = page[offset + 1: offset + self.record_size]
                record = self.struct.unpack(data)
                print(f"Slot {slot}: {record}")