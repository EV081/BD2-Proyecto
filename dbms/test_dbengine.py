"""
Tests de integracion: DataBase + indices + schema persistente
Ejecutar con:
    python dbms/test_dbengine.py
"""

import os
import sys
import math
import json
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dbms.dbengine import DataBase


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
    for folder in ["data", "schemas", "indexes"]:
        if os.path.isdir(folder):
            shutil.rmtree(folder)


# ================================================================== #
#  TEST 1: Insert + select sin indice (full scan)                     #
# ================================================================== #

def test_no_index():
    header("TEST 1: Insert + select sin indice (full scan)")
    cleanup()

    schema = {"id": "int", "edad": "int", "salario": "float"}
    db = DataBase("empleados", schema=schema)

    db.insert({"id": 1, "edad": 25, "salario": 3000.0})
    db.insert({"id": 2, "edad": 30, "salario": 4500.0})
    db.insert({"id": 3, "edad": 25, "salario": 3200.0})
    db.insert({"id": 4, "edad": 40, "salario": 6000.0})
    db.insert({"id": 5, "edad": 25, "salario": 2800.0})

    all_recs = db.select_all()
    check("select_all retorna 5 registros", len(all_recs) == 5, f"got {len(all_recs)}")

    by_age = db.select("edad", 25)
    check("select(edad=25) sin indice = 3", len(by_age) == 3, f"got {len(by_age)}")

    by_id = db.select("id", 4)
    check("select(id=4) sin indice = 1", len(by_id) == 1)
    check("select(id=4) salario correcto", by_id[0][2] == 6000.0)

    cleanup()


# ================================================================== #
#  TEST 2: Crear indice sobre tabla existente                         #
# ================================================================== #

def test_create_index_existing_data():
    header("TEST 2: Crear indice sobre tabla con datos existentes")
    cleanup()

    schema = {"id": "int", "edad": "int", "salario": "float"}
    db = DataBase("empleados", schema=schema)

    db.insert({"id": 1, "edad": 25, "salario": 3000.0})
    db.insert({"id": 2, "edad": 30, "salario": 4500.0})
    db.insert({"id": 3, "edad": 25, "salario": 3200.0})

    db.create_index("id", index_type="bplus", unique=True)
    db.create_index("edad", index_type="bplus", unique=False)

    check("has_index(id)", db.has_index("id"))
    check("has_index(edad)", db.has_index("edad"))

    by_id = db.select("id", 2)
    check("select(id=2) via indice = 1", len(by_id) == 1)
    check("select(id=2) salario = 4500.0", by_id[0][2] == 4500.0)

    by_age = db.select("edad", 25)
    check("select(edad=25) via indice = 2", len(by_age) == 2, f"got {len(by_age)}")

    cleanup()


# ================================================================== #
#  TEST 3: Insert actualiza indices                                    #
# ================================================================== #

def test_insert_updates_index():
    header("TEST 3: Insert actualiza indices automaticamente")
    cleanup()

    schema = {"id": "int", "edad": "int", "salario": "float"}
    db = DataBase("empleados", schema=schema)
    db.create_index("id", index_type="bplus", unique=True)
    db.create_index("edad", index_type="bplus", unique=False)

    db.insert({"id": 1, "edad": 25, "salario": 3000.0})
    db.insert({"id": 2, "edad": 30, "salario": 4500.0})
    db.insert({"id": 3, "edad": 25, "salario": 3200.0})
    db.insert({"id": 4, "edad": 30, "salario": 5000.0})

    check("select(id=3) encontrado", len(db.select("id", 3)) == 1)
    check("select(edad=30) = 2", len(db.select("edad", 30)) == 2)

    cleanup()


# ================================================================== #
#  TEST 4: Range search                                                #
# ================================================================== #

def test_range_search():
    header("TEST 4: Range search con indice")
    cleanup()

    schema = {"id": "int", "edad": "int", "salario": "float"}
    db = DataBase("empleados", schema=schema)
    db.create_index("edad", index_type="bplus", unique=False)

    datos = [
        {"id": 1, "edad": 20, "salario": 2000.0},
        {"id": 2, "edad": 25, "salario": 3000.0},
        {"id": 3, "edad": 30, "salario": 4000.0},
        {"id": 4, "edad": 35, "salario": 5000.0},
        {"id": 5, "edad": 40, "salario": 6000.0},
        {"id": 6, "edad": 25, "salario": 3100.0},
        {"id": 7, "edad": 30, "salario": 4100.0},
    ]
    for d in datos:
        db.insert(d)

    rango = db.select_range("edad", 25, 35)
    check("range(edad, 25, 35) = 5", len(rango) == 5, f"got {len(rango)}")

    rango_sal = db.select_range("salario", 3000.0, 4100.0)
    check("range(salario, 3000, 4100) sin indice = 4", len(rango_sal) == 4, f"got {len(rango_sal)}")

    cleanup()


