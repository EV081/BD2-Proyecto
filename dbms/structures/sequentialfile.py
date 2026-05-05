"""
SequentialFile — Indice basado en archivo secuencial con archivo auxiliar.

Estructura:
  - Archivo principal (main): registros (key, rid) ordenados por key.
    Cada registro tiene un puntero (next) al siguiente en orden logico.
  - Archivo auxiliar (aux): registros nuevos que no se insertan en orden.
    Cuando el auxiliar alcanza K registros, se reconstruye (merge) el
    archivo principal integrando los registros auxiliares.

Operaciones: add, search, rangeSearch, remove.
Interfaz compatible con BPlusTree para integrarse con dbengine.
"""

import os
import struct


class SequentialFile:

    # Puntero: (file_id, position)
    #   file_id: 0 = main, 1 = aux, -1 = null
    PTR_FMT = "=bi"  # file_id(1) + pos(4) = 5 bytes
    PTR_SIZE = struct.calcsize(PTR_FMT)
    NULL_PTR = (-1, -1)

    # Metadata (archivo principal, al inicio):
    #   num_main(4), num_aux(4), head_file(1), head_pos(4), max_aux(4)
    META_FMT = "=IIbiI"
    META_SIZE = struct.calcsize(META_FMT)

    def __init__(self, index_file, key_format="i", page_size=4096, unique=True,
                 max_aux=5):
        self.page_size = page_size
        self.unique = unique
        self.key_fmt = "=" + key_format
        self.key_size = struct.calcsize(self.key_fmt)
        self.val_fmt = "=ii"  # RID: (page_num, slot)
        self.val_size = struct.calcsize(self.val_fmt)
        # Cada entrada: key + rid + next_ptr
        self.entry_size = self.key_size + self.val_size + self.PTR_SIZE
        self.max_aux = max_aux  # K: reconstruir cuando aux alcanza este tamaño

        # Contadores de acceso a disco
        self.disk_reads = 0
        self.disk_writes = 0

        # Guardar en carpeta indexes/
        index_dir = os.path.join(os.path.dirname(os.path.abspath(index_file)), "indexes")
        os.makedirs(index_dir, exist_ok=True)
        base = os.path.basename(index_file)
        self.main_file = os.path.join(index_dir, base)
        self.aux_file = os.path.join(index_dir, base.replace(".idx", "_aux.idx"))

        # Estado
        self.num_main = 0
        self.num_aux = 0
        self.head = self.NULL_PTR  # puntero al primer registro en orden

        if os.path.exists(self.main_file) and os.path.getsize(self.main_file) >= self.META_SIZE:
            self._load_metadata()
        else:
            self._init_files()

    def reset_stats(self):
        self.disk_reads = 0
        self.disk_writes = 0

    # ------------------------------------------------------------------ #
    #  ACCESO A DISCO                                                      #
    # ------------------------------------------------------------------ #

    def _init_files(self):
        """Crea archivos vacios con metadata."""
        with open(self.main_file, "wb") as f:
            meta = struct.pack(self.META_FMT, 0, 0, -1, -1, self.max_aux)
            f.write(meta)
        with open(self.aux_file, "wb") as f:
            pass  # archivo vacio

    def _load_metadata(self):
        self.disk_reads += 1
        with open(self.main_file, "rb") as f:
            data = f.read(self.META_SIZE)
        self.num_main, self.num_aux, h_file, h_pos, self.max_aux = struct.unpack(
            self.META_FMT, data)
        self.head = (h_file, h_pos)

    def _save_metadata(self):
        self.disk_writes += 1
        meta = struct.pack(self.META_FMT, self.num_main, self.num_aux,
                           self.head[0], self.head[1], self.max_aux)
        with open(self.main_file, "r+b") as f:
            f.write(meta)

    def _read_entry(self, file_id, pos):
        """Lee una entrada de main (file_id=0) o aux (file_id=1)."""
        self.disk_reads += 1
        filepath = self.main_file if file_id == 0 else self.aux_file
        offset = (self.META_SIZE + pos * self.entry_size) if file_id == 0 else (pos * self.entry_size)
        with open(filepath, "rb") as f:
            f.seek(offset)
            data = f.read(self.entry_size)
        if len(data) < self.entry_size:
            return None, None, self.NULL_PTR
        key = struct.unpack_from(self.key_fmt, data, 0)[0]
        rid = struct.unpack_from(self.val_fmt, data, self.key_size)
        next_file, next_pos = struct.unpack_from(self.PTR_FMT, data, self.key_size + self.val_size)
        return key, rid, (next_file, next_pos)

    def _write_entry(self, file_id, pos, key, rid, next_ptr):
        """Escribe una entrada en main o aux."""
        self.disk_writes += 1
        filepath = self.main_file if file_id == 0 else self.aux_file
        offset = (self.META_SIZE + pos * self.entry_size) if file_id == 0 else (pos * self.entry_size)

        entry = bytearray(self.entry_size)
        struct.pack_into(self.key_fmt, entry, 0, key)
        struct.pack_into(self.val_fmt, entry, self.key_size, *rid)
        struct.pack_into(self.PTR_FMT, entry, self.key_size + self.val_size, *next_ptr)

        # Asegurar que el archivo es suficientemente grande
        needed = offset + self.entry_size
        file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        if file_size < needed:
            with open(filepath, "ab") as f:
                f.write(b"\x00" * (needed - file_size))

        with open(filepath, "r+b") as f:
            f.seek(offset)
            f.write(entry)

    def _update_next_ptr(self, file_id, pos, next_ptr):
        """Actualiza solo el puntero next de una entrada existente."""
        self.disk_writes += 1
        filepath = self.main_file if file_id == 0 else self.aux_file
        offset = (self.META_SIZE + pos * self.entry_size) if file_id == 0 else (pos * self.entry_size)
        ptr_offset = offset + self.key_size + self.val_size

        with open(filepath, "r+b") as f:
            f.seek(ptr_offset)
            f.write(struct.pack(self.PTR_FMT, *next_ptr))

    def _normalize_key(self, key):
        if isinstance(key, str):
            key = key.encode("utf-8")
        packed = struct.pack(self.key_fmt, key)
        return struct.unpack(self.key_fmt, packed)[0]

    # ------------------------------------------------------------------ #
    #  RECORRIDO EN ORDEN (siguiendo punteros)                             #
    # ------------------------------------------------------------------ #

    def _traverse(self):
        """Recorre todas las entradas en orden logico siguiendo punteros."""
        current = self.head
        while current != self.NULL_PTR:
            file_id, pos = current
            key, rid, next_ptr = self._read_entry(file_id, pos)
            if key is None:
                break
            yield key, rid, file_id, pos, next_ptr
            current = next_ptr

    # ------------------------------------------------------------------ #
    #  BUSQUEDA                                                            #
    # ------------------------------------------------------------------ #

    def search(self, key):
        """Busca la primera entrada con la clave. Retorna RID o None."""
        key = self._normalize_key(key)
        for entry_key, rid, _, _, _ in self._traverse():
            if entry_key == key:
                return rid
            if entry_key > key:
                break
        return None

    def search_all(self, key, limit=0, offset=0):
        """Retorna todos los RIDs con la clave dada."""
        key = self._normalize_key(key)
        results = []
        skipped = 0
        for entry_key, rid, _, _, _ in self._traverse():
            if entry_key == key:
                if skipped < offset:
                    skipped += 1
                else:
                    results.append(rid)
                    if limit and len(results) >= limit:
                        break
            elif entry_key > key:
                break
        return results

    def range_search(self, begin_key, end_key, limit=0, offset=0):
        """Busqueda por rango [begin_key, end_key]."""
        begin_key = self._normalize_key(begin_key)
        end_key = self._normalize_key(end_key)
        results = []
        skipped = 0
        for entry_key, rid, _, _, _ in self._traverse():
            if entry_key > end_key:
                break
            if entry_key >= begin_key:
                if skipped < offset:
                    skipped += 1
                else:
                    results.append(rid)
                    if limit and len(results) >= limit:
                        break
        return results

    # ------------------------------------------------------------------ #
    #  ADD (INSERT)                                                        #
    # ------------------------------------------------------------------ #

    def add(self, key, value):
        """
        Inserta (key, rid).
        - Busca la posicion correcta siguiendo punteros.
        - Inserta en el archivo auxiliar.
        - Si aux alcanza max_aux, reconstruye.
        """
        key = self._normalize_key(key)

        # Caso: estructura vacia
        if self.head == self.NULL_PTR:
            # Insertar como primer registro en main
            self._write_entry(0, 0, key, value, self.NULL_PTR)
            self.head = (0, 0)
            self.num_main = 1
            self._save_metadata()
            return

        # Buscar posicion: encontrar el predecesor (prev) donde prev.key <= key < next.key
        prev_loc = None  # (file_id, pos) del predecesor
        current = self.head

        # Verificar si debe ir antes del head
        head_key, head_rid, head_next = self._read_entry(self.head[0], self.head[1])

        if key < head_key:
            # Insertar antes del head actual → en auxiliar
            aux_pos = self.num_aux
            self._write_entry(1, aux_pos, key, value, self.head)
            self.head = (1, aux_pos)
            self.num_aux += 1
            self._save_metadata()
            self._check_reconstruct()
            return

        if key == head_key and self.unique:
            # Sobreescribir
            self._write_entry(self.head[0], self.head[1], key, value, head_next)
            return

        # Recorrer para encontrar posicion
        prev_file, prev_pos = self.head[0], self.head[1]
        prev_key = head_key
        current = head_next

        while current != self.NULL_PTR:
            cur_key, cur_rid, cur_next = self._read_entry(current[0], current[1])
            if cur_key is None:
                break
            if cur_key >= key:
                if cur_key == key and self.unique:
                    # Sobreescribir
                    self._write_entry(current[0], current[1], key, value, cur_next)
                    return
                break
            prev_file, prev_pos = current[0], current[1]
            prev_key = cur_key
            current = cur_next

        # Insertar en auxiliar despues de prev
        aux_pos = self.num_aux
        self._write_entry(1, aux_pos, key, value, current)
        # Actualizar el next del predecesor
        self._update_next_ptr(prev_file, prev_pos, (1, aux_pos))
        self.num_aux += 1
        self._save_metadata()
        self._check_reconstruct()

    def _check_reconstruct(self):
        """Reconstruye si el auxiliar alcanzo el limite."""
        if self.num_aux >= self.max_aux:
            self._reconstruct()

    def _reconstruct(self):
        """
        Reconstruccion fisica: merge de main + aux en un nuevo main ordenado.
        """
        # Recolectar todas las entradas en orden
        entries = []
        for key, rid, _, _, _ in self._traverse():
            entries.append((key, rid))

        # Reescribir main con todas las entradas ordenadas
        with open(self.main_file, "wb") as f:
            meta = struct.pack(self.META_FMT, len(entries), 0, 0, 0, self.max_aux)
            f.write(meta)

        # Escribir entradas con punteros secuenciales
        for i, (key, rid) in enumerate(entries):
            if i < len(entries) - 1:
                next_ptr = (0, i + 1)
            else:
                next_ptr = self.NULL_PTR
            self._write_entry(0, i, key, rid, next_ptr)

        # Limpiar auxiliar
        with open(self.aux_file, "wb") as f:
            pass

        # Actualizar estado
        self.num_main = len(entries)
        self.num_aux = 0
        self.head = (0, 0) if entries else self.NULL_PTR
        self._save_metadata()

    # ------------------------------------------------------------------ #
    #  REMOVE (DELETE)                                                     #
    # ------------------------------------------------------------------ #

    def remove(self, key, value=None):
        """
        Elimina una entrada. Actualiza punteros para mantener la cadena.
        """
        key = self._normalize_key(key)

        if self.head == self.NULL_PTR:
            return False

        # Caso: eliminar el head
        head_key, head_rid, head_next = self._read_entry(self.head[0], self.head[1])
        if head_key == key and (value is None or head_rid == tuple(value)):
            self.head = head_next
            self._save_metadata()
            return True

        # Recorrer buscando la entrada a eliminar
        prev_file, prev_pos = self.head[0], self.head[1]
        current = head_next

        while current != self.NULL_PTR:
            cur_key, cur_rid, cur_next = self._read_entry(current[0], current[1])
            if cur_key is None:
                break
            if cur_key == key and (value is None or cur_rid == tuple(value)):
                # Eliminar: prev.next = current.next
                self._update_next_ptr(prev_file, prev_pos, cur_next)
                return True
            if cur_key > key:
                break
            prev_file, prev_pos = current[0], current[1]
            current = cur_next

        return False
