import os
import struct
from src.storage.pagemanager import PageManager


class _Deleted:
    __slots__ = ('record',)

    def __init__(self, record):
        self.record = record

class SequentialFile:

    # Data page header: num_entries(4) + next_page(4) = 8 bytes
    PAGE_HEADER_FMT = "=Ii"
    PAGE_HEADER_SIZE = struct.calcsize(PAGE_HEADER_FMT)

    # Metadata on page 0:
    #   num_main(4) + num_aux(4) + head_page(4) + num_pages(4)
    #   + max_aux(4) + first_aux(4) + num_deleted(4)
    META_FMT = "=IIiIIiI"
    META_SIZE = struct.calcsize(META_FMT)

    def __init__(self, index_file, key_format="i", page_size=4096, unique=True, max_aux=None, pm=None, record_format=None, key_position=0):
        self.page_size = page_size
        self.unique = unique
        self.key_fmt = "=" + key_format
        self.key_size = struct.calcsize(self.key_fmt)

        # Modo clustered vs indice secundario
        self.clustered = record_format is not None
        self.key_position = key_position
        self.on_reconstruct = None  # callback para reconstruir indices secundarios
        self._just_reconstructed = False  # flag para evitar doble-insercion

        if self.clustered:
            self.record_struct = struct.Struct(record_format)
            # Clustered slot: 1-byte deleted flag + record data
            self.entry_size = 1 + self.record_struct.size
        else:
            self.record_struct = None
            self.val_fmt = "=ii" # RID: (page_num, slot)
            self.val_size = struct.calcsize(self.val_fmt)
            self.entry_size = self.key_size + self.val_size

        self.entries_per_page = (page_size - self.PAGE_HEADER_SIZE) // self.entry_size

        if max_aux is None:
            max_aux = self.entries_per_page
        self.max_aux = max_aux

        # In-memory state
        self.num_main = 0
        self.num_aux = 0
        self.head_page = -1      # first main page
        self.num_pages = 1       # page 0 = metadata
        self.first_aux = -1      # first aux page
        self.num_deleted = 0     # soft-deleted entries (clustered mode)
        self._last_aux = -1      # cache: last aux page (avoids traversal)

        # PageManager para I/O de paginas
        if pm is not None:
            self.pm = pm
        else:
            index_dir = os.path.join(
                os.path.dirname(os.path.abspath(index_file)), "indexes")
            os.makedirs(index_dir, exist_ok=True)
            index_path = os.path.join(index_dir, os.path.basename(index_file))
            self.pm = PageManager(index_path, page_size)

        self.index_file = self.pm.path

        if self.pm.num_pages() > 0:
            self._load_metadata()
        else:
            self._init_file()

    #  DISK I/O STATS (delegados a PageManager)                            
    @property
    def disk_reads(self):
        return self.pm.disk_reads

    @disk_reads.setter
    def disk_reads(self, val):
        self.pm.disk_reads = val

    @property
    def disk_writes(self):
        return self.pm.disk_writes

    @disk_writes.setter
    def disk_writes(self, val):
        self.pm.disk_writes = val

    def reset_stats(self):
        self.pm.reset_stats()

    #  LOW-LEVEL PAGE I/O                                                  
    def _init_file(self):
        page = bytearray(self.page_size)
        struct.pack_into(self.META_FMT, page, 0, 0, 0, -1, 1, self.max_aux, -1, 0)
        self.pm.write_page(0, page)

    def _alloc_page(self):
        pid = self.num_pages
        self.num_pages += 1
        return pid

    def _load_metadata(self):
        data = self.pm.read_page(0)
        (self.num_main, self.num_aux, self.head_page,
        self.num_pages, self.max_aux, self.first_aux,
        self.num_deleted) = struct.unpack_from(self.META_FMT, data, 0)

    def _save_metadata(self):
        page = bytearray(self.page_size)
        struct.pack_into(self.META_FMT, page, 0,
                        self.num_main, self.num_aux, self.head_page,
                        self.num_pages, self.max_aux, self.first_aux,
                        self.num_deleted)
        self.pm.write_page(0, page)

    #  PAGE SERIALIZATION
    def _read_data_page(self, page_id):
        data = self.pm.read_page(page_id)
        count, next_page = struct.unpack_from(self.PAGE_HEADER_FMT, data, 0)
        entries = []
        off = self.PAGE_HEADER_SIZE
        for _ in range(count):
            if self.clustered:
                flag = data[off]
                off += 1
                record = self.record_struct.unpack_from(data, off)
                key = record[self.key_position]
                if flag == 1:
                    entries.append((key, _Deleted(record)))
                else:
                    entries.append((key, record))
                off += self.record_struct.size
            else:
                key = struct.unpack_from(self.key_fmt, data, off)[0]
                off += self.key_size
                rid = struct.unpack_from(self.val_fmt, data, off)
                off += self.val_size
                entries.append((key, rid))
        return entries, next_page

    def _write_data_page(self, page_id, entries, next_page=-1):
        page = bytearray(self.page_size)
        struct.pack_into(self.PAGE_HEADER_FMT, page, 0, len(entries), next_page)
        off = self.PAGE_HEADER_SIZE
        for key, val in entries:
            if self.clustered:
                if isinstance(val, _Deleted):
                    page[off] = 1  # deleted flag
                    off += 1
                    self.record_struct.pack_into(page, off, *val.record)
                else:
                    page[off] = 0  # active flag
                    off += 1
                    self.record_struct.pack_into(page, off, *val)
                off += self.record_struct.size
            else:
                struct.pack_into(self.key_fmt, page, off, key)
                off += self.key_size
                struct.pack_into(self.val_fmt, page, off, *val)
                off += self.val_size
        self.pm.write_page(page_id, page)

    #  BINARY SEARCH HELPER                                                
    @staticmethod
    def _bisect_left(entries, key):
        lo, hi = 0, len(entries)
        while lo < hi:
            mid = (lo + hi) // 2
            if entries[mid][0] < key:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _normalize_key(self, key):
        if isinstance(key, str):
            key = key.encode("utf-8")
        packed = struct.pack(self.key_fmt, key)
        return struct.unpack(self.key_fmt, packed)[0]

    #  BINARY SEARCH OVER CONTIGUOUS MAIN PAGES                            
    def _num_main_pages(self):
        if self.head_page == -1:
            return 0
        if self.first_aux != -1:
            return self.first_aux - self.head_page
        return self.num_pages - self.head_page

    def _find_main_page(self, key):
        nmp = self._num_main_pages()
        if nmp == 0:
            return None
        lo = self.head_page
        hi = lo + nmp - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            entries, next_page = self._read_data_page(mid)
            if not entries:
                return None
            if key < entries[0][0]:
                hi = mid - 1
            elif key > entries[-1][0]:
                lo = mid + 1
            else:
                return (mid, entries, next_page)
        return None

    def _find_first_main_page_ge(self, key):
        nmp = self._num_main_pages()
        if nmp == 0:
            return None
        lo = self.head_page
        hi = lo + nmp - 1
        result = None
        while lo <= hi:
            mid = (lo + hi) // 2
            entries, _ = self._read_data_page(mid)
            if not entries:
                lo = mid + 1
                continue
            if entries[-1][0] >= key:
                result = mid
                hi = mid - 1
            else:
                lo = mid + 1
        return result

    #  TRAVERSAL                                                           
    def _traverse_main(self):
        page_id = self.head_page
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            for entry in entries:
                if self.clustered and isinstance(entry[1], _Deleted):
                    continue
                yield entry
            page_id = next_page

    def _traverse_aux(self):
        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            for entry in entries:
                if self.clustered and isinstance(entry[1], _Deleted):
                    continue
                yield entry
            page_id = next_page

    #  CLUSTERED MODE: HeapFile-compatible interface                        
    def records_per_page(self):
        return self.entries_per_page

    def read_record(self, page_id, slot):
        entries, _ = self._read_data_page(page_id)
        if slot < len(entries):
            val = entries[slot][1]
            if isinstance(val, _Deleted):
                return None
            return val
        return None

    def add_record(self, record):
        key = record[self.key_position]
        key = self._normalize_key(key)

        loc = self._update_existing(key, record)
        if self.unique and loc:
            return loc

        loc = self._append_to_aux(key, record)
        self.num_aux += 1
        self._save_metadata()
        self._check_reconstruct()

        if self._just_reconstructed:
            return self._find_location(key)
        return loc

    def delete_record(self, page_id, slot):

        entries, next_page = self._read_data_page(page_id)
        if slot < len(entries):
            key, val = entries[slot]
            if isinstance(val, _Deleted):
                return  # Ya eliminado
            entries[slot] = (key, _Deleted(val))
            self._write_data_page(page_id, entries, next_page)
            self.num_deleted += 1
            self._save_metadata()

    def iter_all_records(self):
        page_id = self.head_page
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            for slot, (key, record) in enumerate(entries):
                if isinstance(record, _Deleted):
                    continue
                yield (page_id, slot, record)
            page_id = next_page

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            for slot, (key, record) in enumerate(entries):
                if isinstance(record, _Deleted):
                    continue
                yield (page_id, slot, record)
            page_id = next_page

    def _find_location(self, key):
        result = self._find_main_page(key)
        if result is not None:
            page_id, entries, _ = result
            idx = self._bisect_left(entries, key)
            if idx < len(entries) and entries[idx][0] == key:
                if not isinstance(entries[idx][1], _Deleted):
                    return (page_id, idx)

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if entries:
                idx = self._bisect_left(entries, key)
                if idx < len(entries) and entries[idx][0] == key:
                    if not isinstance(entries[idx][1], _Deleted):
                        return (page_id, idx)
            page_id = next_page

        return (-1, -1)

    def _is_main_page(self, target_page_id):
        if self.head_page == -1:
            return False
        return self.head_page <= target_page_id < self.head_page + self._num_main_pages()

    #  SEARCH                                                              
    def search(self, key):
        key = self._normalize_key(key)

        result = self._find_main_page(key)
        if result is not None:
            _, entries, _ = result
            idx = self._bisect_left(entries, key)
            if idx < len(entries) and entries[idx][0] == key:
                if not isinstance(entries[idx][1], _Deleted):
                    return entries[idx][1]

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if entries:
                idx = self._bisect_left(entries, key)
                if idx < len(entries) and entries[idx][0] == key:
                    if not isinstance(entries[idx][1], _Deleted):
                        return entries[idx][1]
            page_id = next_page

        return None

    def search_all(self, key, limit=0, offset=0):
        key = self._normalize_key(key)
        all_rids = []

        start = self._find_first_main_page_ge(key)
        if start is not None:
            nmp = self._num_main_pages()
            end_page = self.head_page + nmp
            page_id = start
            while page_id < end_page:
                entries, _ = self._read_data_page(page_id)
                if not entries or entries[0][0] > key:
                    break
                idx = self._bisect_left(entries, key)
                while idx < len(entries) and entries[idx][0] == key:
                    if not isinstance(entries[idx][1], _Deleted):
                        all_rids.append(entries[idx][1])
                    idx += 1
                page_id += 1

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if entries:
                idx = self._bisect_left(entries, key)
                while idx < len(entries) and entries[idx][0] == key:
                    if not isinstance(entries[idx][1], _Deleted):
                        all_rids.append(entries[idx][1])
                    idx += 1
            page_id = next_page

        if offset:
            all_rids = all_rids[offset:]
        if limit:
            all_rids = all_rids[:limit]
        return all_rids

    def range_search(self, begin_key, end_key, limit=0, offset=0):
        begin_key = self._normalize_key(begin_key)
        end_key = self._normalize_key(end_key)
        candidates = []

        start = self._find_first_main_page_ge(begin_key)
        if start is not None:
            nmp = self._num_main_pages()
            end_page = self.head_page + nmp
            page_id = start
            while page_id < end_page:
                entries, _ = self._read_data_page(page_id)
                if not entries or entries[0][0] > end_key:
                    break
                idx = self._bisect_left(entries, begin_key)
                while idx < len(entries) and entries[idx][0] <= end_key:
                    if not isinstance(entries[idx][1], _Deleted):
                        candidates.append(entries[idx])
                    idx += 1
                page_id += 1

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if entries:
                idx = self._bisect_left(entries, begin_key)
                while idx < len(entries) and entries[idx][0] <= end_key:
                    if not isinstance(entries[idx][1], _Deleted):
                        candidates.append(entries[idx])
                    idx += 1
            page_id = next_page

        candidates.sort(key=lambda e: e[0])

        results = []
        for i, (_key, val) in enumerate(candidates):
            if i < offset:
                continue
            results.append(val)
            if limit and len(results) >= limit:
                break
        return results

    #  ADD (INSERT)                                                        
    def add(self, key, value):
        key = self._normalize_key(key)

        if self.unique and self._update_existing(key, value):
            return

        self._append_to_aux(key, value)
        self.num_aux += 1
        self._save_metadata()
        self._check_reconstruct()

    def _update_existing(self, key, value):
        result = self._find_main_page(key)
        if result is not None:
            page_id, entries, next_page = result
            idx = self._bisect_left(entries, key)
            if idx < len(entries) and entries[idx][0] == key:
                if not (self.clustered and isinstance(entries[idx][1], _Deleted)):
                    entries[idx] = (key, value)
                    self._write_data_page(page_id, entries, next_page)
                    return (page_id, idx)

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if entries:
                idx = self._bisect_left(entries, key)
                if idx < len(entries) and entries[idx][0] == key:
                    if not (self.clustered and isinstance(entries[idx][1], _Deleted)):
                        entries[idx] = (key, value)
                        self._write_data_page(page_id, entries, next_page)
                        return (page_id, idx)
            page_id = next_page

        return None

    def _append_to_aux(self, key, value):
        if self.first_aux == -1:
            pid = self._alloc_page()
            self._write_data_page(pid, [(key, value)], -1)
            self.first_aux = pid
            self._last_aux = pid
            return (pid, 0)

        # Recorre una vez para encontrar la última página auxiliar y luego almacena en caché.
        if self._last_aux == -1:
            page_id = self.first_aux
            while page_id != -1:
                _, next_page = self._read_data_page(page_id)
                if next_page == -1:
                    self._last_aux = page_id
                    break
                page_id = next_page

        last_id = self._last_aux
        last_entries, _ = self._read_data_page(last_id)

        if len(last_entries) < self.entries_per_page:
            idx = self._bisect_left(last_entries, key)
            last_entries.insert(idx, (key, value))
            self._write_data_page(last_id, last_entries, -1)
            return (last_id, idx)
        else:
            new_pid = self._alloc_page()
            self._write_data_page(new_pid, [(key, value)], -1)
            self._write_data_page(last_id, last_entries, new_pid)
            self._last_aux = new_pid
            return (new_pid, 0)

    def _check_reconstruct(self):
        if self.num_aux >= self.max_aux:
            self._reconstruct()

    def _reconstruct(self):
        all_entries = []
        for entry in self._traverse_main():
            all_entries.append(entry)
        for entry in self._traverse_aux():
            all_entries.append(entry)
        all_entries.sort(key=lambda e: e[0])

        self.num_pages = 1

        if not all_entries:
            self.num_main = 0
            self.num_aux = 0
            self.head_page = -1
            self.first_aux = -1
            self._last_aux = -1
            self.num_deleted = 0
            self._save_metadata()
            self.pm.truncate(1)
            if self.clustered and self.on_reconstruct:
                self.on_reconstruct()
            return

        chunks = []
        for i in range(0, len(all_entries), self.entries_per_page):
            chunks.append(all_entries[i:i + self.entries_per_page])

        page_ids = [self._alloc_page() for _ in chunks]

        for i, (chunk, pid) in enumerate(zip(chunks, page_ids)):
            nxt = page_ids[i + 1] if i + 1 < len(page_ids) else -1
            self._write_data_page(pid, chunk, nxt)

        self.head_page = page_ids[0]
        self.num_main = len(all_entries)
        self.num_aux = 0
        self.first_aux = -1
        self._last_aux = -1
        self.num_deleted = 0  # Todas las entradas eliminadas han desaparecido
        self._save_metadata()

        self.pm.truncate(self.num_pages)

        # Notificar al DataBase para reconstruir indices secundarios
        if self.clustered and self.on_reconstruct:
            self._just_reconstructed = True
            self.on_reconstruct()

    #  REMOVE (DELETE)                                                   
    def remove(self, key, value=None):
        key = self._normalize_key(key)
        result = self._find_main_page(key)
        if result is not None:
            page_id, entries, next_page = result

            found = None
            for i, (k, val) in enumerate(entries):
                if k == key:
                    if self.clustered:
                        if not isinstance(val, _Deleted):
                            found = i
                            break
                    elif value is None or val == tuple(value):
                        found = i
                        break

            if found is not None:
                if self.clustered:
                    k_found, v_found = entries[found]
                    entries[found] = (k_found, _Deleted(v_found))
                    self._write_data_page(page_id, entries, next_page)
                    self.num_deleted += 1
                    self._save_metadata()
                    return True
                else:
                    entries.pop(found)
                    if entries:
                        self._write_data_page(page_id, entries, next_page)
                    else:
                        prev_page_id = page_id - 1 if page_id > self.head_page else -1
                        if prev_page_id == -1:
                            self.head_page = next_page
                        else:
                            prev_entries, _ = self._read_data_page(prev_page_id)
                            self._write_data_page(prev_page_id, prev_entries, next_page)
                    self.num_main -= 1
                    self._save_metadata()
                    return True

        page_id = self.first_aux
        prev_page_id = -1
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)

            found = None
            for i, (k, val) in enumerate(entries):
                if k == key:
                    if self.clustered:
                        if not isinstance(val, _Deleted):
                            found = i
                            break
                    elif value is None or val == tuple(value):
                        found = i
                        break

            if found is not None:
                if self.clustered:
                    k_found, v_found = entries[found]
                    entries[found] = (k_found, _Deleted(v_found))
                    self._write_data_page(page_id, entries, next_page)
                    self.num_deleted += 1
                    self._save_metadata()
                    return True
                else:
                    entries.pop(found)
                    if entries:
                        self._write_data_page(page_id, entries, next_page)
                    else:
                        if prev_page_id == -1:
                            self.first_aux = next_page
                        else:
                            prev_entries, _ = self._read_data_page(prev_page_id)
                            self._write_data_page(prev_page_id, prev_entries, next_page)
                    self.num_aux -= 1
                    self._save_metadata()
                    return True

            prev_page_id = page_id
            page_id = next_page

        return False

    #  COMPACTION                                                          
    def compact(self):
        if self.num_deleted > 0:
            self._reconstruct()
