"""
Tests del R-Tree: Indice Espacial 2D
Ejecutar con:
    python dbms/structures/test_rtree.py
"""

import os
import sys
import math
import shutil
import random
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dbms.structures.rtree import RTree


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


def dist(x1, y1, x2, y2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def test_indexes_folder():
    header("TEST 1: Carpeta indexes")
    cleanup()
    rt = RTree("test_spatial.idx")
    check("Carpeta indexes/ creada", os.path.isdir("indexes"))
    check("Archivo en indexes/", os.path.exists(os.path.join("indexes", "test_spatial.idx")))
    cleanup()


def test_basic_insert_search():
    header("TEST 2: Insert + search basico")
    cleanup()
    rt = RTree("geo.idx")
    rt.add(10.0, 20.0, (0, 0))
    rt.add(15.0, 25.0, (0, 1))
    rt.add(30.0, 40.0, (0, 2))
    check("search(10,20)", rt.search(10.0, 20.0) == (0, 0))
    check("search(15,25)", rt.search(15.0, 25.0) == (0, 1))
    check("search(99,99) = None", rt.search(99.0, 99.0) is None)
    cleanup()


def test_radius_search():
    header("TEST 3: Busqueda circular")
    cleanup()
    rt = RTree("geo.idx")
    for x, y, rid in [(0,0,(0,0)), (1,0,(0,1)), (0,1,(0,2)), (1,1,(0,3)), (5,5,(0,4)), (10,10,(0,5))]:
        rt.add(float(x), float(y), rid)
    results = rt.radius_search(0.0, 0.0, 1.5)
    check("radius(0,0,r=1.5) = 4", len(results) == 4, f"got {len(results)}")
    dists = [r[3] for r in results]
    check("Ordenado por distancia", dists == sorted(dists))
    results3 = rt.radius_search(5.0, 5.0, 20.0)
    check("radius(5,5,r=20) = 6 (todos)", len(results3) == 6, f"got {len(results3)}")
    cleanup()


def test_knn_search():
    header("TEST 4: k-NN search")
    cleanup()
    rt = RTree("geo.idx")
    for x, y, rid in [(0,0,(0,0)), (1,1,(0,1)), (2,2,(0,2)), (3,3,(0,3)), (10,10,(0,4))]:
        rt.add(float(x), float(y), rid)
    results = rt.knn_search(0.0, 0.0, 3)
    check("knn(0,0,k=3) = 3", len(results) == 3)
    check("1er vecino = (0,0)", results[0][0] == 0.0 and results[0][1] == 0.0)
    pts = [(r[0], r[1]) for r in results]
    check("3-NN correcto", pts == [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)], f"got {pts}")
    cleanup()


def test_pagination():
    header("TEST 5: Paginacion")
    cleanup()
    rt = RTree("geo.idx")
    for i in range(100):
        rt.add(float(i), 0.0, (0, i))
    page1 = rt.knn_search(0.0, 0.0, 5, offset=0)
    page2 = rt.knn_search(0.0, 0.0, 5, offset=5)
    check("page1 = 5", len(page1) == 5)
    check("page2 = 5", len(page2) == 5)
    check("Paginacion consecutiva", page2[0][0] != page1[0][0])
    paged = rt.radius_search(50.0, 0.0, 20.0, limit=5)
    check("radius limit=5", len(paged) <= 5)
    cleanup()


def test_delete():
    header("TEST 6: Delete")
    cleanup()
    rt = RTree("geo.idx")
    for i in range(1, 6):
        rt.add(float(i), float(i), (0, i - 1))
    check("search(3,3) antes", rt.search(3.0, 3.0) == (0, 2))
    rt.remove(3.0, 3.0)
    check("search(3,3) despues = None", rt.search(3.0, 3.0) is None)
    check("search(1,1) sigue", rt.search(1.0, 1.0) == (0, 0))
    rt.add(10.0, 10.0, (1, 0))
    rt.add(10.0, 10.0, (1, 1))
    rt.remove(10.0, 10.0, rid=(1, 0))
    check("delete selectivo por RID", rt.search(10.0, 10.0) == (1, 1))
    check("remove inexistente = False", not rt.remove(99.0, 99.0))
    cleanup()