# ================================================================== #
#  TEST 5: Delete actualiza indices                                    #
# ================================================================== #

def test_delete_updates_index():
    header("TEST 5: Delete actualiza indices")
    cleanup()

    schema = {"id": "int", "edad": "int", "salario": "float"}
    db = DataBase("empleados", schema=schema)
    db.create_index("id", index_type="bplus", unique=True)
    db.create_index("edad", index_type="bplus", unique=False)

    db.insert({"id": 1, "edad": 25, "salario": 3000.0})
    db.insert({"id": 2, "edad": 30, "salario": 4500.0})
    db.insert({"id": 3, "edad": 25, "salario": 3200.0})
    db.insert({"id": 4, "edad": 25, "salario": 2800.0})

    check("Antes: select(edad=25) = 3", len(db.select("edad", 25)) == 3)

    deleted = db.delete("id", 3)
    check("delete(id=3) = 1", deleted == 1)
    check("select(id=3) = 0", len(db.select("id", 3)) == 0)
    check("select(edad=25) = 2", len(db.select("edad", 25)) == 2)

    deleted2 = db.delete("edad", 25)
    check("delete(edad=25) = 2", deleted2 == 2)
    check("select_all = 1 restante", len(db.select_all()) == 1)

    cleanup()


# ================================================================== #
#  TEST 6: Drop index                                                  #
# ================================================================== #

def test_drop_index():
    header("TEST 6: Drop index")
    cleanup()

    schema = {"id": "int", "edad": "int", "salario": "float"}
    db = DataBase("empleados", schema=schema)
    db.create_index("edad", index_type="bplus", unique=False)
    db.insert({"id": 1, "edad": 25, "salario": 3000.0})

    check("has_index(edad) = True", db.has_index("edad"))
    db.drop_index("edad")
    check("has_index(edad) = False", not db.has_index("edad"))
    check("select sigue via full scan", len(db.select("edad", 25)) == 1)

    cleanup()


# ================================================================== #
#  TEST 7: Volumen — 1000 registros                                    #
# ================================================================== #

def test_volume():
    header("TEST 7: Volumen — 1000 registros")
    cleanup()

    schema = {"id": "int", "categoria": "int", "precio": "float"}
    db = DataBase("productos", schema=schema)
    db.create_index("id", index_type="bplus", unique=True)
    db.create_index("categoria", index_type="bplus", unique=False)

    for i in range(1000):
        db.insert({"id": i, "categoria": i % 10, "precio": float(i * 10)})

    check("select(id=500) = 1", len(db.select("id", 500)) == 1)
    check("select(categoria=3) = 100", len(db.select("categoria", 3)) == 100)
    check("range(id, 100, 109) = 10", len(db.select_range("id", 100, 109)) == 10)

    db.delete("id", 500)
    check("select(id=500) = 0 post-delete", len(db.select("id", 500)) == 0)
    check("select_all = 999", len(db.select_all()) == 999)

    cleanup()


# ================================================================== #
#  TEST 8: Errores esperados                                           #
# ================================================================== #

def test_errors():
    header("TEST 8: Errores esperados")
    cleanup()

    schema = {"id": "int", "nombre": "char(20)"}
    db = DataBase("test_err", schema=schema)

    try:
        db.create_index("noexiste", index_type="bplus")
        check("Error: columna inexistente", False)
    except ValueError:
        check("Error: columna inexistente", True)

    try:
        db.create_index("id", index_type="magico")
        check("Error: tipo invalido", False)
    except ValueError:
        check("Error: tipo invalido", True)

    db.create_index("id", index_type="bplus", unique=True)
    try:
        db.create_index("id", index_type="bplus", unique=True)
        check("Error: indice duplicado", False)
    except ValueError:
        check("Error: indice duplicado", True)

    try:
        db.drop_index("noexiste")
        check("Error: drop inexistente", False)
    except ValueError:
        check("Error: drop inexistente", True)

    cleanup()


