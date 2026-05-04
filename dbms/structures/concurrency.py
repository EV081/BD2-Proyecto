import os
import threading
import time
from enum import Enum

from dbms.structures.bplus import BPlusTree


# ===================================================================== #
#  TIPOS Y EXCEPCIONES                                                   #
# ===================================================================== #

class LockType(Enum):
    SHARED = "S"
    EXCLUSIVE = "X"


class DeadlockError(Exception):
    pass


class LockTimeoutError(Exception):
    pass


# ===================================================================== #
#  PAGE LOCK MANAGER                                                      #
# ===================================================================== #

class PageLockManager:
    """
    Gestor de bloqueos a nivel de pagina.
    - Shared (S): multiples lectores simultaneos.
    - Exclusive (X): un solo escritor, sin lectores.
    - Upgrade S->X si el TX es el unico holder.
    - Deteccion de deadlocks via grafo wait-for (BFS).
    - Timeout configurable.
    """

    def __init__(self, timeout=5.0):
        self.timeout = timeout
        self._cond = threading.Condition(threading.Lock())
        # {page_id: {"type": LockType, "holders": set(tx_id)}}
        self._page_locks = {}
        # {tx_id: {page_id: LockType}}
        self._tx_locks = {}
        # wait-for graph: {tx_id: set(tx_ids que lo bloquean)}
        self._wait_for = {}

    def acquire(self, tx_id, page_id, lock_type):
        """
        Adquiere un lock sobre una pagina.
        Bloquea hasta que se conceda, o lanza DeadlockError/LockTimeoutError.
        """
        deadline = time.time() + self.timeout

        with self._cond:
            while True:
                # Ya tenemos lock suficiente?
                if self._already_holds(tx_id, page_id, lock_type):
                    return True

                # Intentar upgrade S -> X
                if self._try_upgrade(tx_id, page_id, lock_type):
                    return True

                # Intentar conceder
                if self._can_grant(page_id, tx_id, lock_type):
                    self._grant(page_id, tx_id, lock_type)
                    self._wait_for.pop(tx_id, None)
                    return True

                # Registrar espera
                blockers = self._get_blockers(page_id, tx_id)
                self._wait_for[tx_id] = blockers

                # Detectar deadlock
                if self._has_cycle(tx_id):
                    self._wait_for.pop(tx_id, None)
                    raise DeadlockError(
                        f"TX{tx_id}: deadlock detectado esperando page {page_id}"
                    )

                # Verificar timeout
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._wait_for.pop(tx_id, None)
                    raise LockTimeoutError(
                        f"TX{tx_id}: timeout esperando page {page_id}"
                    )

                self._cond.wait(timeout=min(remaining, 0.05))

    def release(self, tx_id, page_id):
        """Libera el lock de un TX sobre una pagina."""
        with self._cond:
            if page_id in self._page_locks:
                info = self._page_locks[page_id]
                info["holders"].discard(tx_id)
                if not info["holders"]:
                    del self._page_locks[page_id]
            if tx_id in self._tx_locks:
                self._tx_locks[tx_id].pop(page_id, None)
            self._cond.notify_all()

    def release_all(self, tx_id):
        """Libera todos los locks de un TX (commit/abort)."""
        with self._cond:
            if tx_id in self._tx_locks:
                for pid in list(self._tx_locks[tx_id]):
                    if pid in self._page_locks:
                        self._page_locks[pid]["holders"].discard(tx_id)
                        if not self._page_locks[pid]["holders"]:
                            del self._page_locks[pid]
                del self._tx_locks[tx_id]
            self._wait_for.pop(tx_id, None)
            self._cond.notify_all()

    def get_locks_held(self, tx_id):
        """Retorna dict {page_id: LockType} de locks del TX."""
        with self._cond:
            return dict(self._tx_locks.get(tx_id, {}))

    # ---- internos ----

    def _already_holds(self, tx_id, page_id, lock_type):
        if tx_id not in self._tx_locks:
            return False
        if page_id not in self._tx_locks[tx_id]:
            return False
        held = self._tx_locks[tx_id][page_id]
        if held == LockType.EXCLUSIVE:
            return True
        if lock_type == LockType.SHARED:
            return True
        return False

    def _try_upgrade(self, tx_id, page_id, lock_type):
        """Upgrade S -> X si somos el unico holder."""
        if lock_type != LockType.EXCLUSIVE:
            return False
        if tx_id not in self._tx_locks or page_id not in self._tx_locks[tx_id]:
            return False
        if self._tx_locks[tx_id][page_id] != LockType.SHARED:
            return False
        info = self._page_locks.get(page_id)
        if info and len(info["holders"]) == 1 and tx_id in info["holders"]:
            info["type"] = LockType.EXCLUSIVE
            self._tx_locks[tx_id][page_id] = LockType.EXCLUSIVE
            return True
        return False

    def _can_grant(self, page_id, tx_id, lock_type):
        if page_id not in self._page_locks:
            return True
        info = self._page_locks[page_id]
        if lock_type == LockType.SHARED:
            return info["type"] == LockType.SHARED
        return not info["holders"]

    def _grant(self, page_id, tx_id, lock_type):
        if page_id not in self._page_locks:
            self._page_locks[page_id] = {"type": lock_type, "holders": set()}
        info = self._page_locks[page_id]
        info["holders"].add(tx_id)
        if lock_type == LockType.EXCLUSIVE:
            info["type"] = LockType.EXCLUSIVE
        self._tx_locks.setdefault(tx_id, {})[page_id] = lock_type

    def _get_blockers(self, page_id, tx_id):
        if page_id in self._page_locks:
            return self._page_locks[page_id]["holders"] - {tx_id}
        return set()

    def _has_cycle(self, start_tx):
        """BFS en el grafo wait-for buscando un ciclo que incluya start_tx."""
        visited = set()
        queue = list(self._wait_for.get(start_tx, set()))
        while queue:
            tx = queue.pop(0)
            if tx == start_tx:
                return True
            if tx in visited:
                continue
            visited.add(tx)
            queue.extend(self._wait_for.get(tx, set()))
        return False


