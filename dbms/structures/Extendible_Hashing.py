"""
ExtendibleHash — Indice basado en Extendible Hashing.

Usa un directorio que duplica su tamaño cuando un bucket se desborda.
Busqueda por igualdad en O(1) promedio (1-2 accesos a disco).
Range search requiere escanear todos los buckets (no es eficiente para rangos).

Interfaz compatible con BPlusTree para integrarse con dbengine.
"""

import os
import struct


class ExtendibleHash:

    # Metadata (pagina 0): global_depth(4), num_buckets(4), num_entries(4)
    META_FMT = "=III"
    META_SIZE = struct.calcsize(META_FMT)

    # Bucket header: local_depth(4), count(4)
    BUCKET_HEADER_FMT = "=II"
    BUCKET_HEADER_SIZE = struct.calcsize(BUCKET_HEADER_FMT)

    def __init__(self, index_file, key_format="i", page_size=4096, unique=True,
                 bucket_capacity=None):
        self.page_size = page_size
        self.unique = unique
        self.key_fmt = "=" + key_format
        self.key_size = struct.calcsize(self.key_fmt)
        self.val_fmt = "=ii"  # RID: (page_num, slot)
        self.val_size = struct.calcsize(self.val_fmt)
        self.entry_size = self.key_size + self.val_size

        # Capacidad de un bucket (entradas por pagina)
        if bucket_capacity is None:
            self.bucket_capacity = (page_size - self.BUCKET_HEADER_SIZE) // self.entry_size
        else:
            self.bucket_capacity = bucket_capacity

        # Contadores de acceso a disco
        self.disk_reads = 0
        self.disk_writes = 0

        # Guardar en carpeta indexes/
        index_dir = os.path.join(os.path.dirname(os.path.abspath(index_file)), "indexes")
        os.makedirs(index_dir, exist_ok=True)
        self.index_file = os.path.join(index_dir, os.path.basename(index_file))

        # Estado en memoria
        self.global_depth = 0
        self.directory = []  # lista de page_ids de buckets
        self.num_buckets = 0
        self.num_entries = 0

        if os.path.exists(self.index_file) and os.path.getsize(self.index_file) >= page_size:
            self._load_metadata()
        else:
            self._init_file()

    def reset_stats(self):
        self.disk_reads = 0
        self.disk_writes = 0

    # ------------------------------------------------------------------ #
    #  ACCESO A DISCO                                                      #
    # ------------------------------------------------------------------ #

    def _read_page(self, page_id):
        self.disk_reads += 1
        with open(self.index_file, "rb") as f:
            f.seek(page_id * self.page_size)
            data = f.read(self.page_size)
        if len(data) < self.page_size:
            data = data + b"\x00" * (self.page_size - len(data))
        return data

    def _write_page(self, page_id, data):
        self.disk_writes += 1
        needed = (page_id + 1) * self.page_size
        file_size = os.path.getsize(self.index_file) if os.path.exists(self.index_file) else 0
        if file_size < needed:
            with open(self.index_file, "ab") as f:
                f.write(b"\x00" * (needed - file_size))
        with open(self.index_file, "r+b") as f:
            f.seek(page_id * self.page_size)
            f.write(data)

    def _alloc_page(self):
        """Reserva una nueva pagina al final del archivo."""
        file_size = os.path.getsize(self.index_file) if os.path.exists(self.index_file) else 0
        page_id = file_size // self.page_size
        # Escribir pagina vacia
        with open(self.index_file, "ab") as f:
            f.write(b"\x00" * self.page_size)
        return page_id

    # ------------------------------------------------------------------ #
    #  INICIALIZACION Y METADATA                                           #
    # ------------------------------------------------------------------ #

    def _init_file(self):
        """Crea un archivo nuevo con depth=1, 2 buckets."""
        with open(self.index_file, "wb") as f:
            f.write(b"\x00" * self.page_size)  # pagina 0: metadata

        self.global_depth = 1
        self.num_buckets = 2
        self.num_entries = 0

        # Crear 2 buckets iniciales (paginas 1 y 2)
        bucket0_page = self._create_empty_bucket(local_depth=1)
        bucket1_page = self._create_empty_bucket(local_depth=1)

        self.directory = [bucket0_page, bucket1_page]
        self._save_metadata()

    def _create_empty_bucket(self, local_depth):
        """Crea un bucket vacio y retorna su page_id."""
        page_id = self._alloc_page()
        page = bytearray(self.page_size)
        struct.pack_into(self.BUCKET_HEADER_FMT, page, 0, local_depth, 0)
        self._write_page(page_id, page)
        return page_id

    def _save_metadata(self):
        """Guarda metadata + directorio en pagina 0."""
        page = bytearray(self.page_size)
        struct.pack_into(self.META_FMT, page, 0,
                         self.global_depth, self.num_buckets, self.num_entries)
        # Directorio despues de metadata
        off = self.META_SIZE
        for page_id in self.directory:
            struct.pack_into("=I", page, off, page_id)
            off += 4
        self._write_page(0, page)

    def _load_metadata(self):
        """Carga metadata + directorio desde pagina 0."""
        data = self._read_page(0)
        self.global_depth, self.num_buckets, self.num_entries = struct.unpack_from(
            self.META_FMT, data, 0)
        dir_size = 1 << self.global_depth
        self.directory = []
        off = self.META_SIZE
        for _ in range(dir_size):
            page_id = struct.unpack_from("=I", data, off)[0]
            self.directory.append(page_id)
            off += 4

    # ------------------------------------------------------------------ #
    #  BUCKET OPERATIONS                                                   #
    # ------------------------------------------------------------------ #

    def _read_bucket(self, page_id):
        """Lee un bucket y retorna (local_depth, entries: list[(key, rid)])."""
        data = self._read_page(page_id)
        local_depth, count = struct.unpack_from(self.BUCKET_HEADER_FMT, data, 0)
        entries = []
        off = self.BUCKET_HEADER_SIZE
        for _ in range(count):
            key = struct.unpack_from(self.key_fmt, data, off)[0]
            rid = struct.unpack_from(self.val_fmt, data, off + self.key_size)
            entries.append((key, rid))
            off += self.entry_size
        return local_depth, entries

    def _write_bucket(self, page_id, local_depth, entries):
        """Escribe un bucket con sus entradas."""
        page = bytearray(self.page_size)
        struct.pack_into(self.BUCKET_HEADER_FMT, page, 0, local_depth, len(entries))
        off = self.BUCKET_HEADER_SIZE
        for key, rid in entries:
            struct.pack_into(self.key_fmt, page, off, key)
            struct.pack_into(self.val_fmt, page, off + self.key_size, *rid)
            off += self.entry_size
        self._write_page(page_id, page)

    # ------------------------------------------------------------------ #
    #  HASH                                                                #
    # ------------------------------------------------------------------ #

    def _hash(self, key):
        """Hash de la clave, retorna los bits menos significativos."""
        if isinstance(key, bytes):
            h = 0
            for b in key:
                h = h * 31 + b
        elif isinstance(key, int):
            h = key * 2654435761  # Knuth multiplicative hash
        elif isinstance(key, float):
            h = hash(key)
        else:
            h = hash(key)
        return h & ((1 << self.global_depth) - 1)

    def _normalize_key(self, key):
        if isinstance(key, str):
            key = key.encode("utf-8")
        packed = struct.pack(self.key_fmt, key)
        return struct.unpack(self.key_fmt, packed)[0]

    # ------------------------------------------------------------------ #
    #  BUSQUEDA                                                            #
    # ------------------------------------------------------------------ #

    def search(self, key):
        """Busca la primera entrada con la clave. Retorna RID o None."""
        key = self._normalize_key(key)
        idx = self._hash(key)
        bucket_page = self.directory[idx]
        _, entries = self._read_bucket(bucket_page)

        for entry_key, rid in entries:
            if entry_key == key:
                return rid
        return None

    def search_all(self, key, limit=0, offset=0):
        """Retorna todos los RIDs con la clave dada."""
        key = self._normalize_key(key)
        idx = self._hash(key)
        bucket_page = self.directory[idx]
        _, entries = self._read_bucket(bucket_page)

        results = []
        skipped = 0
        for entry_key, rid in entries:
            if entry_key == key:
                if skipped < offset:
                    skipped += 1
                else:
                    results.append(rid)
                    if limit and len(results) >= limit:
                        break
        return results

    def range_search(self, begin_key, end_key, limit=0, offset=0):
        """
        Extendible Hashing NO soporta rangeSearch.
        El dbengine usa full scan para rangos en columnas con indice hash.
        """
        raise NotImplementedError(
            "Extendible Hashing no soporta busqueda por rango. "
            "Use full scan o un indice B+Tree/Sequential."
        )

    # ------------------------------------------------------------------ #
    #  ADD (INSERT)                                                        #
    # ------------------------------------------------------------------ #

    def add(self, key, value):
        """Inserta (key, rid) en el hash."""
        key = self._normalize_key(key)
        idx = self._hash(key)
        bucket_page = self.directory[idx]
        local_depth, entries = self._read_bucket(bucket_page)

        # Verificar duplicado en modo unique
        if self.unique:
            for i, (entry_key, _) in enumerate(entries):
                if entry_key == key:
                    entries[i] = (key, value)
                    self._write_bucket(bucket_page, local_depth, entries)
                    return

        # Si hay espacio en el bucket
        if len(entries) < self.bucket_capacity:
            entries.append((key, value))
            self._write_bucket(bucket_page, local_depth, entries)
            self.num_entries += 1
            self._save_metadata()
            return

        # Bucket lleno -> split
        self._split_bucket(idx, bucket_page, local_depth, entries, key, value)

    def _split_bucket(self, dir_idx, bucket_page, local_depth, entries, new_key, new_value):
        """Divide un bucket y redistribuye las entradas."""
        entries.append((new_key, new_value))
        self.num_entries += 1

        if local_depth == self.global_depth:
            # Duplicar directorio
            self.global_depth += 1
            self.directory = self.directory + self.directory[:]

        new_local_depth = local_depth + 1
        new_bucket_page = self._create_empty_bucket(new_local_depth)
        self.num_buckets += 1

        # Redistribuir entradas
        entries_old = []
        entries_new = []
        bit_mask = 1 << (new_local_depth - 1)

        for entry_key, rid in entries:
            h = self._hash_full(entry_key)
            if h & bit_mask:
                entries_new.append((entry_key, rid))
            else:
                entries_old.append((entry_key, rid))

        # Escribir ambos buckets
        self._write_bucket(bucket_page, new_local_depth, entries_old)
        self._write_bucket(new_bucket_page, new_local_depth, entries_new)

        # Actualizar directorio
        for i in range(len(self.directory)):
            if self.directory[i] == bucket_page:
                h_bits = i & ((1 << new_local_depth) - 1)
                if h_bits & bit_mask:
                    self.directory[i] = new_bucket_page

        self._save_metadata()

        # Verificar si alguno de los buckets sigue desbordado
        if len(entries_old) > self.bucket_capacity:
            idx = self._find_dir_index(bucket_page)
            self._split_bucket(idx, bucket_page, new_local_depth, entries_old[:-1],
                               entries_old[-1][0], entries_old[-1][1])
            self.num_entries -= 1  # Corregir doble conteo
        if len(entries_new) > self.bucket_capacity:
            idx = self._find_dir_index(new_bucket_page)
            self._split_bucket(idx, new_bucket_page, new_local_depth, entries_new[:-1],
                               entries_new[-1][0], entries_new[-1][1])
            self.num_entries -= 1

    def _hash_full(self, key):
        """Hash completo sin mascara (para redistribucion)."""
        if isinstance(key, bytes):
            h = 0
            for b in key:
                h = h * 31 + b
        elif isinstance(key, int):
            h = key * 2654435761
        elif isinstance(key, float):
            h = hash(key)
        else:
            h = hash(key)
        return h

    def _find_dir_index(self, bucket_page):
        """Encuentra un indice del directorio que apunte a este bucket."""
        for i, page in enumerate(self.directory):
            if page == bucket_page:
                return i
        return 0

    # ------------------------------------------------------------------ #
    #  REMOVE (DELETE)                                                     #
    # ------------------------------------------------------------------ #

    def remove(self, key, value=None):
        """Elimina una entrada. Si value se especifica, elimina esa entrada exacta."""
        key = self._normalize_key(key)
        idx = self._hash(key)
        bucket_page = self.directory[idx]
        local_depth, entries = self._read_bucket(bucket_page)

        found = False
        for i, (entry_key, rid) in enumerate(entries):
            if entry_key == key:
                if value is None or rid == tuple(value):
                    entries.pop(i)
                    found = True
                    break

        if not found:
            return False

        self._write_bucket(bucket_page, local_depth, entries)
        self.num_entries -= 1
        self._save_metadata()
        return True
