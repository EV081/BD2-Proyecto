# Arquitectura del DBMS — Memoria Primaria vs Secundaria

## Arquitectura General

```
SQL Query
   ↓
PARSER (RAM) ─── scanner.py → parser.py → ast_nodes.py → db_visitor.py
   ↓
ORQUESTADOR (RAM) ─── dbengine.py
   ↓
   ├── HEAP STORAGE (RAM+Disco) ─── pagemanager.py → data/*.bin
   ├── ÍNDICES (RAM+Disco) ─── bplus.py / sequentialfile.py / Extendible_Hashing.py / rtree.py → indexes/*.idx
   ├── METADATA (RAM+Disco) ─── schema.py → schemas/*.json
   ├── CONCURRENCIA (solo RAM) ─── concurrency.py
   └── ORDENAMIENTO (RAM+Disco temporal) ─── external_sort.py
```

---

## Archivos que usan MEMORIA SECUNDARIA (Disco)

| Archivo | Qué almacena en disco | Formato |
|---|---|---|
| **`dbms/utils/pagemanager.py`** | Datos de tablas → `data/*.bin` | Páginas fijas de 4096B con registros + flag de borrado |
| **`dbms/structures/bplus.py`** | Índice B+ Tree → `indexes/{tabla}_{col}.idx` | Página 0 = metadata, nodos internos/hojas en páginas |
| **`dbms/structures/sequentialfile.py`** | Índice secuencial → `indexes/{t}_{c}.idx` (archivo único paginado) | Página 0 = metadata, main pages + aux pages en páginas de 4096B |
| **`dbms/structures/Extendible_Hashing.py`** | Índice hash → `indexes/{t}_{c}.idx` | Directorio + buckets en páginas |
| **`dbms/structures/rtree.py`** | Índice espacial → `indexes/{t}_{cx}_{cy}.idx` | Nodos con MBRs en páginas |
| **`dbms/utils/schema.py`** | Esquemas → `schemas/{tabla}.json` | JSON con columnas, tipos, PK, índices |
| **`dbms/utils/external_sort.py`** | Archivos temporales durante sort | Runs temporales en disco |

Todos estos usan operaciones como `seek()`, `read()`, `write()` sobre archivos binarios, y mantienen contadores `disk_reads` / `disk_writes`.

---

## Archivos que usan MEMORIA PRIMARIA (RAM)

| Archivo | Qué mantiene en RAM |
|---|---|
| **`dbms/dbengine.py`** | `self.schema` (dict), `self.indexes` (objetos), `self.record_count`, `self.point_columns` |
| **`dbms/utils/pagemanager.py`** | `free_slots` (lista de huecos), `last_page/last_slot`, buffers de página (`bytearray(4096)`) |
| **`dbms/structures/bplus.py`** | Nodos deserializados (dict con keys/values/children), path de traversal, `root_page`, `max_keys` |
| **`dbms/structures/sequentialfile.py`** | `head_page`, `first_aux`, contadores `num_main/num_aux`, entries deserializadas por página durante traversal |
| **`dbms/structures/Extendible_Hashing.py`** | `self.directory` (lista de page IDs), `global_depth`, entries de bucket en RAM |
| **`dbms/structures/rtree.py`** | Nodos con bounding boxes, priority queue (`heapq`) para k-NN |
| **`dbms/structures/concurrency.py`** | **100% RAM** — `_page_locks`, `_tx_locks`, grafo wait-for para deadlock detection |
| **`dbms/parser/*`** | AST completo, tokens, tablas de símbolos — todo en RAM |
| **`dbms/utils/external_sort.py`** | Buffer de ordenamiento, min-heap para k-way merge |

---

## Flujo de I/O (RAM ↔ Disco)