# ================================================================== #
#  TEST 9: R-Tree — knn + radius via dbengine                         #
# ================================================================== #

def test_rtree_queries():
    header("TEST 9: R-Tree — knn + radius via dbengine")
    cleanup()

    schema = {"id": "int", "lat": "float", "lon": "float", "nombre": "char(20)"}
    db = DataBase("ciudades", schema=schema)
    db.create_index(("lat", "lon"), index_type="rtree")

    ciudades = [
        {"id": 1, "lat": -12.04, "lon": -77.03, "nombre": "Lima"},
        {"id": 2, "lat": -33.45, "lon": -70.66, "nombre": "Santiago"},
        {"id": 3, "lat": -22.91, "lon": -43.17, "nombre": "Rio"},
        {"id": 4, "lat": 4.71,   "lon": -74.07, "nombre": "Bogota"},
        {"id": 5, "lat": -0.18,  "lon": -78.47, "nombre": "Quito"},
    ]
    for c in ciudades:
        db.insert(c)

    knn = db.select_knn("lat", "lon", -12.04, -77.03, 3)
    check("knn(Lima, k=3) = 3", len(knn) == 3)
    check("knn[0] es Lima (id=1)", knn[0][0] == 1)

    knn_json = db.select_knn_json("lat", "lon", -12.04, -77.03, 3)
    check("knn JSON: query rojo", knn_json["query_point"]["color"] == "red")
    check("knn JSON: 3 azules", len(knn_json["results"]) == 3)
    check("knn JSON serializable", True if json.dumps(knn_json) else False)

    radius = db.select_radius("lat", "lon", -12.04, -77.03, 15.0)
    check("radius(Lima, r=15) > 0", len(radius) > 0)

    cleanup()


# ================================================================== #
#  TEST 10: R-Tree — delete sincroniza indices                         #
# ================================================================== #

def test_rtree_delete():
    header("TEST 10: R-Tree — delete sincroniza indices")
    cleanup()

    schema = {"id": "int", "lat": "float", "lon": "float"}
    db = DataBase("geo_del", schema=schema)
    db.create_index("id", index_type="bplus", unique=True)
    db.create_index(("lat", "lon"), index_type="rtree")

    db.insert({"id": 1, "lat": 10.0, "lon": 20.0})
    db.insert({"id": 2, "lat": 30.0, "lon": 40.0})
    db.insert({"id": 3, "lat": 50.0, "lon": 60.0})

    check("knn antes: 3", len(db.select_knn("lat", "lon", 10.0, 20.0, 3)) == 3)

    db.delete("id", 2)
    check("knn despues: 2", len(db.select_knn("lat", "lon", 10.0, 20.0, 3)) == 2)

    cleanup()


# ================================================================== #
#  TEST 11: Primary Key                                                #
# ================================================================== #

def test_primary_key():
    header("TEST 11: Primary Key")
    cleanup()

    schema = {"id": "int", "nombre": "char(20)", "edad": "int"}
    db = DataBase("personas", schema=schema, primary_key="id")

    check("primary_key = 'id'", db.primary_key == "id")
    check("Indice PK auto-creado", db.has_index("id"))

    db.insert({"id": 1, "nombre": "Ana", "edad": 25})
    db.insert({"id": 2, "nombre": "Bob", "edad": 30})

    result = db.select("id", 1)
    check("select(id=1) via PK index = 1", len(result) == 1)
    check("nombre correcto", result[0][1] == "Ana")

    # PK invalida
    try:
        DataBase("bad_pk", schema={"x": "int"}, primary_key="noexiste")
        check("Error: PK inexistente", False)
    except ValueError:
        check("Error: PK inexistente", True)

    cleanup()


# ================================================================== #
#  TEST 12: Schema JSON — formato nuevo                                #
# ================================================================== #

