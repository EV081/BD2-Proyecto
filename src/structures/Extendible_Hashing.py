import os
import struct

from src.storage.pagemanager import PageManager


class ExtendibleHash:

    # Metadata (pagina 0): global_depth(4), num_buckets(4), num_entries(4)
    META_FMT = "=III"
    META_SIZE = struct.calcsize(META_FMT)

    # Bucket header: local_depth(4), count(4)
    BUCKET_HEADER_FMT = "=II"
    BUCKET_HEADER_SIZE = struct.calcsize(BUCKET_HEADER_FMT)

    def __init__(self, index_file, key_format="i", page_size=4096, unique=True,
                 bucket_capacity=None, pm=None):
        self.page_size = page_size
        self.unique = unique
        self.key_fmt = "=" + key_format
        self.key_size = struct.calcsize(self.key_fmt)
        self.val_fmt = "=ii"  # RID: (page_num, slot)
        self.val_size = struct.calcsize(self.val_fmt)
        self.entry_size = self.key_size + self.val_size

        if bucket_capacity is None:
            self.bucket_capacity = (page_size - self.BUCKET_HEADER_SIZE) // self.entry_size
        else:
            self.bucket_capacity = bucket_capacity

        # Estado en memoria
        self.global_depth = 0
        self.directory = []
        self.num_buckets = 0
        self.num_entries = 0

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

  
    #  INICIALIZACION Y METADATA                                           
    def _init_file(self):
        """Crea un archivo nuevo con depth=1, 2 buckets."""
  
        self.pm.write_page(0, bytearray(self.page_size))

        self.global_depth = 1
        self.num_buckets = 2
        self.num_entries = 0

        bucket0_page = self._create_empty_bucket(local_depth=1)
        bucket1_page = self._create_empty_bucket(local_depth=1)

        self.directory = [bucket0_page, bucket1_page]
        self._save_metadata()

    def _alloc_page(self):
        """Reserva una nueva pagina al final del archivo."""
        page_id = self.pm.num_pages()
        self.pm.write_page(page_id, bytearray(self.page_size))
        return page_id

    def _create_empty_bucket(self, local_depth):
        page_id = self._alloc_page()
        page = bytearray(self.page_size)
        struct.pack_into(self.BUCKET_HEADER_FMT, page, 0, local_depth, 0)
        self.pm.write_page(page_id, page)
        return page_id

    def _save_metadata(self):
        page = bytearray(self.page_size)
        struct.pack_into(self.META_FMT, page, 0,
                         self.global_depth, self.num_buckets, self.num_entries)
        off = self.META_SIZE
        for page_id in self.directory:
            struct.pack_into("=I", page, off, page_id)
            off += 4
        self.pm.write_page(0, page)

    def _load_metadata(self):
        data = self.pm.read_page(0)
        self.global_depth, self.num_buckets, self.num_entries = struct.unpack_from(
            self.META_FMT, data, 0)
        dir_size = 1 << self.global_depth
        self.directory = []
        off = self.META_SIZE
        for _ in range(dir_size):
            page_id = struct.unpack_from("=I", data, off)[0]
            self.directory.append(page_id)
            off += 4

    #  BUCKET OPERATIONS                                                  
    def _read_bucket(self, page_id):
        data = self.pm.read_page(page_id)
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
        page = bytearray(self.page_size)
        struct.pack_into(self.BUCKET_HEADER_FMT, page, 0, local_depth, len(entries))
        off = self.BUCKET_HEADER_SIZE
        for key, rid in entries:
            struct.pack_into(self.key_fmt, page, off, key)
            struct.pack_into(self.val_fmt, page, off + self.key_size, *rid)
            off += self.entry_size
        self.pm.write_page(page_id, page)

    
    #  HASH                                                                
    def _hash(self, key):
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
        return h & ((1 << self.global_depth) - 1)

    def _hash_full(self, key):
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

    def _normalize_key(self, key):
        if isinstance(key, str):
            key = key.encode("utf-8")
        packed = struct.pack(self.key_fmt, key)
        return struct.unpack(self.key_fmt, packed)[0]

 
    #  BUSQUEDA                                                            
    def search(self, key):
        key = self._normalize_key(key)
        idx = self._hash(key)
        bucket_page = self.directory[idx]
        _, entries = self._read_bucket(bucket_page)

        for entry_key, rid in entries:
            if entry_key == key:
                return rid
        return None

    def search_all(self, key, limit=0, offset=0):
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
        raise NotImplementedError(
            "Extendible Hashing no soporta busqueda por rango. "
            "Use full scan o un indice B+Tree/Sequential."
        )


    #  ADD (INSERT)                                                      
    def add(self, key, value):
        key = self._normalize_key(key)
        idx = self._hash(key)
        bucket_page = self.directory[idx]
        local_depth, entries = self._read_bucket(bucket_page)

        if self.unique:
            for i, (entry_key, _) in enumerate(entries):
                if entry_key == key:
                    entries[i] = (key, value)
                    self._write_bucket(bucket_page, local_depth, entries)
                    return

        if len(entries) < self.bucket_capacity:
            entries.append((key, value))
            self._write_bucket(bucket_page, local_depth, entries)
            self.num_entries += 1
            self._save_metadata()
            return

        self._split_bucket(idx, bucket_page, local_depth, entries, key, value)

    def _split_bucket(self, dir_idx, bucket_page, local_depth, entries, new_key, new_value):
        entries.append((new_key, new_value))
        self.num_entries += 1

        if local_depth == self.global_depth:
            self.global_depth += 1
            self.directory = self.directory + self.directory[:]

        new_local_depth = local_depth + 1
        new_bucket_page = self._create_empty_bucket(new_local_depth)
        self.num_buckets += 1

        entries_old = []
        entries_new = []
        bit_mask = 1 << (new_local_depth - 1)

        for entry_key, rid in entries:
            h = self._hash_full(entry_key)
            if h & bit_mask:
                entries_new.append((entry_key, rid))
            else:
                entries_old.append((entry_key, rid))

        self._write_bucket(bucket_page, new_local_depth, entries_old)
        self._write_bucket(new_bucket_page, new_local_depth, entries_new)

        for i in range(len(self.directory)):
            if self.directory[i] == bucket_page:
                h_bits = i & ((1 << new_local_depth) - 1)
                if h_bits & bit_mask:
                    self.directory[i] = new_bucket_page

        self._save_metadata()

        if len(entries_old) > self.bucket_capacity:
            idx = self._find_dir_index(bucket_page)
            self._split_bucket(idx, bucket_page, new_local_depth, entries_old[:-1],
                               entries_old[-1][0], entries_old[-1][1])
            self.num_entries -= 1
        if len(entries_new) > self.bucket_capacity:
            idx = self._find_dir_index(new_bucket_page)
            self._split_bucket(idx, new_bucket_page, new_local_depth, entries_new[:-1],
                               entries_new[-1][0], entries_new[-1][1])
            self.num_entries -= 1

    def _find_dir_index(self, bucket_page):
        for i, page in enumerate(self.directory):
            if page == bucket_page:
                return i
        return 0

  
    #  REMOVE                                                  
    def remove(self, key, value=None):
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