# ===================================================================== #
#  TRANSACTION LOG                                                        #
# ===================================================================== #

class TransactionLog:
    """Registro thread-safe de operaciones."""

    def __init__(self):
        self._lock = threading.Lock()
        self.entries = []

    def log(self, tx_id, operation, detail=""):
        with self._lock:
            ts = time.time()
            entry = {
                "time": ts,
                "tx_id": tx_id,
                "op": operation,
                "detail": detail,
            }
            self.entries.append(entry)

    def format(self):
        lines = []
        for e in self.entries:
            t = time.strftime("%H:%M:%S", time.localtime(e["time"]))
            ms = f".{int(e['time'] * 1000) % 1000:03d}"
            lines.append(f"[TX{e['tx_id']}] {t}{ms} {e['op']} {e['detail']}")
        return "\n".join(lines)

    def clear(self):
        with self._lock:
            self.entries.clear()

    def find_conflicts(self):
        """
        Analiza el log para identificar conflictos potenciales.
        Un conflicto ocurre cuando dos TX acceden a la misma pagina
        y al menos uno es escritura.
        """
        # Agrupar accesos por pagina
        page_accesses = {}
        for e in self.entries:
            if e["op"] in ("READ", "WRITE") and "page=" in e["detail"]:
                pid = int(e["detail"].split("page=")[1])
                page_accesses.setdefault(pid, []).append(e)

        conflicts = []
        for pid, accesses in page_accesses.items():
            tx_ids = set(a["tx_id"] for a in accesses)
            has_write = any(a["op"] == "WRITE" for a in accesses)
            if len(tx_ids) > 1 and has_write:
                conflicts.append({
                    "page": pid,
                    "transactions": tx_ids,
                    "type": "W-W" if all(a["op"] == "WRITE" for a in accesses if a["tx_id"] in tx_ids)
                            else "R-W",
                })
        return conflicts


# ===================================================================== #
#  CONCURRENT B+ TREE                                                     #
# ===================================================================== #

class ConcurrentBPlusTree(BPlusTree):
    """
    B+ Tree con soporte de concurrencia.
    Intercepta lecturas/escrituras de paginas para adquirir locks
    automaticamente segun el tx_id del hilo actual.
    """

    def __init__(self, index_file, lock_manager, tx_log, **kwargs):
        self._lock_mgr = lock_manager
        self._tx_log = tx_log
        self._local = threading.local()
        self._io_lock = threading.Lock()
        self._meta_lock = threading.Lock()
        super().__init__(index_file, **kwargs)

    # ---- thread-local tx_id ----

    def _get_tx(self):
        return getattr(self._local, "tx_id", None)

    def _set_tx(self, tx_id):
        self._local.tx_id = tx_id

    # ---- override acceso a disco ----

    def _read_page_raw(self, page_id):
        tx_id = self._get_tx()
        if tx_id is not None:
            self._lock_mgr.acquire(tx_id, page_id, LockType.SHARED)
            self._tx_log.log(tx_id, "LOCK_S", f"page={page_id}")

        with self._io_lock:
            self.disk_reads += 1
            with open(self.index_file, "rb") as f:
                f.seek(page_id * self.page_size)
                data = f.read(self.page_size)

        if tx_id is not None:
            self._tx_log.log(tx_id, "READ", f"page={page_id}")
        return data

    def _write_page_raw(self, page_id, data):
        tx_id = self._get_tx()
        if tx_id is not None:
            self._lock_mgr.acquire(tx_id, page_id, LockType.EXCLUSIVE)
            self._tx_log.log(tx_id, "LOCK_X", f"page={page_id}")

        with self._io_lock:
            self.disk_writes += 1
            needed = (page_id + 1) * self.page_size
            file_size = (
                os.path.getsize(self.index_file)
                if os.path.exists(self.index_file) else 0
            )
            if file_size < needed:
                with open(self.index_file, "ab") as f:
                    f.write(b"\x00" * (needed - file_size))
            with open(self.index_file, "r+b") as f:
                f.seek(page_id * self.page_size)
                f.write(data)

        if tx_id is not None:
            self._tx_log.log(tx_id, "WRITE", f"page={page_id}")

    def _alloc_page(self):
        with self._meta_lock:
            pid = self.num_pages
            self.num_pages += 1
            return pid

    def _save_metadata(self):
        with self._meta_lock:
            super()._save_metadata()

    def _load_metadata(self):
        with self._meta_lock:
            super()._load_metadata()


