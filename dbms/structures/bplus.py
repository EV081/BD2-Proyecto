import os
import math
import struct


class BPlusTree:

    HEADER_FMT = "=BIi"                        # is_leaf(1) num_keys(4) next_leaf(4)
    HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 9 bytes
    META_FMT = "=iI"                            # root_page(4) num_pages(4)
    META_SIZE = struct.calcsize(META_FMT)       # 8 bytes

    def __init__(self, index_file, key_format="i", page_size=4096, unique=True):
        self.index_file = index_file
        self.page_size = page_size
        self.unique = unique
        self.key_fmt = "=" + key_format
        self.key_size = struct.calcsize(self.key_fmt)
        self.val_fmt = "=ii"                    # Record IDentifier: (page_num, slot)
        self.val_size = struct.calcsize(self.val_fmt)
        self.child_size = 4                     # page_id

        # Max keys por nodo (limitado por espacio en pagina)
        # Interno: HEADER + max_keys * key + (max_keys+1) * child <= page_size
        # Hoja:    HEADER + max_keys * key + max_keys * val     <= page_size
        internal_max = (page_size - self.HEADER_SIZE - self.child_size) // (self.key_size + self.child_size)
        leaf_max = (page_size - self.HEADER_SIZE) // (self.key_size + self.val_size)
        self.max_keys = min(internal_max, leaf_max)

        # Garantiza que los nodos esten al menos medio llenos
        self.min_keys = math.ceil(self.max_keys / 2)

        # Contadores de acceso a disco
        self.disk_reads = 0
        self.disk_writes = 0

        # Metadata
        self.root_page = -1
        self.num_pages = 1   # page 0 = metadata

        # Guardar el archivo de indice dentro de la carpeta "indexes"
        index_dir = os.path.join(os.path.dirname(os.path.abspath(index_file)), "indexes")
        os.makedirs(index_dir, exist_ok=True)
        self.index_file = os.path.join(index_dir, os.path.basename(index_file))

        if os.path.exists(self.index_file) and os.path.getsize(self.index_file) >= page_size:
            self._load_metadata()
        else:
            self._init_file()

    def reset_stats(self):
        self.disk_reads = 0
        self.disk_writes = 0

    # ------------------------------------------------------------------ #
    #  ACCESO A DISCO (bajo nivel)                                        #
    # ------------------------------------------------------------------ #

    def _init_file(self):
        with open(self.index_file, "wb") as f:
            page = bytearray(self.page_size)
            struct.pack_into(self.META_FMT, page, 0, -1, 1)
            f.write(page)

    def _load_metadata(self):
        data = self._read_page_raw(0)
        self.root_page, self.num_pages = struct.unpack_from(self.META_FMT, data, 0)

    def _save_metadata(self):
        page = bytearray(self.page_size)
        struct.pack_into(self.META_FMT, page, 0, self.root_page, self.num_pages)
        self._write_page_raw(0, page)

    def _read_page_raw(self, page_id):
        self.disk_reads += 1
        with open(self.index_file, "rb") as f:
            f.seek(page_id * self.page_size)
            return f.read(self.page_size)

    def _write_page_raw(self, page_id, data):
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
        pid = self.num_pages
        self.num_pages += 1
        return pid

    # ------------------------------------------------------------------ #
    #  SERIALIZACION DE NODOS                                             #
    # ------------------------------------------------------------------ #

    def _read_node(self, page_id):
        data = self._read_page_raw(page_id)
        is_leaf, num_keys, next_leaf = struct.unpack_from(self.HEADER_FMT, data, 0)

        keys = []
        off = self.HEADER_SIZE
        for _ in range(num_keys):
            keys.append(struct.unpack_from(self.key_fmt, data, off)[0])
            off += self.key_size

        # Area de values/children empieza despues de max_keys claves
        area_off = self.HEADER_SIZE + self.max_keys * self.key_size

        if is_leaf:
            values = []
            for i in range(num_keys):
                v = struct.unpack_from(self.val_fmt, data, area_off + i * self.val_size)
                values.append(v)
            return {
                "is_leaf": True, "keys": keys, "values": values,
                "next_leaf": next_leaf, "page_id": page_id,
            }
        else:
            children = []
            for i in range(num_keys + 1):
                c = struct.unpack_from("=i", data, area_off + i * self.child_size)[0]
                children.append(c)
            return {
                "is_leaf": False, "keys": keys, "children": children,
                "next_leaf": -1, "page_id": page_id,
            }

    def _write_node(self, page_id, node):
        page = bytearray(self.page_size)
        keys = node["keys"]
        struct.pack_into(
            self.HEADER_FMT, page, 0,
            int(node["is_leaf"]), len(keys), node.get("next_leaf", -1),
        )

        off = self.HEADER_SIZE
        for k in keys:
            struct.pack_into(self.key_fmt, page, off, k)
            off += self.key_size

        area_off = self.HEADER_SIZE + self.max_keys * self.key_size

        if node["is_leaf"]:
            for i, v in enumerate(node["values"]):
                struct.pack_into(self.val_fmt, page, area_off + i * self.val_size, *v)
        else:
            for i, c in enumerate(node["children"]):
                struct.pack_into("=i", page, area_off + i * self.child_size, c)

        self._write_page_raw(page_id, page)

    # ------------------------------------------------------------------ #
    #  HELPERS                                                            #
    # ------------------------------------------------------------------ #

    def _normalize_key(self, key):
        if isinstance(key, str):
            key = key.encode("utf-8")
        packed = struct.pack(self.key_fmt, key)
        return struct.unpack(self.key_fmt, packed)[0]

    def _find_leaf(self, key, leftmost=False):
        path = []
        node = self._read_node(self.root_page)
        while not node["is_leaf"]:
            i = 0
            if leftmost:
                while i < len(node["keys"]) and key > node["keys"][i]:
                    i += 1
            else:
                while i < len(node["keys"]) and key >= node["keys"][i]:
                    i += 1
            path.append((node, i))
            node = self._read_node(node["children"][i])
        return node, path

    def _find_key_in_leaf(self, leaf, key, value=None):
        for i, k in enumerate(leaf["keys"]):
            if k == key:
                if value is None or leaf["values"][i] == tuple(value):
                    return i
            elif k > key:
                break
        return None

    # ------------------------------------------------------------------ #
    #  BUSQUEDA                                                             #
    # ------------------------------------------------------------------ #

    def search(self, key):
        key = self._normalize_key(key)
        if self.root_page == -1:
            return None

        # Para non-unique, ir a la hoja izquierda para encontrar la primera ocurrencia.
        # Para unique, ir a la derecha (donde esta el dato cuando key == separador).
        leaf, _ = self._find_leaf(key, leftmost=not self.unique)

        while True:
            for i, k in enumerate(leaf["keys"]):
                if k == key:
                    return leaf["values"][i]
                elif k > key:
                    return None
            if leaf["next_leaf"] == -1:
                return None
            leaf = self._read_node(leaf["next_leaf"])

    def search_all(self, key, limit=0, offset=0):
        """
        Retorna los RIDs asociados a una clave (indice no-unico).

        Args:
            key: Clave a buscar.
            limit: Maximo de resultados a retornar (0 = sin limite).
            offset: Cantidad de resultados a saltar antes de empezar a recoger.
        """
        key = self._normalize_key(key)
        if self.root_page == -1:
            return []

        leaf, _ = self._find_leaf(key, leftmost=True)
        results = []
        skipped = 0

        while True:
            for i, k in enumerate(leaf["keys"]):
                if k == key:
                    if skipped < offset:
                        skipped += 1
                        continue
                    results.append(leaf["values"][i])
                    if limit and len(results) >= limit:
                        return results
                elif k > key:
                    return results
            if leaf["next_leaf"] == -1:
                break
            leaf = self._read_node(leaf["next_leaf"])

        return results

    def range_search(self, begin_key, end_key, limit=0, offset=0):
        """
        Busqueda por rango [begin, end].

        Args:
            begin_key: Clave inicial (inclusive).
            end_key: Clave final (inclusive).
            limit: Maximo de resultados a retornar (0 = sin limite).
            offset: Cantidad de resultados a saltar antes de empezar a recoger.
        """
        begin_key = self._normalize_key(begin_key)
        end_key = self._normalize_key(end_key)

        if self.root_page == -1:
            return []

        leaf, _ = self._find_leaf(begin_key, leftmost=True)
        results = []
        skipped = 0

        while True:
            for i, k in enumerate(leaf["keys"]):
                if k > end_key:
                    return results
                if k >= begin_key:
                    if skipped < offset:
                        skipped += 1
                        continue
                    results.append(leaf["values"][i])
                    if limit and len(results) >= limit:
                        return results
            if leaf["next_leaf"] == -1:
                break
            leaf = self._read_node(leaf["next_leaf"])

        return results

    # ------------------------------------------------------------------ #
    #  ADD (INSERT)                                                       #
    # ------------------------------------------------------------------ #

    def add(self, key, value):
        key = self._normalize_key(key)

        # Arbol vacio: crear primera hoja
        if self.root_page == -1:
            pid = self._alloc_page()
            self._write_node(pid, {
                "is_leaf": True, "keys": [key], "values": [value],
                "next_leaf": -1, "page_id": pid,
            })
            self.root_page = pid
            self._save_metadata()
            return

        leaf, path = self._find_leaf(key)

        # Posicion de insercion (mantener orden)
        i = 0
        while i < len(leaf["keys"]) and key > leaf["keys"][i]:
            i += 1

        # Manejo de clave duplicada
        if i < len(leaf["keys"]) and leaf["keys"][i] == key:
            if self.unique:
                # Indice unico: sobreescribir el RID existente
                leaf["values"][i] = value
                self._write_node(leaf["page_id"], leaf)
                return
            # Indice no-unico: avanzar tras los duplicados existentes
            # para insertar al final del grupo (mantener orden de insercion)
            while i < len(leaf["keys"]) and leaf["keys"][i] == key:
                i += 1

        leaf["keys"].insert(i, key)
        leaf["values"].insert(i, value)

        if len(leaf["keys"]) <= self.max_keys:
            self._write_node(leaf["page_id"], leaf)
        else:
            self._split_leaf(leaf, path)

        self._save_metadata()

    def _split_leaf(self, node, path):
        mid = len(node["keys"]) // 2

        right_pid = self._alloc_page()
        right = {
            "is_leaf": True,
            "keys": node["keys"][mid:],
            "values": node["values"][mid:],
            "next_leaf": node["next_leaf"],
            "page_id": right_pid,
        }
        node["keys"] = node["keys"][:mid]
        node["values"] = node["values"][:mid]
        node["next_leaf"] = right_pid

        self._write_node(node["page_id"], node)
        self._write_node(right_pid, right)

        self._insert_into_parent(node["page_id"], right["keys"][0], right_pid, path)

    def _split_internal(self, node, path):
        mid = len(node["keys"]) // 2
        push_key = node["keys"][mid]

        right_pid = self._alloc_page()
        right = {
            "is_leaf": False,
            "keys": node["keys"][mid + 1:],
            "children": node["children"][mid + 1:],
            "next_leaf": -1,
            "page_id": right_pid,
        }
        node["keys"] = node["keys"][:mid]
        node["children"] = node["children"][:mid + 1]

        self._write_node(node["page_id"], node)
        self._write_node(right_pid, right)

        self._insert_into_parent(node["page_id"], push_key, right_pid, path)

    def _insert_into_parent(self, left_pid, key, right_pid, path):
        if not path:
            # Nueva raiz
            new_root = self._alloc_page()
            self._write_node(new_root, {
                "is_leaf": False,
                "keys": [key],
                "children": [left_pid, right_pid],
                "next_leaf": -1, "page_id": new_root,
            })
            self.root_page = new_root
            return

        parent, child_idx = path.pop()
        parent["keys"].insert(child_idx, key)
        parent["children"].insert(child_idx + 1, right_pid)

        if len(parent["keys"]) <= self.max_keys:
            self._write_node(parent["page_id"], parent)
        else:
            self._split_internal(parent, path)

    # ------------------------------------------------------------------ #
    #  REMOVE (DELETE)                                                    #
    # ------------------------------------------------------------------ #

    def remove(self, key, value=None):
        key = self._normalize_key(key)
        if self.root_page == -1:
            return False

        # Para non-unique, buscar desde la hoja izquierda;
        # para unique, ir a la derecha (donde key == separador implica dato a la derecha)
        leftmost = not self.unique
        leaf, path = self._find_leaf(key, leftmost=leftmost)

        # Buscar clave (y opcionalmente RID especifico) en la hoja
        key_idx = self._find_key_in_leaf(leaf, key, value)

        # Si no se encontro en esta hoja, escanear hojas siguientes (non-unique)
        if key_idx is None and not self.unique:
            while leaf["next_leaf"] != -1:
                next_leaf = self._read_node(leaf["next_leaf"])
                key_idx = self._find_key_in_leaf(next_leaf, key, value)
                if key_idx is not None:
                    # Encontrado en hoja accedida via next_leaf.
                    # Eliminar directamente sin underflow cascading
                    # (la hoja intermedia tipicamente no esta cerca del minimo).
                    next_leaf["keys"].pop(key_idx)
                    next_leaf["values"].pop(key_idx)
                    self._write_node(next_leaf["page_id"], next_leaf)
                    self._save_metadata()
                    return True
                if not any(k == key for k in next_leaf["keys"]):
                    break
                leaf = next_leaf

        if key_idx is None:
            return False

        leaf["keys"].pop(key_idx)
        leaf["values"].pop(key_idx)

        # Caso especial: hoja raiz
        if leaf["page_id"] == self.root_page:
            if not leaf["keys"]:
                self.root_page = -1
            self._write_node(leaf["page_id"], leaf)
            self._save_metadata()
            return True

        if len(leaf["keys"]) >= self.min_keys:
            self._write_node(leaf["page_id"], leaf)
            self._save_metadata()
            return True

        # Underflow: redistribuir o fusionar
        self._handle_leaf_underflow(leaf, path)
        self._save_metadata()
        return True

    def _handle_leaf_underflow(self, node, path):
        if not path:
            self._write_node(node["page_id"], node)
            return

        parent, child_idx = path[-1]

        # Intentar prestar del hermano izquierdo
        if child_idx > 0:
            left = self._read_node(parent["children"][child_idx - 1])
            if len(left["keys"]) > self.min_keys:
                node["keys"].insert(0, left["keys"].pop())
                node["values"].insert(0, left["values"].pop())
                parent["keys"][child_idx - 1] = node["keys"][0]
                self._write_node(left["page_id"], left)
                self._write_node(node["page_id"], node)
                self._write_node(parent["page_id"], parent)
                return

        # Intentar prestar del hermano derecho
        if child_idx < len(parent["children"]) - 1:
            right = self._read_node(parent["children"][child_idx + 1])
            if len(right["keys"]) > self.min_keys:
                node["keys"].append(right["keys"].pop(0))
                node["values"].append(right["values"].pop(0))
                parent["keys"][child_idx] = right["keys"][0]
                self._write_node(right["page_id"], right)
                self._write_node(node["page_id"], node)
                self._write_node(parent["page_id"], parent)
                return

        # Fusionar
        if child_idx > 0:
            left = self._read_node(parent["children"][child_idx - 1])
            self._merge_leaves(left, node, parent, child_idx - 1, path)
        else:
            right = self._read_node(parent["children"][child_idx + 1])
            self._merge_leaves(node, right, parent, child_idx, path)

    def _merge_leaves(self, left, right, parent, sep_idx, path):
        left["keys"].extend(right["keys"])
        left["values"].extend(right["values"])
        left["next_leaf"] = right["next_leaf"]
        self._write_node(left["page_id"], left)

        parent["keys"].pop(sep_idx)
        parent["children"].pop(sep_idx + 1)

        if parent["page_id"] == self.root_page and not parent["keys"]:
            self.root_page = left["page_id"]
        elif len(parent["keys"]) < self.min_keys and parent["page_id"] != self.root_page:
            path.pop()
            self._handle_internal_underflow(parent, path)
        else:
            self._write_node(parent["page_id"], parent)

    def _handle_internal_underflow(self, node, path):
        if not path:
            if not node["keys"] and len(node["children"]) == 1:
                self.root_page = node["children"][0]
            else:
                self._write_node(node["page_id"], node)
            return

        parent, child_idx = path[-1]

        # Prestar del hermano izquierdo
        if child_idx > 0:
            left = self._read_node(parent["children"][child_idx - 1])
            if len(left["keys"]) > self.min_keys:
                node["keys"].insert(0, parent["keys"][child_idx - 1])
                node["children"].insert(0, left["children"].pop())
                parent["keys"][child_idx - 1] = left["keys"].pop()
                self._write_node(left["page_id"], left)
                self._write_node(node["page_id"], node)
                self._write_node(parent["page_id"], parent)
                return

        # Prestar del hermano derecho
        if child_idx < len(parent["children"]) - 1:
            right = self._read_node(parent["children"][child_idx + 1])
            if len(right["keys"]) > self.min_keys:
                node["keys"].append(parent["keys"][child_idx])
                node["children"].append(right["children"].pop(0))
                parent["keys"][child_idx] = right["keys"].pop(0)
                self._write_node(right["page_id"], right)
                self._write_node(node["page_id"], node)
                self._write_node(parent["page_id"], parent)
                return

        # Fusionar nodos internos
        if child_idx > 0:
            left = self._read_node(parent["children"][child_idx - 1])
            self._merge_internal(left, node, parent, child_idx - 1, path)
        else:
            right = self._read_node(parent["children"][child_idx + 1])
            self._merge_internal(node, right, parent, child_idx, path)

    def _merge_internal(self, left, right, parent, sep_idx, path):
        left["keys"].append(parent["keys"][sep_idx])
        left["keys"].extend(right["keys"])
        left["children"].extend(right["children"])
        self._write_node(left["page_id"], left)

        parent["keys"].pop(sep_idx)
        parent["children"].pop(sep_idx + 1)

        if parent["page_id"] == self.root_page and not parent["keys"]:
            self.root_page = left["page_id"]
        elif len(parent["keys"]) < self.min_keys and parent["page_id"] != self.root_page:
            path.pop()
            self._handle_internal_underflow(parent, path)
        else:
            self._write_node(parent["page_id"], parent)

    # ------------------------------------------------------------------ #
    #  DEBUG                                                              #
    # ------------------------------------------------------------------ #

    def print_tree(self):
        if self.root_page == -1:
            print("(arbol vacio)")
            return
        self._print_node(self.root_page, 0)

    def _print_node(self, page_id, level):
        node = self._read_node(page_id)
        indent = "  " * level
        if node["is_leaf"]:
            pairs = list(zip(node["keys"], node["values"]))
            print(f"{indent}HOJA[p{page_id}] keys={node['keys']}  next={node['next_leaf']}")
        else:
            print(f"{indent}INTERNO[p{page_id}] keys={node['keys']}")
            for c in node["children"]:
                self._print_node(c, level + 1)
