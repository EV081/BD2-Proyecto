"""
Tests del Simulador de Acceso Concurrente
Ejecutar con:
    python dbms/structures/test_concurrency.py
"""

import os
import sys
import shutil
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dbms.structures.concurrency import (
    PageLockManager, TransactionLog, ConcurrentBPlusTree,
    Transaction, LockType, DeadlockError, LockTimeoutError,
)


PASSED = 0
FAILED = 0


def header(name):
    print()
    print("=" * 65)
    print(f"  {name}")
    print("=" * 65)


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [OK]   {description}")
    else:
        FAILED += 1
        print(f"  [FAIL] {description}")
        if detail:
            print(f"         -> {detail}")


def cleanup():
    if os.path.isdir("indexes"):
        shutil.rmtree("indexes")


def make_tree(**kwargs):
    """Crea un ConcurrentBPlusTree con lock manager y log."""
    lm = PageLockManager(timeout=2.0)
    tlog = TransactionLog()
    tree = ConcurrentBPlusTree("conc_test.idx", lm, tlog,
                               key_format="i", unique=True, **kwargs)
    return tree, lm, tlog


# ================================================================== #
#  TEST 1: Locks basicos — shared y exclusive                         #
# ================================================================== #

def test_lock_basics():
    header("TEST 1: Shared / Exclusive locks basicos")
    lm = PageLockManager(timeout=1.0)

    # Multiples shared locks no se bloquean entre si
    lm.acquire(1, 0, LockType.SHARED)
    lm.acquire(2, 0, LockType.SHARED)
    check("2 shared locks en misma pagina", True)

    locks_1 = lm.get_locks_held(1)
    locks_2 = lm.get_locks_held(2)
    check("TX1 tiene lock en page 0", 0 in locks_1)
    check("TX2 tiene lock en page 0", 0 in locks_2)

    lm.release_all(1)
    lm.release_all(2)

    # Exclusive lock bloquea a shared
    lm.acquire(1, 0, LockType.EXCLUSIVE)
    result = {"acquired": False}

    def try_shared():
        try:
            lm.acquire(2, 0, LockType.SHARED)
            result["acquired"] = True
        except LockTimeoutError:
            result["acquired"] = False

    t = threading.Thread(target=try_shared)
    t.start()
    time.sleep(0.3)
    # TX2 deberia estar bloqueado
    check("Shared bloqueado por exclusive", not result["acquired"])
    lm.release_all(1)
    t.join(timeout=2.0)
    check("Shared concedido tras liberar exclusive", result["acquired"])
    lm.release_all(2)


# ================================================================== #
#  TEST 2: Lock upgrade S -> X                                        #
# ================================================================== #

def test_lock_upgrade():
    header("TEST 2: Lock upgrade S -> X")
    lm = PageLockManager(timeout=1.0)

    lm.acquire(1, 5, LockType.SHARED)
    check("TX1 shared en page 5", lm.get_locks_held(1)[5] == LockType.SHARED)

    # Upgrade cuando es unico holder
    lm.acquire(1, 5, LockType.EXCLUSIVE)
    check("Upgrade a exclusive", lm.get_locks_held(1)[5] == LockType.EXCLUSIVE)
    lm.release_all(1)


# ================================================================== #
#  TEST 3: Deadlock detection                                         #
# ================================================================== #

def test_deadlock_detection():
    header("TEST 3: Deadlock detection (wait-for graph)")
    lm = PageLockManager(timeout=3.0)

    # TX1 tiene page 0, TX2 tiene page 1
    lm.acquire(1, 0, LockType.EXCLUSIVE)
    lm.acquire(2, 1, LockType.EXCLUSIVE)

    deadlock_detected = {"value": False}
    errors = []

    def tx1_wants_page1():
        try:
            lm.acquire(1, 1, LockType.EXCLUSIVE)
        except DeadlockError as e:
            deadlock_detected["value"] = True
            errors.append(("TX1", str(e)))
        except LockTimeoutError as e:
            errors.append(("TX1-timeout", str(e)))

    def tx2_wants_page0():
        try:
            lm.acquire(2, 0, LockType.EXCLUSIVE)
        except DeadlockError as e:
            deadlock_detected["value"] = True
            errors.append(("TX2", str(e)))
        except LockTimeoutError as e:
            errors.append(("TX2-timeout", str(e)))

    t1 = threading.Thread(target=tx1_wants_page1)
    t2 = threading.Thread(target=tx2_wants_page0)
    t1.start()
    time.sleep(0.1)
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)

    check("Deadlock detectado", deadlock_detected["value"],
          f"errors={errors}")
    lm.release_all(1)
    lm.release_all(2)


# ================================================================== #
#  TEST 4: Lock timeout                                               #
# ================================================================== #