def test_schema_format():
    header("TEST 12: Schema JSON — formato nuevo")
    cleanup()

    schema = {"id": "int", "lat": "float", "lon": "float"}
    db = DataBase("geo_schema", schema=schema, primary_key="id")
    db.create_index(("lat", "lon"), index_type="rtree")

    # Leer el JSON directamente
    import json
    with open(os.path.join("schemas", "geo_schema.json"), "r") as f:
        raw = json.load(f)

    check("JSON tiene 'columns'", "columns" in raw)
    check("JSON tiene 'primary_key'", "primary_key" in raw)
    check("JSON tiene 'indexes'", "indexes" in raw)

    check("columns correcto", raw["columns"] == schema)
    check("primary_key = 'id'", raw["primary_key"] == "id")

    # Debe haber 2 indices: PK bplus + rtree
    check("2 indices en metadata", len(raw["indexes"]) == 2,
          f"got {len(raw['indexes'])}")

    idx_types = sorted([idx["type"] for idx in raw["indexes"]])
    check("Tipos: bplus + rtree", idx_types == ["bplus", "rtree"],
          f"got {idx_types}")

    # Verificar estructura de cada indice
    for idx_meta in raw["indexes"]:
        if idx_meta["type"] == "bplus":
            check("bplus: column='id', unique=True",
                  idx_meta["column"] == "id" and idx_meta["unique"] is True)
        elif idx_meta["type"] == "rtree":
            check("rtree: columns=['lat','lon']",
                  idx_meta["column"] == ["lat", "lon"])

    cleanup()


# ================================================================== #
#  TEST 13: Persistencia — recargar tabla con indices                  #
# ================================================================== #

def test_persistence():
    header("TEST 13: Persistencia — recargar tabla con indices")
    cleanup()

    schema = {"id": "int", "lat": "float", "lon": "float"}
    db = DataBase("geo_persist", schema=schema, primary_key="id")
    db.create_index(("lat", "lon"), index_type="rtree")

    db.insert({"id": 1, "lat": 10.0, "lon": 20.0})
    db.insert({"id": 2, "lat": 30.0, "lon": 40.0})
    db.insert({"id": 3, "lat": 50.0, "lon": 60.0})

    # Simular recarga: crear nueva instancia sobre la misma tabla
    db2 = DataBase("geo_persist")

    check("Schema recargado", db2.schema == schema)
    check("PK recargada", db2.primary_key == "id")
    check("Indice bplus recargado", db2.has_index("id"))
    check("Indice rtree recargado", db2.has_index(("lat", "lon")))

    # Verificar que los indices funcionan
    result = db2.select("id", 2)
    check("select(id=2) funciona post-recarga", len(result) == 1)
    check("datos correctos", result[0] == (2, 30.0, 40.0))

    knn = db2.select_knn("lat", "lon", 10.0, 20.0, 2)
    check("knn funciona post-recarga", len(knn) == 2)

    cleanup()


# ================================================================== #
#  TEST 14: Drop index persiste en schema                              #
# ================================================================== #

def test_drop_persists():
    header("TEST 14: Drop index persiste en schema")
    cleanup()

    schema = {"id": "int", "edad": "int"}
    db = DataBase("drop_test", schema=schema, primary_key="id")
    db.create_index("edad", index_type="bplus", unique=False)

    db.insert({"id": 1, "edad": 25})

    # Verificar: 2 indices (PK + edad)
    import json
    with open(os.path.join("schemas", "drop_test.json"), "r") as f:
        raw = json.load(f)
    check("2 indices antes de drop", len(raw["indexes"]) == 2)

    db.drop_index("edad")

    with open(os.path.join("schemas", "drop_test.json"), "r") as f:
        raw2 = json.load(f)
    check("1 indice despues de drop", len(raw2["indexes"]) == 1)
    check("Solo queda PK", raw2["indexes"][0]["column"] == "id")

    # Recargar y verificar
    db2 = DataBase("drop_test")
    check("has_index(id) post-recarga", db2.has_index("id"))
    check("no has_index(edad) post-recarga", not db2.has_index("edad"))

    cleanup()


# ================================================================== #
#  MAIN                                                               #
# ================================================================== #

if __name__ == "__main__":
    print()
    print("*" * 65)
    print("*    TESTS DE INTEGRACION: DataBase + Indices + Schema           *")
    print("*" * 65)

    test_no_index()
    test_create_index_existing_data()
    test_insert_updates_index()
    test_range_search()
    test_delete_updates_index()
    test_drop_index()
    test_volume()
    test_errors()
    test_rtree_queries()
    test_rtree_delete()
    test_primary_key()
    test_schema_format()
    test_persistence()
    test_drop_persists()

    print()
    print("=" * 65)
    print(f"  RESUMEN: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 65)
    print()

    if FAILED > 0:
        sys.exit(1)
