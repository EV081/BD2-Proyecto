import os
import struct

class PageManager:

    DB_FOLDER = "data"

    def __init__(self, table_name, record_format, page_size=4096):
        self.path = os.path.join(self.DB_FOLDER, table_name + ".dat")
        self.page_size = page_size
        self.struct = struct.Struct(record_format)
        self.record_size = self.struct.size + 1  # +1 deleted flag
        self.free_slots = []
        self.last_page = 0
        self.last_slot = 0

        os.makedirs(self.DB_FOLDER, exist_ok=True)

        if not os.path.exists(self.path):
            open(self.path, "wb").close()
        else:
            self._init_state()


    # ------------------------
    # INIT
    # ------------------------
    def _init_state(self):
        for p in range(self.num_pages()):
            page = self.read_page(p)
            for slot in range(self.records_per_page()):
                offset = slot * self.record_size
                if page[offset] == 1:
                    self.free_slots.append((p, slot))
                else:
                    if p > self.last_page or (p == self.last_page and s >= self.last_slot):
                        self.last_page = p
                        self.last_slot = slot


    # ------------------------
    # UTIL
    # ------------------------
    def records_per_page(self):
        return self.page_size // self.record_size

    def num_pages(self):
        return os.path.getsize(self.path) // self.page_size

    # ------------------------
    # PAGE
    # ------------------------
    def read_page(self, page_num):
        with open(self.path, "rb") as f:
            f.seek(page_num * self.page_size)
            return f.read(self.page_size)

    def write_page(self, page_num, data):
        with open(self.path, "rb+") as f:
            f.seek(page_num * self.page_size)
            f.write(data)

    def create_empty_page(self):
        page = bytearray(self.page_size)
        for i in range(self.records_per_page()):
            page[i * self.record_size] = 1  # all deleted
        return page

    # ------------------------
    # RECORD
    # ------------------------
    def read_record(self, page_num, slot):
        page = self.read_page(page_num)

        offset = slot * self.record_size
        if page[offset] == 1:
            return None

        data = page[offset + 1: offset + self.record_size]
        return self.struct.unpack(data)

    def write_record(self, page_num, slot, record):
        page = bytearray(self.read_page(page_num))

        offset = slot * self.record_size
        page[offset] = 0  # active
        page[offset + 1: offset + self.record_size] = self.struct.pack(*record)

        self.write_page(page_num, page)

    # ------------------------
    # INSERT
    # ------------------------
    def add_record(self, record):
        # Caso 1: Usar free slots
        if self.free_slots:
            p, slot = self.free_slots.pop()
            page = bytearray(self.read_page(p))
            offset = slot * self.record_size
            page[offset] = 0
            page[offset + 1: offset + self.record_size] = self.struct.pack(*record)
            self.write_page(p, page)
            return (p, slot)

        # Caso 2: Agregar al final  
        if self.num_pages() == 0:
            page = self.create_empty_page()
            self.write_page(0, page)
            self.last_page = 0
            self.last_slot = 0

        page = bytearray(self.read_page(self.last_page))
        offset = self.last_slot * self.record_size

        # Si hay espacio
        if self.last_slot < self.records_per_page():
            page[offset] = 0
            page[offset + 1: offset + self.record_size] = self.struct.pack(*record)
            self.write_page(self.last_page, page)
            self.last_slot += 1
            return (self.last_page, self.last_slot - 1)
        
        # Si no hay -> nueva pagina
        p = self.num_pages()
        page = self.create_empty_page()

        page[0] = 0
        page[1:self.record_size] = self.struct.pack(*record)

        self.write_page(p, page)

        # actualizar tail
        self.last_page = p
        self.last_slot = 1

        return (p, 0)


    # ------------------------
    # DELETE
    # ------------------------
    def delete_record(self, page_num, slot):
        page = bytearray(self.read_page(page_num))
        offset = slot * self.record_size
        if offset < len(page):
            page[offset] = 1
        self.write_page(page_num, page)
        # agregar a free list
        self.free_slots.append((page_num, slot))



    # ------------------------
    # DEBUG
    # ------------------------
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