# ===================================================================== #
#  TRANSACTION                                                            #
# ===================================================================== #

class Transaction:
    """
    Transaccion sobre un ConcurrentBPlusTree.
    Protocolo: Strict 2PL (locks se liberan solo en commit/abort).
    """
    _counter = 0
    _counter_lock = threading.Lock()

    def __init__(self, tree, lock_manager, tx_log):
        with Transaction._counter_lock:
            Transaction._counter += 1
            self.tx_id = Transaction._counter

        self.tree = tree
        self.lock_mgr = lock_manager
        self.log = tx_log
        self.active = True
        self.log.log(self.tx_id, "BEGIN")

    def search(self, key):
        """Busqueda exacta dentro de la transaccion."""
        self._check_active()
        self.tree._set_tx(self.tx_id)
        self.log.log(self.tx_id, "SEARCH", f"key={key}")
        try:
            result = self.tree.search(key)
            self.log.log(self.tx_id, "FOUND" if result else "NOT_FOUND", f"key={key}")
            return result
        except (DeadlockError, LockTimeoutError) as e:
            self.log.log(self.tx_id, "ERROR", str(e))
            self.abort()
            raise
        finally:
            self.tree._set_tx(None)

    def range_search(self, begin, end):
        """Busqueda por rango dentro de la transaccion."""
        self._check_active()
        self.tree._set_tx(self.tx_id)
        self.log.log(self.tx_id, "RANGE_SEARCH", f"[{begin},{end}]")
        try:
            results = self.tree.range_search(begin, end)
            self.log.log(self.tx_id, "RANGE_RESULT", f"count={len(results)}")
            return results
        except (DeadlockError, LockTimeoutError) as e:
            self.log.log(self.tx_id, "ERROR", str(e))
            self.abort()
            raise
        finally:
            self.tree._set_tx(None)

    def add(self, key, value):
        """Insercion dentro de la transaccion."""
        self._check_active()
        self.tree._set_tx(self.tx_id)
        self.log.log(self.tx_id, "INSERT", f"key={key} val={value}")
        try:
            self.tree.add(key, value)
            self.log.log(self.tx_id, "INSERT_OK", f"key={key}")
        except (DeadlockError, LockTimeoutError) as e:
            self.log.log(self.tx_id, "ERROR", str(e))
            self.abort()
            raise
        finally:
            self.tree._set_tx(None)

    def remove(self, key):
        """Eliminacion dentro de la transaccion."""
        self._check_active()
        self.tree._set_tx(self.tx_id)
        self.log.log(self.tx_id, "DELETE", f"key={key}")
        try:
            ok = self.tree.remove(key)
            self.log.log(self.tx_id, "DELETE_OK" if ok else "DELETE_NOTFOUND", f"key={key}")
            return ok
        except (DeadlockError, LockTimeoutError) as e:
            self.log.log(self.tx_id, "ERROR", str(e))
            self.abort()
            raise
        finally:
            self.tree._set_tx(None)

    def commit(self):
        """Confirma la transaccion y libera todos los locks."""
        if not self.active:
            return
        self.log.log(self.tx_id, "COMMIT")
        self.lock_mgr.release_all(self.tx_id)
        self.active = False

    def abort(self):
        """Aborta la transaccion y libera todos los locks."""
        if not self.active:
            return
        self.log.log(self.tx_id, "ABORT")
        self.lock_mgr.release_all(self.tx_id)
        self.active = False

    def _check_active(self):
        if not self.active:
            raise RuntimeError(f"TX{self.tx_id} ya finalizo")

    @staticmethod
    def reset_counter():
        with Transaction._counter_lock:
            Transaction._counter = 0
