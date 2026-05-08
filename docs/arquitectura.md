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
| **`dbms/structures/sequentialfile.py`** | Índice secuencial → `indexes/{t}_{c}.idx` + `_aux.idx` | Archivo principal + auxiliar con punteros encadenados |
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
| **`dbms/structures/sequentialfile.py`** | `num_main`, `num_aux`, puntero `head`, entries durante traversal |
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
              │ SeqFile     │──_read_entry→ indexes/*_aux   │
              │  (head,ptrs)│←─entry data─│  (main+aux)     │
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

### Sequential File (`sequentialfile.py`)

- **Disco**: Dos archivos — principal (`*.idx`) y auxiliar (`*_aux.idx`)
  - Header del principal: `num_main(4) + num_aux(4) + head_file(1) + head_pos(4) + max_aux(4)`
  - Entries: `key + RID(8B) + next_ptr(file_id[1] + pos[4])`
- **RAM**: Puntero `head`, contadores `num_main/num_aux`, entries durante traversal
- **Reconstrucción**: Cuando `num_aux >= max_aux`, merge de ambos archivos en uno ordenado

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

## Resumen de Clasificación

| Clasificación | Archivos |
|---|---|
| **Solo RAM** | `concurrency.py`, `parser/*` (scanner, parser, ast_nodes, visitor, db_visitor, lexer_token) |
| **Solo Disco** | `data/*.bin`, `indexes/*.idx`, `schemas/*.json` (archivos generados en runtime) |
| **Puente RAM↔Disco** | `pagemanager.py`, `bplus.py`, `sequentialfile.py`, `Extendible_Hashing.py`, `rtree.py`, `schema.py`, `external_sort.py` |
| **Orquestador (RAM, delega I/O)** | `dbengine.py` |