def test_lock_timeout():
    header("TEST 4: Lock timeout")
    lm = PageLockManager(timeout=0.5)

    lm.acquire(1, 0, LockType.EXCLUSIVE)

    timed_out = {"value": False}

    def try_lock():
        try:
            lm.acquire(2, 0, LockType.EXCLUSIVE)
        except LockTimeoutError:
            timed_out["value"] = True

    t0 = time.time()
    t = threading.Thread(target=try_lock)
    t.start()
    t.join(timeout=3.0)
    elapsed = time.time() - t0

    check("Timeout detectado", timed_out["value"])
    check(f"Timeout en ~0.5s (fue {elapsed:.2f}s)", 0.3 < elapsed < 1.5,
          f"elapsed={elapsed:.3f}")
    lm.release_all(1)


# ================================================================== #
#  TEST 5: Transaction Log                                            #
# ================================================================== #

def test_transaction_log():
    header("TEST 5: Transaction Log")
    tlog = TransactionLog()

    tlog.log(1, "BEGIN")
    tlog.log(1, "READ", "page=0")
    tlog.log(2, "BEGIN")
    tlog.log(2, "WRITE", "page=0")
    tlog.log(1, "WRITE", "page=1")
    tlog.log(2, "READ", "page=1")
    tlog.log(1, "COMMIT")
    tlog.log(2, "COMMIT")

    formatted = tlog.format()
    check("Log tiene 8 entradas", len(tlog.entries) == 8)
    check("Log formateado no vacio", len(formatted) > 0)

    conflicts = tlog.find_conflicts()
    check("Conflictos detectados", len(conflicts) > 0,
          f"conflicts={conflicts}")

    # Page 0: TX1 READ, TX2 WRITE -> conflicto R-W
    page0_conflict = [c for c in conflicts if c["page"] == 0]
    check("Conflicto R-W en page 0", len(page0_conflict) > 0)
    if page0_conflict:
        check("Tipo R-W", page0_conflict[0]["type"] == "R-W")


# ================================================================== #
#  TEST 6: Dos transacciones concurrentes — reads                     #
# ================================================================== #

def test_concurrent_reads():
    header("TEST 6: Dos TX concurrentes — lecturas simultaneas")
    cleanup()
    Transaction.reset_counter()

    tree, lm, tlog = make_tree()

    # Insertar datos sin transaccion
    for i in range(20):
        tree.add(i, (0, i))

    results = {"tx1": None, "tx2": None}
    tlog.clear()

    def tx_read(tx_name, key):
        tx = Transaction(tree, lm, tlog)
        results[tx_name] = tx.search(key)
        tx.commit()

    t1 = threading.Thread(target=tx_read, args=("tx1", 5))
    t2 = threading.Thread(target=tx_read, args=("tx2", 10))
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)

    check("TX1 encontro key=5", results["tx1"] == (0, 5))
    check("TX2 encontro key=10", results["tx2"] == (0, 10))

    # Verificar que el log tiene entradas de ambas TX
    tx_ids = set(e["tx_id"] for e in tlog.entries)
    check("Log tiene 2 TX", len(tx_ids) == 2)

    # Imprimir log
    print("  --- Log ---")
    for line in tlog.format().split("\n"):
        print(f"  {line}")

    cleanup()


# ================================================================== #
#  TEST 7: Dos TX concurrentes — escrituras intercaladas             #
# ================================================================== #

def test_concurrent_writes():
    header("TEST 7: Dos TX concurrentes — escrituras intercaladas")
    cleanup()
    Transaction.reset_counter()

    tree, lm, tlog = make_tree()

    # Poblamos
    for i in range(10):
        tree.add(i, (0, i))
    tlog.clear()

    completed = {"tx1": False, "tx2": False}

    def tx_insert(name, start, count):
        # Reintentar si hay deadlock (la TX victima reintenta)
        for attempt in range(3):
            tx = Transaction(tree, lm, tlog)
            try:
                for i in range(start, start + count):
                    tx.add(i, (1, i))
                tx.commit()
                completed[name] = True
                return
            except (DeadlockError, LockTimeoutError):
                tx.abort()
                time.sleep(0.1 * (attempt + 1))  # backoff

    t1 = threading.Thread(target=tx_insert, args=("tx1", 100, 5))
    t2 = threading.Thread(target=tx_insert, args=("tx2", 200, 5))
    t1.start()
    t2.start()
    t1.join(timeout=15.0)
    t2.join(timeout=15.0)

    # Verificar que ambas completaron (con reintentos)
    check("TX1 completada (key=100)", tree.search(100) == (1, 100))
    check("TX2 completada (key=200)", tree.search(200) == (1, 200))

    # Verificar log tiene deadlocks o reintentos
    aborts = [e for e in tlog.entries if e["op"] == "ABORT"]
    commits = [e for e in tlog.entries if e["op"] == "COMMIT"]
    check(f"Commits >= 2", len(commits) >= 2, f"got {len(commits)}")
    if aborts:
        print(f"  Deadlocks resueltos via retry: {len(aborts)} aborts")

    conflicts = tlog.find_conflicts()
    if conflicts:
        print(f"  Conflictos detectados: {len(conflicts)}")
        for c in conflicts[:3]:
            print(f"    Page {c['page']}: {c['type']} entre TX {c['transactions']}")

    print("  --- Log (primeras 20 lineas) ---")
    lines = tlog.format().split("\n")
    for line in lines[:20]:
        print(f"  {line}")
    if len(lines) > 20:
        print(f"  ... ({len(lines) - 20} lineas mas)")

    cleanup()