```
                    RAM                          DISCO
              ┌─────────────┐            ┌──────────────────┐
  Consulta →  │ Parser/AST  │            │                  │
              │ DBEngine    │──read_page──→ data/tabla.bin   │
              │  ↕          │←─bytearray──│  (heap pages)    │
              │ PageManager │──write_page─→                  │
              │             │            │                  │
              │ BPlusTree   │──_read_node─→ indexes/*.idx   │
              │  (node dict)│←─unmarshal──│  (B+ pages)     │
              │             │──_write_node→                  │
              │             │            │                  │
              │ SeqFile     │─_read_data  │                  │
              │  (entries   │  _page()───→ indexes/*.idx    │
              │   per page) │←─page buf──│  (main+aux pags) │
              │             │            │                  │
              │ ExtHash     │──_read_page─→ indexes/*.idx   │
              │ (directory) │←─bucket────│  (hash buckets)  │
              │             │            │                  │
              │ SchemaManager│──json.load─→ schemas/*.json  │
              │  (dict)     │──json.dump──→                  │
              │             │            │                  │
              │ LockManager │            │  (sin disco)      │
              │  (locks,    │            │                  │
              │   wait-for) │            │                  │
              └─────────────┘            └──────────────────┘
```

---

## Detalle por Estructura de Índice

### B+ Tree (`bplus.py`)

- **Disco**: Archivo `indexes/{tabla}_{columna}.idx`
  - Página 0: metadata (`root_page` + `num_pages`)
  - Nodos internos: header (9B) + keys + punteros a hijos
  - Nodos hoja: header (9B) + keys + RIDs (page_num, slot)
- **RAM**: Nodos se deserializan a dicts `{"is_leaf", "keys", "values"/"children", "next_leaf"}`
- **Operaciones de disco**: `_read_page_raw()`, `_write_page_raw()`, `_read_node()`, `_write_node()`

### Sequential File (`sequentialfile.py`) — Paginado

Archivo único paginado con área principal ordenada y área auxiliar de overflow.

- **Disco**: Archivo único `indexes/{tabla}_{columna}.idx`
  - **Página 0 — Metadata (24B)**:
    ```
    num_main(4) + num_aux(4) + head_page(4) + num_pages(4) + max_aux(4) + first_aux(4)
    ```
  - **Main pages**: entries ordenadas por key, encadenadas via `next_page` en header de página
  - **Aux pages**: overflow para inserciones nuevas, ordenadas dentro de cada página
  - **Header de data page (8B)**: `num_entries(4) + next_page(4)`
  - **Entry**: `key(key_size) + RID(page_num[4] + slot[4])` — sin punteros por entry
  - **Entries por página**: `(4096 - 8) / entry_size` ≈ 340 para claves `int`
- **RAM**: `head_page`, `first_aux`, contadores `num_main/num_aux`, entries deserializadas por página
- **Búsqueda**: Binaria dentro de cada página (`_bisect_left`), skip de páginas por rango de keys
- **Reconstrucción**: Cuando `num_aux >= max_aux`, merge de main+aux en páginas main ordenadas
- **Operaciones de disco**: `_read_page_raw()`, `_write_page_raw()`, `_read_data_page()`, `_write_data_page()`

#### Layout del archivo en disco

```
┌──────────────────────────────────────────────────────┐
│ Página 0: METADATA                                   │
│   num_main | num_aux | head_page | num_pages          │
│   max_aux  | first_aux                                │
├──────────────────────────────────────────────────────┤
│ Página 1: MAIN PAGE (sorted)          next → Pág 2   │
│   [key₁,RID₁] [key₂,RID₂] ... [keyₙ,RIDₙ]          │
├──────────────────────────────────────────────────────┤
│ Página 2: MAIN PAGE (sorted)          next → -1      │
│   [keyₙ₊₁,RIDₙ₊₁] ...                               │
├──────────────────────────────────────────────────────┤
│ Página 3: AUX PAGE (sorted intra-page) next → -1     │
│   [keyₓ,RIDₓ] ... (overflow inserts)                 │
└──────────────────────────────────────────────────────┘
```

#### Flujo de búsqueda