def test_volume():
    header("TEST 7: Volumen — 1000 puntos")
    cleanup()
    rt = RTree("geo_vol.idx")
    random.seed(42)
    points = []
    for i in range(1000):
        x = random.uniform(-90.0, 90.0)
        y = random.uniform(-180.0, 180.0)
        rt.add(x, y, (i // 100, i % 100))
        points.append((x, y))
    results = rt.knn_search(0.0, 0.0, 5)
    check("knn(0,0,k=5) = 5", len(results) == 5)
    dists_knn = [r[3] for r in results]
    check("knn ordenado", dists_knn == sorted(dists_knn))
    all_dists = sorted([dist(0, 0, p[0], p[1]) for p in points])
    check("knn correctos", all(abs(a - e) < 1e-6 for a, e in zip(dists_knn, all_dists[:5])))
    radius_results = rt.radius_search(0.0, 0.0, 10.0)
    brute_count = sum(1 for p in points if dist(0, 0, p[0], p[1]) <= 10.0)
    check("radius count correcto", len(radius_results) == brute_count,
          f"rtree={len(radius_results)}, brute={brute_count}")
    cleanup()


def test_delete_volume():
    header("TEST 8: Delete masivo")
    cleanup()
    rt = RTree("geo_del.idx")
    random.seed(123)
    points = []
    for i in range(200):
        x = random.uniform(0.0, 100.0)
        y = random.uniform(0.0, 100.0)
        rt.add(x, y, (0, i))
        points.append((x, y, (0, i)))
    deleted = sum(1 for p in points[:100] if rt.remove(p[0], p[1], rid=p[2]))
    check(f"Eliminados {deleted}/100", deleted == 100)
    found = sum(1 for p in points[100:]
                if any(r[2] == p[2] for r in rt.search_all(p[0], p[1])))
    check("Restantes encontrados", found == 100, f"found {found}")
    cleanup()


def test_json_response():
    header("TEST 9: JSON response")
    cleanup()
    rt = RTree("geo_json.idx")
    rt.add(-12.0, -77.0, (0, 0))
    rt.add(-33.4, -70.6, (0, 1))
    rt.add(4.7, -74.1, (0, 2))
    result = rt.knn_search_json(-12.0, -77.0, 2)
    check("query_point rojo", result["query_point"]["color"] == "red")
    check("total = 2", result["total"] == 2)
    check("resultados azules", all(r["color"] == "blue" for r in result["results"]))
    check("JSON serializable", True if json.dumps(result) else False)
    cleanup()


def test_persistence():
    header("TEST 10: Persistencia")
    cleanup()
    rt = RTree("geo_persist.idx")
    rt.add(1.0, 2.0, (0, 0))
    rt.add(3.0, 4.0, (0, 1))
    rt2 = RTree("geo_persist.idx")
    check("Persiste", rt2.search(3.0, 4.0) == (0, 1))
    cleanup()


def test_duplicates():
    header("TEST 11: Puntos duplicados")
    cleanup()
    rt = RTree("geo_dup.idx")
    for i in range(10):
        rt.add(5.0, 5.0, (0, i))
    check("10 entradas en (5,5)", len(rt.search_all(5.0, 5.0)) == 10)
    rt.remove(5.0, 5.0, rid=(0, 3))
    check("9 despues de delete", len(rt.search_all(5.0, 5.0)) == 9)
    cleanup()


def test_io_stats():
    header("TEST 12: Disk I/O stats")
    cleanup()
    rt = RTree("geo_io.idx")
    for i in range(200):
        rt.add(float(i), float(i), (0, i))
    rt.reset_stats()
    rt.search(100.0, 100.0)
    check(f"search: {rt.disk_reads} reads (< 200)", rt.disk_reads < 200)
    cleanup()


if __name__ == "__main__":
    print()
    print("*" * 65)
    print("*    TESTS: R-Tree (Indice Espacial 2D)                         *")
    print("*" * 65)

    test_indexes_folder()
    test_basic_insert_search()
    test_radius_search()
    test_knn_search()
    test_pagination()
    test_delete()
    test_volume()
    test_delete_volume()
    test_json_response()
    test_persistence()
    test_duplicates()
    test_io_stats()

    print()
    print("=" * 65)
    print(f"  RESUMEN: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 65)
    print()

    if FAILED > 0:
        sys.exit(1)
