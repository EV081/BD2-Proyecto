"""
R-Tree: Indice Espacial 2D para puntos (latitud, longitud)
Soporta:
  - Insercion de puntos (x, y) con RID
  - Busqueda circular (centro + radio)
  - k-NN (k vecinos mas cercanos) con min-heap
  - Eliminacion con condense-tree
  - Paginacion de resultados
  - Respuesta JSON con puntos coloreados para visualizacion
"""

import os
import math
import struct
import heapq


class RTree:

    # Header: is_leaf(1B) num_entries(4B)
    HEADER_FMT = "=BI"
    HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 5 bytes

    # Metadata page (page 0)
    META_FMT = "=iI"  # root_page(4), num_pages(4)
    META_SIZE = struct.calcsize(META_FMT)  # 8 bytes

    # Leaf entry: x(8) y(8) page_num(4) slot(4) = 24 bytes
    LEAF_ENTRY_FMT = "=ddii"
    LEAF_ENTRY_SIZE = struct.calcsize(LEAF_ENTRY_FMT)

    # Internal entry: min_x(8) min_y(8) max_x(8) max_y(8) child_page(4) = 36 bytes
    INTERNAL_ENTRY_FMT = "=ddddi"
    INTERNAL_ENTRY_SIZE = struct.calcsize(INTERNAL_ENTRY_FMT)

    def __init__(self, index_file, page_size=4096):
        self.page_size = page_size

        # Max entries por tipo de nodo
        self.max_leaf_entries = (page_size - self.HEADER_SIZE) // self.LEAF_ENTRY_SIZE
        self.max_internal_entries = (page_size - self.HEADER_SIZE) // self.INTERNAL_ENTRY_SIZE

        # Min entries (ceil(M/2), minimo 2 para que split funcione)
        self.min_leaf_entries = max(2, math.ceil(self.max_leaf_entries / 2))
        self.min_internal_entries = max(2, math.ceil(self.max_internal_entries / 2))

        # Contadores de acceso a disco
        self.disk_reads = 0
        self.disk_writes = 0

        # Metadata
        self.root_page = -1
        self.num_pages = 1  # page 0 = metadata

        # Guardar en carpeta indexes/
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
    #  ACCESO A DISCO                                                      #
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
    #  SERIALIZACION DE NODOS                                              #
    # ------------------------------------------------------------------ #

    def _read_node(self, page_id):
        data = self._read_page_raw(page_id)
        is_leaf, num_entries = struct.unpack_from(self.HEADER_FMT, data, 0)

        if is_leaf:
            entries = []
            off = self.HEADER_SIZE
            for _ in range(num_entries):
                x, y, pn, sl = struct.unpack_from(self.LEAF_ENTRY_FMT, data, off)
                entries.append({"x": x, "y": y, "rid": (pn, sl)})
                off += self.LEAF_ENTRY_SIZE
            return {"is_leaf": True, "entries": entries, "page_id": page_id}
        else:
            entries = []
            off = self.HEADER_SIZE
            for _ in range(num_entries):
                min_x, min_y, max_x, max_y, child = struct.unpack_from(
                    self.INTERNAL_ENTRY_FMT, data, off
                )
                entries.append({
                    "mbr": (min_x, min_y, max_x, max_y),
                    "child": child,
                })
                off += self.INTERNAL_ENTRY_SIZE
            return {"is_leaf": False, "entries": entries, "page_id": page_id}

    def _write_node(self, page_id, node):
        page = bytearray(self.page_size)
        entries = node["entries"]
        struct.pack_into(self.HEADER_FMT, page, 0, int(node["is_leaf"]), len(entries))

        off = self.HEADER_SIZE
        if node["is_leaf"]:
            for e in entries:
                struct.pack_into(self.LEAF_ENTRY_FMT, page, off,
                                 e["x"], e["y"], e["rid"][0], e["rid"][1])
                off += self.LEAF_ENTRY_SIZE
        else:
            for e in entries:
                mbr = e["mbr"]
                struct.pack_into(self.INTERNAL_ENTRY_FMT, page, off,
                                 mbr[0], mbr[1], mbr[2], mbr[3], e["child"])
                off += self.INTERNAL_ENTRY_SIZE

        self._write_page_raw(page_id, page)

    # ------------------------------------------------------------------ #
    #  MBR HELPERS                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _point_mbr(x, y):
        return (x, y, x, y)

    @staticmethod
    def _mbr_area(mbr):
        return (mbr[2] - mbr[0]) * (mbr[3] - mbr[1])

    @staticmethod
    def _mbr_union(a, b):
        return (min(a[0], b[0]), min(a[1], b[1]),
                max(a[2], b[2]), max(a[3], b[3]))

    @staticmethod
    def _mbr_enlargement(mbr, new_mbr):
        union = RTree._mbr_union(mbr, new_mbr)
        return RTree._mbr_area(union) - RTree._mbr_area(mbr)

    @staticmethod
    def _mbr_contains_point(mbr, x, y):
        return mbr[0] <= x <= mbr[2] and mbr[1] <= y <= mbr[3]

    @staticmethod
    def _mbr_intersects_circle(mbr, cx, cy, radius):
        closest_x = max(mbr[0], min(cx, mbr[2]))
        closest_y = max(mbr[1], min(cy, mbr[3]))
        dx = closest_x - cx
        dy = closest_y - cy
        return (dx * dx + dy * dy) <= radius * radius

    @staticmethod
    def _min_dist_to_mbr(mbr, x, y):
        dx = max(mbr[0] - x, 0, x - mbr[2])
        dy = max(mbr[1] - y, 0, y - mbr[3])
        return math.sqrt(dx * dx + dy * dy)

    @staticmethod
    def _distance(x1, y1, x2, y2):
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    def _compute_mbr(self, node):
        if node["is_leaf"]:
            if not node["entries"]:
                return (0.0, 0.0, 0.0, 0.0)
            xs = [e["x"] for e in node["entries"]]
            ys = [e["y"] for e in node["entries"]]
            return (min(xs), min(ys), max(xs), max(ys))
        else:
            if not node["entries"]:
                return (0.0, 0.0, 0.0, 0.0)
            mbr = node["entries"][0]["mbr"]
            for e in node["entries"][1:]:
                mbr = self._mbr_union(mbr, e["mbr"])
            return mbr

    def _entry_mbr(self, entry, is_leaf):
        if is_leaf:
            return self._point_mbr(entry["x"], entry["y"])
        else:
            return entry["mbr"]

    # ------------------------------------------------------------------ #
    #  INSERT                                                              #
    # ------------------------------------------------------------------ #

    def add(self, x, y, rid):
        entry = {"x": float(x), "y": float(y), "rid": tuple(rid)}
        point_mbr = self._point_mbr(entry["x"], entry["y"])

        # Arbol vacio
        if self.root_page == -1:
            pid = self._alloc_page()
            self._write_node(pid, {
                "is_leaf": True, "entries": [entry], "page_id": pid,
            })
            self.root_page = pid
            self._save_metadata()
            return

        # Elegir la mejor hoja
        leaf, path = self._choose_leaf(point_mbr)

        # Insertar en la hoja
        leaf["entries"].append(entry)

        if len(leaf["entries"]) <= self.max_leaf_entries:
            self._write_node(leaf["page_id"], leaf)
            self._adjust_tree(path, leaf)
        else:
            # Split hoja
            new_node = self._split_node(leaf)
            self._write_node(leaf["page_id"], leaf)
            self._write_node(new_node["page_id"], new_node)
            self._adjust_tree_with_split(path, leaf, new_node)

        self._save_metadata()

    def _choose_leaf(self, mbr):
        path = []
        node = self._read_node(self.root_page)

        while not node["is_leaf"]:
            best_idx = 0
            best_enlargement = float("inf")
            best_area = float("inf")

            for i, e in enumerate(node["entries"]):
                enlargement = self._mbr_enlargement(e["mbr"], mbr)
                area = self._mbr_area(e["mbr"])
                if (enlargement < best_enlargement or
                        (enlargement == best_enlargement and area < best_area)):
                    best_enlargement = enlargement
                    best_area = area
                    best_idx = i

            path.append((node, best_idx))
            node = self._read_node(node["entries"][best_idx]["child"])

        return node, path

    # ------------------------------------------------------------------ #
    #  SPLIT (Quadratic)                                                   #
    # ------------------------------------------------------------------ #

    def _split_node(self, node):
        entries = node["entries"]
        is_leaf = node["is_leaf"]

        seed1, seed2 = self._pick_seeds(entries, is_leaf)

        group1 = [entries[seed1]]
        group2 = [entries[seed2]]
        remaining = [e for i, e in enumerate(entries) if i != seed1 and i != seed2]

        mbr1 = self._entry_mbr(group1[0], is_leaf)
        mbr2 = self._entry_mbr(group2[0], is_leaf)

        min_entries = self.min_leaf_entries if is_leaf else self.min_internal_entries

        while remaining:
            if len(group1) + len(remaining) == min_entries:
                group1.extend(remaining)
                break
            if len(group2) + len(remaining) == min_entries:
                group2.extend(remaining)
                break

            # Pick next: entrada con mayor preferencia por un grupo
            best_idx = 0
            best_diff = -1.0
            for i, e in enumerate(remaining):
                e_mbr = self._entry_mbr(e, is_leaf)
                d1 = self._mbr_enlargement(mbr1, e_mbr)
                d2 = self._mbr_enlargement(mbr2, e_mbr)
                diff = abs(d1 - d2)
                if diff > best_diff:
                    best_diff = diff
                    best_idx = i

            chosen = remaining.pop(best_idx)
            c_mbr = self._entry_mbr(chosen, is_leaf)
            d1 = self._mbr_enlargement(mbr1, c_mbr)
            d2 = self._mbr_enlargement(mbr2, c_mbr)

            if d1 < d2:
                group1.append(chosen)
                mbr1 = self._mbr_union(mbr1, c_mbr)
            elif d2 < d1:
                group2.append(chosen)
                mbr2 = self._mbr_union(mbr2, c_mbr)
            elif self._mbr_area(mbr1) <= self._mbr_area(mbr2):
                group1.append(chosen)
                mbr1 = self._mbr_union(mbr1, c_mbr)
            else:
                group2.append(chosen)
                mbr2 = self._mbr_union(mbr2, c_mbr)

        node["entries"] = group1

        new_pid = self._alloc_page()
        new_node = {
            "is_leaf": is_leaf,
            "entries": group2,
            "page_id": new_pid,
        }
        return new_node

    def _pick_seeds(self, entries, is_leaf):
        worst_waste = -float("inf")
        seed1, seed2 = 0, 1

        for i in range(len(entries)):
            mbr_i = self._entry_mbr(entries[i], is_leaf)
            for j in range(i + 1, len(entries)):
                mbr_j = self._entry_mbr(entries[j], is_leaf)
                combined = self._mbr_union(mbr_i, mbr_j)
                waste = self._mbr_area(combined) - self._mbr_area(mbr_i) - self._mbr_area(mbr_j)
                if waste > worst_waste:
                    worst_waste = waste
                    seed1, seed2 = i, j

        return seed1, seed2

    # ------------------------------------------------------------------ #
    #  ADJUST TREE                                                         #
    # ------------------------------------------------------------------ #

    def _adjust_tree(self, path, node):
        mbr = self._compute_mbr(node)
        for parent, idx in reversed(path):
            parent["entries"][idx]["mbr"] = mbr
            self._write_node(parent["page_id"], parent)
            mbr = self._compute_mbr(parent)

    def _adjust_tree_with_split(self, path, node, new_node):
        node_mbr = self._compute_mbr(node)
        new_mbr = self._compute_mbr(new_node)

        while path:
            parent, idx = path.pop()

            parent["entries"][idx]["mbr"] = node_mbr
            new_entry = {"mbr": new_mbr, "child": new_node["page_id"]}
            parent["entries"].append(new_entry)

            if len(parent["entries"]) <= self.max_internal_entries:
                self._write_node(parent["page_id"], parent)
                # Ajustar MBRs restantes hacia arriba
                mbr = self._compute_mbr(parent)
                for p, i in reversed(path):
                    p["entries"][i]["mbr"] = mbr
                    self._write_node(p["page_id"], p)
                    mbr = self._compute_mbr(p)
                return
            else:
                new_parent = self._split_node(parent)
                self._write_node(parent["page_id"], parent)
                self._write_node(new_parent["page_id"], new_parent)
                node = parent
                new_node = new_parent
                node_mbr = self._compute_mbr(parent)
                new_mbr = self._compute_mbr(new_parent)

        # Root fue splitteado -> nueva raiz
        new_root_pid = self._alloc_page()
        new_root = {
            "is_leaf": False,
            "entries": [
                {"mbr": node_mbr, "child": node["page_id"]},
                {"mbr": new_mbr, "child": new_node["page_id"]},
            ],
            "page_id": new_root_pid,
        }
        self._write_node(new_root_pid, new_root)
        self.root_page = new_root_pid

    # ------------------------------------------------------------------ #
    #  BUSQUEDA: Circular (radio)                                          #
    # ------------------------------------------------------------------ #

    def radius_search(self, cx, cy, radius, limit=0, offset=0):
        """
        Busca todos los puntos dentro de distancia `radius` desde (cx, cy).
        Retorna lista de (x, y, rid, distance) ordenada por distancia.
        """
        if self.root_page == -1:
            return []

        results = []
        stack = [self.root_page]

        while stack:
            page_id = stack.pop()
            node = self._read_node(page_id)

            if node["is_leaf"]:
                for e in node["entries"]:
                    dist = self._distance(cx, cy, e["x"], e["y"])
                    if dist <= radius:
                        results.append((e["x"], e["y"], e["rid"], dist))
            else:
                for e in node["entries"]:
                    if self._mbr_intersects_circle(e["mbr"], cx, cy, radius):
                        stack.append(e["child"])

        results.sort(key=lambda r: r[3])

        if offset:
            results = results[offset:]
        if limit:
            results = results[:limit]

        return results

    # ------------------------------------------------------------------ #
    #  BUSQUEDA: k-NN (k vecinos mas cercanos)                             #
    # ------------------------------------------------------------------ #

    def knn_search(self, qx, qy, k, limit=0, offset=0):
        """
        Busca los k vecinos mas cercanos a (qx, qy) usando min-heap.
        Retorna lista de (x, y, rid, distance) ordenada por distancia.
        """
        if self.root_page == -1 or k <= 0:
            return []

        total_needed = k + offset

        counter = 0
        heap = []
        heapq.heappush(heap, (0.0, counter, "node", self.root_page))
        counter += 1

        candidates = []

        while heap and len(candidates) < total_needed:
            dist, _, item_type, data = heapq.heappop(heap)

            if item_type == "point":
                x, y, rid = data
                candidates.append((x, y, rid, dist))
            else:
                node = self._read_node(data)
                if node["is_leaf"]:
                    for e in node["entries"]:
                        d = self._distance(qx, qy, e["x"], e["y"])
                        heapq.heappush(heap, (d, counter, "point",
                                              (e["x"], e["y"], e["rid"])))
                        counter += 1
                else:
                    for e in node["entries"]:
                        d = self._min_dist_to_mbr(e["mbr"], qx, qy)
                        heapq.heappush(heap, (d, counter, "node", e["child"]))
                        counter += 1

        results = candidates[offset:]
        if limit and len(results) > limit:
            results = results[:limit]

        return results

    # ------------------------------------------------------------------ #
    #  BUSQUEDA: Punto exacto                                              #
    # ------------------------------------------------------------------ #

    def search(self, x, y):
        """Busca RID para punto exacto (x, y). Retorna primer match o None."""
        if self.root_page == -1:
            return None

        stack = [self.root_page]
        while stack:
            page_id = stack.pop()
            node = self._read_node(page_id)

            if node["is_leaf"]:
                for e in node["entries"]:
                    if e["x"] == x and e["y"] == y:
                        return e["rid"]
            else:
                for e in node["entries"]:
                    if self._mbr_contains_point(e["mbr"], x, y):
                        stack.append(e["child"])
        return None

    def search_all(self, x, y, limit=0, offset=0):
        """Busca todos los RIDs para punto (x, y)."""
        if self.root_page == -1:
            return []

        all_results = []
        stack = [self.root_page]

        while stack:
            page_id = stack.pop()
            node = self._read_node(page_id)

            if node["is_leaf"]:
                for e in node["entries"]:
                    if e["x"] == x and e["y"] == y:
                        all_results.append((e["x"], e["y"], e["rid"], 0.0))
            else:
                for e in node["entries"]:
                    if self._mbr_contains_point(e["mbr"], x, y):
                        stack.append(e["child"])

        if offset:
            all_results = all_results[offset:]
        if limit:
            all_results = all_results[:limit]

        return all_results

    # ------------------------------------------------------------------ #
    #  DELETE                                                              #
    # ------------------------------------------------------------------ #

    def remove(self, x, y, rid=None):
        """
        Elimina un punto (x, y) del arbol.
        Si rid es especificado, solo elimina la entrada con ese RID exacto.
        Usa condense-tree con reinsercion de entradas huerfanas.
        """
        x, y = float(x), float(y)
        if self.root_page == -1:
            return False

        # Buscar con path
        path = []
        found = self._search_with_path(self.root_page, x, y, rid, path)

        if found is None:
            return False

        leaf_page_id, entry_idx = found

        # Eliminar entrada de la hoja
        leaf = self._read_node(leaf_page_id)
        leaf["entries"].pop(entry_idx)
        self._write_node(leaf_page_id, leaf)

        # Condense tree: recolectar entradas huerfanas y ajustar MBRs
        orphaned = []
        node = leaf

        while path:
            parent, child_idx = path.pop()
            is_leaf = node["is_leaf"]
            min_entries = self.min_leaf_entries if is_leaf else self.min_internal_entries

            if not node["entries"]:
                # Nodo vacio: remover del padre
                parent["entries"].pop(child_idx)
            elif len(node["entries"]) < min_entries and node["page_id"] != self.root_page:
                # Underflow: recolectar entradas y remover del padre
                orphaned.extend(self._collect_leaf_entries(node))
                parent["entries"].pop(child_idx)
            else:
                # Actualizar MBR en el padre
                parent["entries"][child_idx]["mbr"] = self._compute_mbr(node)

            self._write_node(parent["page_id"], parent)
            node = parent

        # Ajustar raiz
        root = self._read_node(self.root_page)
        if not root["entries"]:
            self.root_page = -1
        elif not root["is_leaf"] and len(root["entries"]) == 1:
            self.root_page = root["entries"][0]["child"]

        self._save_metadata()

        # Reinsertar entradas huerfanas
        for ox, oy, orid in orphaned:
            self.add(ox, oy, orid)

        return True

    def _search_with_path(self, page_id, x, y, rid, path):
        """
        Busca entrada (x, y, rid) construyendo el path.
        Retorna (leaf_page_id, entry_index) o None.
        """
        node = self._read_node(page_id)

        if node["is_leaf"]:
            for i, e in enumerate(node["entries"]):
                if e["x"] == x and e["y"] == y:
                    if rid is None or e["rid"] == tuple(rid):
                        return (page_id, i)
            return None

        for i, e in enumerate(node["entries"]):
            if self._mbr_contains_point(e["mbr"], x, y):
                path.append((node, i))
                result = self._search_with_path(e["child"], x, y, rid, path)
                if result is not None:
                    return result
                path.pop()

        return None

    def _collect_leaf_entries(self, node):
        """Recolecta todas las entradas hoja de un subarbol."""
        entries = []
        if node["is_leaf"]:
            for e in node["entries"]:
                entries.append((e["x"], e["y"], e["rid"]))
        else:
            for e in node["entries"]:
                child = self._read_node(e["child"])
                entries.extend(self._collect_leaf_entries(child))
        return entries

    # ------------------------------------------------------------------ #
    #  JSON RESPONSE (para frontend)                                       #
    # ------------------------------------------------------------------ #

    def radius_search_json(self, cx, cy, radius, limit=0, offset=0):
        """
        Busqueda circular con respuesta JSON para visualizacion.
        Rojo = punto de query, Azul = puntos resultado.
        """
        results = self.radius_search(cx, cy, radius, limit=limit, offset=offset)
        return self._format_json(cx, cy, results)

    def knn_search_json(self, qx, qy, k, limit=0, offset=0):
        """
        k-NN con respuesta JSON para visualizacion.
        Rojo = punto de query, Azul = puntos resultado.
        """
        results = self.knn_search(qx, qy, k, limit=limit, offset=offset)
        return self._format_json(qx, qy, results)

    def _format_json(self, qx, qy, results):
        return {
            "query_point": {
                "x": qx,
                "y": qy,
                "color": "red",
            },
            "results": [
                {
                    "x": r[0],
                    "y": r[1],
                    "rid": {"page": r[2][0], "slot": r[2][1]},
                    "distance": round(r[3], 6),
                    "color": "blue",
                }
                for r in results
            ],
            "total": len(results),
        }

    # ------------------------------------------------------------------ #
    #  DEBUG                                                               #
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
            pts = [(round(e["x"], 2), round(e["y"], 2)) for e in node["entries"]]
            print(f"{indent}HOJA[p{page_id}] {len(node['entries'])} pts: "
                  f"{pts[:5]}{'...' if len(pts) > 5 else ''}")
        else:
            print(f"{indent}INTERNO[p{page_id}] {len(node['entries'])} hijos")
            for e in node["entries"]:
                mbr = e["mbr"]
                print(f"{indent}  MBR=({mbr[0]:.1f},{mbr[1]:.1f})-({mbr[2]:.1f},{mbr[3]:.1f})")
                self._print_node(e["child"], level + 2)