```
search(key=42)
  │
  ├─ Main pages (head_page → next_page → ...)
  │    │
  │    ├─ Pág 1: last_key=30 < 42 → SKIP
  │    ├─ Pág 2: last_key=50 ≥ 42 → binary search → FOUND ✓
  │    └─ (short-circuit: no lee más páginas)
  │
  └─ Aux pages (solo si no encontrado en main)
       └─ Pág 3: binary search dentro de la página
```

#### Reconstrucción

```
ANTES (num_aux ≥ max_aux)              DESPUÉS
┌─────────────┐ ┌─────────────┐       ┌─────────────┐
│ Main pág 1  │ │ Aux pág 3   │       │ Main pág 1  │ (todo sorted)
│ [1,3,5,7]   │ │ [2,6,8]     │ ───→  │ [1,2,3,5,6] │
├─────────────┤ └─────────────┘       ├─────────────┤
│ Main pág 2  │                       │ Main pág 2  │
│ [9,11,13]   │                       │ [7,8,9,11,13]│
└─────────────┘                       └─────────────┘
                                      Aux: vacío
                                      Archivo truncado
```

**Consistencia multi-índice**: La reconstrucción solo reorganiza las páginas internas del SequentialFile. Los RIDs `(page, slot)` apuntan al heap (`data/*.bin`) que NO se modifica, por lo que otros índices (B+Tree, Hash, R-Tree) permanecen válidos.

### Extendible Hashing (`Extendible_Hashing.py`)

- **Disco**: Archivo `indexes/{tabla}_{columna}.idx`
  - Página 0: `global_depth(4) + num_buckets(4) + num_entries(4) + directory[]`
  - Buckets: `local_depth(4) + count(4) + entries[key + RID]`
- **RAM**: `self.directory` (lista de page IDs), `global_depth`, entries deserializadas
- **Split**: Cuando un bucket se llena, se duplica el directorio si es necesario

### R-Tree (`rtree.py`)

- **Disco**: Archivo `indexes/{tabla}_{col_x}_{col_y}.idx`
  - Página 0: metadata (`root_page + num_pages`)
  - Hojas: entries con `x(8) + y(8) + page_num(4) + slot(4)` = 24B
  - Nodos internos: MBRs con `min_x + min_y + max_x + max_y(8 cada uno) + child_page(4)` = 36B
- **RAM**: Nodos con bounding boxes, `heapq` para k-NN

---

## PageManager — El Puente Central

`dbms/utils/pagemanager.py` es el componente más crítico del flujo RAM↔Disco:

| Operación | Disco | RAM |
|---|---|---|
| `read_page(page_num)` | seek + read 4096B | → `bytearray` en RAM |
| `write_page(page_num, data)` | seek + write 4096B | ← `bytearray` desde RAM |
| `read_record(page, slot)` | Lee página completa | Extrae registro específico |
| `write_record(page, slot, record)` | Read-modify-write | Modifica buffer, reescribe página |
| `add_record(record)` | Asigna slot, escribe | Actualiza `free_slots`, `last_page` |
| `delete_record(page, slot)` | Marca flag borrado | Agrega a `free_slots` |

---

## drop_index — Limpieza de archivos

`dbengine.py:drop_index()` elimina el índice del diccionario en RAM **y borra los archivos de disco** asociados (`index_file`, `main_file`, `aux_file`). Esto evita que un archivo de índice de un tipo anterior (ej. B+Tree) corrompa un índice nuevo de otro tipo (ej. Sequential) creado sobre la misma columna.

---

## Resumen de Clasificación

| Clasificación | Archivos |
|---|---|
| **Solo RAM** | `concurrency.py`, `parser/*` (scanner, parser, ast_nodes, visitor, db_visitor, lexer_token) |
| **Solo Disco** | `data/*.bin`, `indexes/*.idx`, `schemas/*.json` (archivos generados en runtime) |
| **Puente RAM↔Disco** | `pagemanager.py`, `bplus.py`, `sequentialfile.py`, `Extendible_Hashing.py`, `rtree.py`, `schema.py`, `external_sort.py` |
| **Orquestador (RAM, delega I/O)** | `dbengine.py` |