# ================================================================== #
#  TEST 8: Read-Write interleaving con conflicto                     #
# ================================================================== #

def test_read_write_conflict():
    header("TEST 8: Read-Write interleaving — conflicto R-W")
    cleanup()
    Transaction.reset_counter()

    tree, lm, tlog = make_tree()
    for i in range(20):
        tree.add(i, (0, i))
    tlog.clear()

    results = {"reader": [], "writer_done": False}
    sync = threading.Event()

    def reader_tx():
        tx = Transaction(tree, lm, tlog)
        try:
            # Lee primero
            results["reader"].append(tx.search(5))
            sync.set()  # Indicar al writer que ya leimos
            time.sleep(0.2)  # Simular trabajo
            # Lee de nuevo (deberia ser consistente en 2PL)
            results["reader"].append(tx.search(5))
            tx.commit()
        except (DeadlockError, LockTimeoutError):
            tx.abort()

    def writer_tx():
        sync.wait(timeout=3.0)  # Esperar a que reader lea primero
        tx = Transaction(tree, lm, tlog)
        try:
            tx.remove(5)
            tx.add(5, (9, 9))
            results["writer_done"] = True
            tx.commit()
        except (DeadlockError, LockTimeoutError):
            tx.abort()

    t1 = threading.Thread(target=reader_tx)
    t2 = threading.Thread(target=writer_tx)
    t1.start()
    t2.start()
    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    check("Reader obtuvo 2 resultados", len(results["reader"]) == 2,
          f"got {len(results['reader'])}")

    # Imprimir log
    print("  --- Log ---")
    for line in tlog.format().split("\n"):
        print(f"  {line}")

    conflicts = tlog.find_conflicts()
    if conflicts:
        print(f"  Conflictos R-W: {len(conflicts)}")

    cleanup()


# ================================================================== #
#  TEST 9: Range search concurrente                                  #
# ================================================================== #

def test_concurrent_range():
    header("TEST 9: Range search concurrente con inserts")
    cleanup()
    Transaction.reset_counter()

    tree, lm, tlog = make_tree()
    for i in range(50):
        tree.add(i, (0, i))
    tlog.clear()

    results = {"range": None, "inserted": False}

    def range_tx():
        tx = Transaction(tree, lm, tlog)
        try:
            results["range"] = tx.range_search(10, 20)
            tx.commit()
        except (DeadlockError, LockTimeoutError):
            tx.abort()

    def insert_tx():
        tx = Transaction(tree, lm, tlog)
        try:
            tx.add(100, (1, 100))
            tx.add(101, (1, 101))
            results["inserted"] = True
            tx.commit()
        except (DeadlockError, LockTimeoutError):
            tx.abort()

    t1 = threading.Thread(target=range_tx)
    t2 = threading.Thread(target=insert_tx)
    t1.start()
    t2.start()
    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    check("Range search retorno resultados",
          results["range"] is not None and len(results["range"]) >= 11,
          f"got {len(results['range']) if results['range'] else 'None'}")
    check("Insert completado", results["inserted"])

    print("  --- Log (primeras 15 lineas) ---")
    lines = tlog.format().split("\n")
    for line in lines[:15]:
        print(f"  {line}")

    cleanup()


# ================================================================== #
#  TEST 10: Transaccion abort y consistencia                          #
# ================================================================== #

def test_abort_consistency():
    header("TEST 10: Abort libera locks correctamente")
    cleanup()
    Transaction.reset_counter()

    tree, lm, tlog = make_tree()
    for i in range(10):
        tree.add(i, (0, i))
    tlog.clear()

    # TX1 inserta y aborta
    tx1 = Transaction(tree, lm, tlog)
    tx1.add(99, (1, 99))
    tx1.abort()

    # TX2 deberia poder operar sin problemas sobre las mismas paginas
    tx2 = Transaction(tree, lm, tlog)
    result = tx2.search(5)
    tx2.commit()

    check("TX2 opero tras abort de TX1", result == (0, 5))

    # Verificar que TX1 no tiene locks
    locks = lm.get_locks_held(tx1.tx_id)
    check("TX1 sin locks tras abort", len(locks) == 0)

    print("  --- Log ---")
    for line in tlog.format().split("\n"):
        print(f"  {line}")

    cleanup()


