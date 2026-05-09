"""
SequentialFile — Page-based sequential file index.

Structure:
  Single index file with fixed-size pages (default 4096B).
  - Page 0: Metadata
  - Main pages: entries sorted by key, linked via next_page pointer
    in the page header. Binary search within each page.
  - Aux pages: overflow area for new insertions. Entries sorted
    within each page for binary search.

  When the auxiliary area reaches max_aux entries, all entries
  (main + aux) are merged into fresh sorted main pages (reconstruction).

Operations: add, search, search_all, range_search, remove.
Interface compatible with BPlusTree for integration with dbengine.
"""

import os
import struct

from dbms.utils.pagemanager import PageManager


class SequentialFile:

    # Data page header: num_entries(4) + next_page(4) = 8 bytes
    PAGE_HEADER_FMT = "=Ii"
    PAGE_HEADER_SIZE = struct.calcsize(PAGE_HEADER_FMT)

    # Metadata on page 0:
    #   num_main(4) + num_aux(4) + head_page(4) + num_pages(4)
    #   + max_aux(4) + first_aux(4)
    META_FMT = "=IIiIIi"
    META_SIZE = struct.calcsize(META_FMT)

    def __init__(self, index_file, key_format="i", page_size=4096, unique=True,
                 max_aux=None, pm=None):
        self.page_size = page_size
        self.unique = unique
        self.key_fmt = "=" + key_format
        self.key_size = struct.calcsize(self.key_fmt)
        self.val_fmt = "=ii"                         # RID: (page_num, slot)
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

    # ------------------------------------------------------------------ #
    #  DISK I/O STATS (delegados a PageManager)                            #
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    #  LOW-LEVEL PAGE I/O                                                  #
    # ------------------------------------------------------------------ #

    def _init_file(self):
        """Create index file with an empty metadata page."""
        page = bytearray(self.page_size)
        struct.pack_into(self.META_FMT, page, 0,
                         0, 0, -1, 1, self.max_aux, -1)
        self.pm.write_page(0, page)

    def _alloc_page(self):
        pid = self.num_pages
        self.num_pages += 1
        return pid

    def _load_metadata(self):
        data = self.pm.read_page(0)
        (self.num_main, self.num_aux, self.head_page,
         self.num_pages, self.max_aux, self.first_aux) = struct.unpack_from(
            self.META_FMT, data, 0)

    def _save_metadata(self):
        page = bytearray(self.page_size)
        struct.pack_into(self.META_FMT, page, 0,
                         self.num_main, self.num_aux, self.head_page,
                         self.num_pages, self.max_aux, self.first_aux)
        self.pm.write_page(0, page)

    # ------------------------------------------------------------------ #
    #  PAGE SERIALIZATION                                                  #
    # ------------------------------------------------------------------ #

    def _read_data_page(self, page_id):
        """Read a data page -> (entries, next_page)."""
        data = self.pm.read_page(page_id)
        count, next_page = struct.unpack_from(self.PAGE_HEADER_FMT, data, 0)
        entries = []
        off = self.PAGE_HEADER_SIZE
        for _ in range(count):
            key = struct.unpack_from(self.key_fmt, data, off)[0]
            off += self.key_size
            rid = struct.unpack_from(self.val_fmt, data, off)
            off += self.val_size
            entries.append((key, rid))
        return entries, next_page

    def _write_data_page(self, page_id, entries, next_page=-1):
        """Write sorted entries to a data page."""
        page = bytearray(self.page_size)
        struct.pack_into(self.PAGE_HEADER_FMT, page, 0, len(entries), next_page)
        off = self.PAGE_HEADER_SIZE
        for key, rid in entries:
            struct.pack_into(self.key_fmt, page, off, key)
            off += self.key_size
            struct.pack_into(self.val_fmt, page, off, *rid)
            off += self.val_size
        self.pm.write_page(page_id, page)

    # ------------------------------------------------------------------ #
    #  BINARY SEARCH HELPER                                                #
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    #  TRAVERSAL                                                           #
    # ------------------------------------------------------------------ #

    def _traverse_main(self):
        page_id = self.head_page
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            for entry in entries:
                yield entry
            page_id = next_page

    def _traverse_aux(self):
        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            for entry in entries:
                yield entry
            page_id = next_page

    # ------------------------------------------------------------------ #
    #  SEARCH                                                              #
    # ------------------------------------------------------------------ #

    def search(self, key):
        key = self._normalize_key(key)

        page_id = self.head_page
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if not entries:
                page_id = next_page
                continue
            if entries[-1][0] < key:
                page_id = next_page
                continue
            idx = self._bisect_left(entries, key)
            if idx < len(entries) and entries[idx][0] == key:
                return entries[idx][1]
            break

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if entries:
                idx = self._bisect_left(entries, key)
                if idx < len(entries) and entries[idx][0] == key:
                    return entries[idx][1]
            page_id = next_page

        return None

    def search_all(self, key, limit=0, offset=0):
        key = self._normalize_key(key)
        all_rids = []

        page_id = self.head_page
        found = False
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if not entries:
                page_id = next_page
                continue
            if not found and entries[-1][0] < key:
                page_id = next_page
                continue

            idx = self._bisect_left(entries, key)
            while idx < len(entries) and entries[idx][0] == key:
                found = True
                all_rids.append(entries[idx][1])
                idx += 1

            if found and idx < len(entries):
                break
            if not found and entries[0][0] > key:
                break
            page_id = next_page

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if entries:
                idx = self._bisect_left(entries, key)
                while idx < len(entries) and entries[idx][0] == key:
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

        page_id = self.head_page
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if not entries:
                page_id = next_page
                continue
            if entries[-1][0] < begin_key:
                page_id = next_page
                continue
            if entries[0][0] > end_key:
                break

            idx = self._bisect_left(entries, begin_key)
            while idx < len(entries) and entries[idx][0] <= end_key:
                candidates.append(entries[idx])
                idx += 1
            page_id = next_page

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if entries:
                idx = self._bisect_left(entries, begin_key)
                while idx < len(entries) and entries[idx][0] <= end_key:
                    candidates.append(entries[idx])
                    idx += 1
            page_id = next_page

        candidates.sort(key=lambda e: e[0])

        results = []
        for i, (_key, rid) in enumerate(candidates):
            if i < offset:
                continue
            results.append(rid)
            if limit and len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------ #
    #  ADD (INSERT)                                                        #
    # ------------------------------------------------------------------ #

    def add(self, key, value):
        key = self._normalize_key(key)

        if self.unique and self._update_existing(key, value):
            return

        self._append_to_aux(key, value)
        self.num_aux += 1
        self._save_metadata()
        self._check_reconstruct()

    def _update_existing(self, key, value):
        page_id = self.head_page
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if not entries:
                page_id = next_page
                continue
            if entries[-1][0] < key:
                page_id = next_page
                continue
            idx = self._bisect_left(entries, key)
            if idx < len(entries) and entries[idx][0] == key:
                entries[idx] = (key, value)
                self._write_data_page(page_id, entries, next_page)
                return True
            break

        page_id = self.first_aux
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if entries:
                idx = self._bisect_left(entries, key)
                if idx < len(entries) and entries[idx][0] == key:
                    entries[idx] = (key, value)
                    self._write_data_page(page_id, entries, next_page)
                    return True
            page_id = next_page

        return False

    def _append_to_aux(self, key, value):
        if self.first_aux == -1:
            pid = self._alloc_page()
            self._write_data_page(pid, [(key, value)], -1)
            self.first_aux = pid
            return

        page_id = self.first_aux
        last_id = page_id
        last_entries = []
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            last_id = page_id
            last_entries = entries
            if next_page == -1:
                break
            page_id = next_page

        if len(last_entries) < self.entries_per_page:
            idx = self._bisect_left(last_entries, key)
            last_entries.insert(idx, (key, value))
            self._write_data_page(last_id, last_entries, -1)
        else:
            new_pid = self._alloc_page()
            self._write_data_page(new_pid, [(key, value)], -1)
            self._write_data_page(last_id, last_entries, new_pid)

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
            self._save_metadata()
            self.pm.truncate(1)
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
        self._save_metadata()

        self.pm.truncate(self.num_pages)

    # ------------------------------------------------------------------ #
    #  REMOVE (DELETE)                                                     #
    # ------------------------------------------------------------------ #

    def remove(self, key, value=None):
        key = self._normalize_key(key)

        page_id = self.head_page
        prev_page_id = -1
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)
            if not entries:
                prev_page_id = page_id
                page_id = next_page
                continue
            if entries[-1][0] < key:
                prev_page_id = page_id
                page_id = next_page
                continue

            found = None
            for i, (k, rid) in enumerate(entries):
                if k == key and (value is None or rid == tuple(value)):
                    found = i
                    break

            if found is not None:
                entries.pop(found)
                if entries:
                    self._write_data_page(page_id, entries, next_page)
                else:
                    if prev_page_id == -1:
                        self.head_page = next_page
                    else:
                        prev_entries, _ = self._read_data_page(prev_page_id)
                        self._write_data_page(prev_page_id, prev_entries, next_page)
                self.num_main -= 1
                self._save_metadata()
                return True

            break

        page_id = self.first_aux
        prev_page_id = -1
        while page_id != -1:
            entries, next_page = self._read_data_page(page_id)

            found = None
            for i, (k, rid) in enumerate(entries):
                if k == key and (value is None or rid == tuple(value)):
                    found = i
                    break

            if found is not None:
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
