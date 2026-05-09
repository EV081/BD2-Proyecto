"""
PageManager — I/O generico de paginas sobre memoria secundaria.

Responsabilidad unica: leer y escribir paginas de tamanio fijo
en un archivo binario, y contabilizar los accesos a disco.

Cualquier componente que necesite acceso paginado a disco
(heap, B+Tree, SequentialFile, Hash, RTree) usa esta clase.
"""

import os


class PageManager:

    def __init__(self, filepath, page_size=4096):
        """
        Args:
            filepath: ruta al archivo binario (se crea si no existe).
            page_size: tamanio de cada pagina en bytes (default 4096).
        """
        self.path = filepath
        self.page_size = page_size

        # Contadores de acceso a disco
        self.disk_reads = 0
        self.disk_writes = 0

        # Crear directorio y archivo si no existen
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if not os.path.exists(filepath):
            open(filepath, "wb").close()

    # ------------------------------------------------------------------ #
    #  STATS                                                               #
    # ------------------------------------------------------------------ #

    def reset_stats(self):
        self.disk_reads = 0
        self.disk_writes = 0

    # ------------------------------------------------------------------ #
    #  PAGE I/O                                                            #
    # ------------------------------------------------------------------ #

    def num_pages(self):
        """Numero de paginas en el archivo."""
        return os.path.getsize(self.path) // self.page_size

    def read_page(self, page_id):
        """Lee una pagina completa del disco. Retorna bytes."""
        self.disk_reads += 1
        with open(self.path, "rb") as f:
            f.seek(page_id * self.page_size)
            data = f.read(self.page_size)
        if len(data) < self.page_size:
            # Pagina incompleta: rellenar con ceros
            data = data + b"\x00" * (self.page_size - len(data))
        return data

    def write_page(self, page_id, data):
        """Escribe una pagina completa al disco. Auto-extiende el archivo."""
        self.disk_writes += 1
        needed = (page_id + 1) * self.page_size
        file_size = os.path.getsize(self.path)

        # Si el archivo es mas chico, extender con ceros
        if file_size < needed:
            with open(self.path, "ab") as f:
                f.write(b"\x00" * (needed - file_size))

        with open(self.path, "rb+") as f:
            f.seek(page_id * self.page_size)
            f.write(data)

    def allocate_page(self):
        """Reserva una pagina nueva al final del archivo. Retorna su page_id."""
        page_id = self.num_pages()
        self.write_page(page_id, bytearray(self.page_size))
        return page_id

    def truncate(self, num_pages):
        """Trunca el archivo a exactamente num_pages paginas."""
        with open(self.path, "r+b") as f:
            f.truncate(num_pages * self.page_size)