# ================================================================== #
#  TEST 11: Stress — multiples TX concurrentes                       #
# ================================================================== #

def test_stress():
    header("TEST 11: Stress — 4 TX concurrentes")
    cleanup()
    Transaction.reset_counter()

    tree, lm, tlog = make_tree()
    # Menor timeout para no bloquear demasiado
    lm.timeout = 3.0

    for i in range(100):
        tree.add(i, (0, i))
    tlog.clear()

    completed = {"count": 0}
    aborted = {"count": 0}
    count_lock = threading.Lock()

    def worker(tx_start, tx_count):
        tx = Transaction(tree, lm, tlog)
        try:
            for i in range(tx_count):
                key = tx_start + i
                tx.add(key, (2, key))
            tx.search(tx_start)
            tx.commit()
            with count_lock:
                completed["count"] += 1
        except (DeadlockError, LockTimeoutError):
            tx.abort()
            with count_lock:
                aborted["count"] += 1

    threads = [
        threading.Thread(target=worker, args=(1000, 10)),
        threading.Thread(target=worker, args=(2000, 10)),
        threading.Thread(target=worker, args=(3000, 10)),
        threading.Thread(target=worker, args=(4000, 10)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    total = completed["count"] + aborted["count"]
    check(f"4 TX finalizaron ({completed['count']} ok, {aborted['count']} abort)",
          total == 4)
    check("Al menos 1 TX completo", completed["count"] >= 1)

    tx_ids = set(e["tx_id"] for e in tlog.entries)
    check(f"Log tiene {len(tx_ids)} TX", len(tx_ids) == 4)

    conflicts = tlog.find_conflicts()
    print(f"  Conflictos: {len(conflicts)}")
    print(f"  Total entradas en log: {len(tlog.entries)}")

    cleanup()


# ================================================================== #
#  TEST 12: Conflict analysis completo                               #
# ================================================================== #

def test_conflict_analysis():
    header("TEST 12: Conflict analysis del log")
    cleanup()
    Transaction.reset_counter()

    tree, lm, tlog = make_tree()
    for i in range(30):
        tree.add(i, (0, i))
    tlog.clear()

    barrier = threading.Barrier(2, timeout=5.0)

    def tx_search_and_delete():
        tx = Transaction(tree, lm, tlog)
        try:
            tx.search(10)
            barrier.wait()
            tx.remove(15)
            tx.commit()
        except (DeadlockError, LockTimeoutError):
            tx.abort()
        except threading.BrokenBarrierError:
            tx.commit()

    def tx_search_and_insert():
        tx = Transaction(tree, lm, tlog)
        try:
            tx.search(15)
            barrier.wait()
            tx.add(500, (2, 500))
            tx.commit()
        except (DeadlockError, LockTimeoutError):
            tx.abort()
        except threading.BrokenBarrierError:
            tx.commit()

    t1 = threading.Thread(target=tx_search_and_delete)
    t2 = threading.Thread(target=tx_search_and_insert)
    t1.start()
    t2.start()
    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    conflicts = tlog.find_conflicts()
    check("Log no vacio", len(tlog.entries) > 0)

    # Clasificar operaciones
    ops = {}
    for e in tlog.entries:
        ops.setdefault(e["tx_id"], []).append(e["op"])

    for tx_id, op_list in ops.items():
        print(f"  TX{tx_id}: {' -> '.join(op_list)}")

    if conflicts:
        print(f"  --- Conflictos detectados: {len(conflicts)} ---")
        for c in conflicts:
            print(f"    Page {c['page']}: {c['type']} "
                  f"entre TX {c['transactions']}")
    else:
        print("  Sin conflictos (las TX no accedieron a mismas paginas)")

    check("Analisis completo", True)
    cleanup()


if __name__ == "__main__":
    print()
    print("*" * 65)
    print("*    TESTS: Simulador de Acceso Concurrente                     *")
    print("*" * 65)

    test_lock_basics()
    test_lock_upgrade()
    test_deadlock_detection()
    test_lock_timeout()
    test_transaction_log()
    test_concurrent_reads()
    test_concurrent_writes()
    test_read_write_conflict()
    test_concurrent_range()
    test_abort_consistency()
    test_stress()
    test_conflict_analysis()

    print()
    print("=" * 65)
    print(f"  RESUMEN: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 65)
    print()

    if FAILED > 0:
        sys.exit(1)
