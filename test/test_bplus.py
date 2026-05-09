"""
Tests del B+ Tree
Ejecutar con:
    python dbms/structures/test_bplus.py
"""

import os
import sys
import math
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dbms.structures.bplus import BPlusTree


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


# ================================================================== #
#  TEST 1: Carpeta indexes                                            #
# ================================================================== #

def test_indexes_folder():
    header("TEST 1: Carpeta indexes")
    cleanup()
    idx = BPlusTree("test.idx", key_format="i")
    check("Carpeta indexes/ creada", os.path.isdir("indexes"))
    check("Archivo en indexes/", os.path.exists(os.path.join("indexes", "test.idx")))
    cleanup()


# ================================================================== #
#  TEST 2: Insert + search unico                                      #
# ================================================================== #

def test_unique_basic():
    header("TEST 2: Insert + search unico")
    cleanup()
    idx = BPlusTree("u.idx", key_format="i", unique=True)
    for i in range(20):
        idx.add(i, (0, i))
    for i in range(20):
        check(f"search({i})", idx.search(i) == (0, i))
    check("search(99) = None", idx.search(99) is None)
    cleanup()


# ================================================================== #
#  TEST 3: Non-unique                                                  #
# ================================================================== #

def test_non_unique():
    header("TEST 3: Non-unique")
    cleanup()
    idx = BPlusTree("nu.idx", key_format="i", unique=False)
    for i in range(5):
        idx.add(42, (0, i))
    results = idx.search_all(42)
    check("search_all(42) = 5", len(results) == 5, f"got {len(results)}")
    rids = [r[1] for r in results]
    check("Orden de insercion", rids == [0, 1, 2, 3, 4], f"got {rids}")
    cleanup()


# ================================================================== #
#  TEST 4: Massive insert/delete                                       #
# ================================================================== #

def test_massive():
    header("TEST 4: Massive insert/delete (500 keys)")
    cleanup()
    idx = BPlusTree("m.idx", key_format="i", unique=True)
    for i in range(500):
        idx.add(i, (i // 100, i % 100))
    check("search(250)", idx.search(250) == (2, 50))
    for i in range(0, 500, 2):
        idx.remove(i)
    check("search(100) removed", idx.search(100) is None)
    check("search(101) still", idx.search(101) == (1, 1))
    remaining = idx.range_search(0, 499)
    check("250 remaining", len(remaining) == 250, f"got {len(remaining)}")
    cleanup()


# ================================================================== #
#  TEST 5: Massive duplicates                                          #
# ================================================================== #

def test_massive_duplicates():
    header("TEST 5: Massive duplicates (400 same key)")
    cleanup()
    idx = BPlusTree("md.idx", key_format="i", unique=False)
    for i in range(400):
        idx.add(42, (i // 100, i % 100))
    results = idx.search_all(42)
    check("400 entradas encontradas", len(results) == 400, f"got {len(results)}")
    cleanup()


# ================================================================== #
#  TEST 6: Range search                                                #
# ================================================================== #

def test_range():
    header("TEST 6: Range search")
    cleanup()
    idx = BPlusTree("r.idx", key_format="i", unique=False)
    for i in range(100):
        idx.add(i, (0, i))
        idx.add(i, (1, i))  # duplicado
    results = idx.range_search(10, 19)
    check("range(10,19) = 20 (10 keys * 2)", len(results) == 20, f"got {len(results)}")
    cleanup()


# ================================================================== #
#  TEST 7: Pagination                                                  #
# ================================================================== #

def test_pagination():
    header("TEST 7: Pagination (10000 records)")
    cleanup()
    idx = BPlusTree("pg.idx", key_format="i", unique=True)
    for i in range(10000):
        idx.add(i, (i // 100, i % 100))
    page1 = idx.range_search(0, 9999, limit=100, offset=0)
    page2 = idx.range_search(0, 9999, limit=100, offset=100)
    check("page1 = 100", len(page1) == 100)
    check("page2 = 100", len(page2) == 100)
    check("page2[0] != page1[0]", page2[0] != page1[0])
    cleanup()


# ================================================================== #
#  TEST 8: Persistence                                                 #
# ================================================================== #

def test_persistence():
    header("TEST 8: Persistence")
    cleanup()
    idx = BPlusTree("p.idx", key_format="i", unique=True)
    for i in range(50):
        idx.add(i, (0, i))
    idx2 = BPlusTree("p.idx", key_format="i", unique=True)
    check("Dato persiste", idx2.search(25) == (0, 25))
    cleanup()


# ================================================================== #
#  TEST 9: Remove specific RID                                         #
# ================================================================== #

def test_remove_specific():
    header("TEST 9: Remove specific RID (non-unique)")
    cleanup()
    idx = BPlusTree("rs.idx", key_format="i", unique=False)
    idx.add(10, (0, 0))
    idx.add(10, (0, 1))
    idx.add(10, (0, 2))
    idx.remove(10, value=(0, 1))
    results = idx.search_all(10)
    check("2 remaining", len(results) == 2, f"got {len(results)}")
    rids = [r for r in results]
    check("(0,1) gone", (0, 1) not in rids)
    cleanup()


# ================================================================== #
#  TEST 10: IO stats                                                   #
# ================================================================== #

def test_io_stats():
    header("TEST 10: IO stats")
    cleanup()
    idx = BPlusTree("io.idx", key_format="i", unique=True)
    for i in range(1000):
        idx.add(i, (0, i))
    idx.reset_stats()
    idx.search(500)
    h = math.ceil(math.log(1000, max(2, idx.max_keys // 2)))
    check(f"search reads={idx.disk_reads} <= height+1={h + 1}",
          idx.disk_reads <= h + 1)
    cleanup()


if __name__ == "__main__":
    print()
    print("*" * 65)
    print("*    TESTS: B+ Tree                                             *")
    print("*" * 65)

    test_indexes_folder()
    test_unique_basic()
    test_non_unique()
    test_massive()
    test_massive_duplicates()
    test_range()
    test_pagination()
    test_persistence()
    test_remove_specific()
    test_io_stats()

    print()
    print("=" * 65)
    print(f"  RESUMEN: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 65)
    print()

    if FAILED > 0:
        sys.exit(1)
