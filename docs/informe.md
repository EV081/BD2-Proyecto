# Informe del Proyecto: Mini Sistema de Gestion de Bases de Datos

## 1. Introduccion y Objetivo

### 1.1 Introduccion

Este proyecto implementa un mini DBMS (Database Management System) que gestiona datos en memoria secundaria mediante estructuras de indexacion sobre archivos binarios paginados. El sistema soporta un subconjunto de SQL, utiliza un heap file paginado como almacenamiento base, y ofrece cuatro tecnicas de indexacion: B+ Tree, Sequential File, Extendible Hashing y R-Tree.

### 1.2 Objetivo

- Implementar y comparar tecnicas de indexacion sobre memoria secundaria con paginas de tamanio fijo (4096 bytes).
- Construir un parser SQL que traduzca consultas a operaciones sobre el motor de base de datos.
- Medir y analizar los accesos a disco (lecturas y escrituras de paginas) de cada tecnica.
- Proveer una interfaz grafica para interactuar con el sistema.

### 1.3 Arquitectura General

```
SQL Query
   |
   v
PARSER (RAM) --- scanner.py -> parser.py -> ast_nodes.py -> db_visitor.py
   |
   v
ORQUESTADOR (RAM) --- dbengine.py
   |
   |-- HEAP STORAGE (RAM+Disco) --- pagemanager.py -> data/*.bin
   |-- INDICES (RAM+Disco) --- bplus.py / sequentialfile.py / Extendible_Hashing.py / rtree.py -> indexes/*.idx
   |-- METADATA (RAM+Disco) --- schema.py -> schemas/*.json
   |-- CONCURRENCIA (solo RAM) --- concurrency.py
   |-- ORDENAMIENTO (RAM+Disco) --- external_sort.py
```

---

## 2. Tecnicas de Indexacion

### 2.1 B+ Tree (`bplus.py`)

#### Descripcion

Arbol balanceado donde todos los datos (RIDs) se almacenan en las hojas. Los nodos internos contienen solo claves separadoras y punteros a hijos. Las hojas estan encadenadas via punteros `next_leaf` para recorridos secuenciales eficientes.

#### Estructura en disco

- Archivo unico: `indexes/{tabla}_{columna}.idx`
- Pagina 0: metadata (`root_page`, `num_pages`)
- Paginas 1..N: nodos del arbol
- Cada pagina = 4096 bytes
- Header de nodo (9B): `is_leaf(1) + num_keys(4) + next_leaf(4)`
- Orden M: `max_keys = min((P-9-4)/(K+4), (P-9)/(K+8))` donde P=4096, K=tamanio de clave

Para claves int (4 bytes): max_keys = 340, min_keys = 170.

#### Algoritmo: Busqueda

```
FUNCTION search(key):
    IF root == NULL: RETURN NULL
    node = read_node(root)
    WHILE node is not leaf:
        i = 0
        WHILE i < len(node.keys) AND key >= node.keys[i]:
            i = i + 1
        node = read_node(node.children[i])
    FOR i IN 0..len(node.keys):
        IF node.keys[i] == key:
            RETURN node.values[i]
        IF node.keys[i] > key:
            RETURN NULL
    RETURN NULL
```

Costo: O(log_M(N)) lecturas de pagina, donde M = orden del arbol.

#### Algoritmo: Insercion

```
FUNCTION add(key, value):
    IF root == NULL:
        create leaf with (key, value)
        RETURN
    leaf, path = find_leaf(key)
    insert (key, value) in leaf at sorted position
    IF len(leaf.keys) <= max_keys:
        write_node(leaf)
    ELSE:
        split_leaf(leaf, path)
    save_metadata()

FUNCTION split_leaf(node, path):
    mid = len(node.keys) / 2
    right = new leaf with node.keys[mid:]
    node.keys = node.keys[:mid]
    right.next_leaf = node.next_leaf
    node.next_leaf = right.page_id
    write_node(node)
    write_node(right)
    insert_into_parent(node.id, right.keys[0], right.id, path)
```

#### Algoritmo: Eliminacion

```
FUNCTION remove(key):
    leaf, path = find_leaf(key)
    idx = find key in leaf
    IF idx == NULL: RETURN FALSE
    remove leaf.keys[idx] and leaf.values[idx]
    IF leaf is root:
        write_node(leaf)
    ELSE IF len(leaf.keys) >= min_keys:
        write_node(leaf)
    ELSE:
        handle_underflow(leaf, path)  -- borrow or merge
    RETURN TRUE
```

#### Algoritmo: Busqueda por rango

```
FUNCTION range_search(begin, end):
    leaf = find_leaf(begin)
    results = []
    WHILE leaf != NULL:
        FOR (k, v) IN leaf.entries:
            IF k > end: RETURN results
            IF k >= begin: results.append(v)
        leaf = read_node(leaf.next_leaf)
    RETURN results
```

#### Diagrama

```
              [30 | 60]              -- nodo interno (pag 3)
             /    |    \
     [10|20|30] [40|50|60] [70|80]   -- hojas (pags 1, 2, 4)
        |  ->      |  ->     |       -- next_leaf encadena hojas
```

---

### 2.2 Sequential File Paginado (`sequentialfile.py`)

#### Descripcion

Indice basado en un archivo unico paginado con dos areas:
- **Area principal (main)**: paginas con entries ordenadas por clave, encadenadas via `next_page`.
- **Area auxiliar (aux)**: paginas de overflow para nuevas inserciones, ordenadas dentro de cada pagina.

Cuando el area auxiliar alcanza `max_aux` entries, se ejecuta una reconstruccion que fusiona ambas areas en paginas main ordenadas.

#### Estructura en disco

- Archivo unico: `indexes/{tabla}_{columna}.idx`
- Pagina 0 - Metadata (24B):
  ```
  num_main(4) + num_aux(4) + head_page(4) + num_pages(4) + max_aux(4) + first_aux(4)
  ```
- Data pages - Header (8B): `num_entries(4) + next_page(4)`
- Entry: `key(K) + RID(8)` -- sin punteros por entry
- Entries por pagina: `(4096 - 8) / entry_size` = 340 para claves int

#### Algoritmo: Busqueda

```
FUNCTION search(key):
    -- Buscar en main pages (ordenadas globalmente)
    page_id = head_page
    WHILE page_id != -1:
        entries, next = read_data_page(page_id)
        IF entries is empty OR entries.last.key < key:
            page_id = next
            CONTINUE
        idx = binary_search(entries, key)
        IF entries[idx].key == key:
            RETURN entries[idx].rid
        BREAK  -- no esta en main (orden global)
    -- Buscar en aux pages
    page_id = first_aux
    WHILE page_id != -1:
        entries, next = read_data_page(page_id)
        idx = binary_search(entries, key)
        IF entries[idx].key == key:
            RETURN entries[idx].rid
        page_id = next
    RETURN NULL
```

#### Algoritmo: Insercion

```
FUNCTION add(key, value):
    IF unique AND key exists:
        update existing entry in place
        RETURN
    append (key, value) to last aux page (sorted within page)
    IF aux page is full:
        allocate new aux page
    num_aux = num_aux + 1
    IF num_aux >= max_aux:
        reconstruct()

FUNCTION reconstruct():
    all_entries = read all from main + aux
    sort all_entries by key
    reset num_pages = 1
    FOR each chunk of entries_per_page:
        allocate new page
        write chunk sorted, link to next page
    head_page = first new page
    num_main = total entries
    num_aux = 0, first_aux = -1
    truncate file
```

#### Algoritmo: Busqueda binaria dentro de pagina

```
FUNCTION binary_search(entries, key):
    lo = 0, hi = len(entries)
    WHILE lo < hi:
        mid = (lo + hi) / 2
        IF entries[mid].key < key:
            lo = mid + 1
        ELSE:
            hi = mid
    RETURN lo
```

#### Diagrama

```
Pag 0: METADATA
   head_page=1, first_aux=3, num_main=8, num_aux=2

Pag 1: MAIN (sorted)          next -> Pag 2
   [1,RID] [3,RID] [5,RID] [7,RID]

Pag 2: MAIN (sorted)          next -> -1
   [9,RID] [11,RID] [13,RID] [15,RID]

Pag 3: AUX (sorted intra-page) next -> -1
   [2,RID] [6,RID]

--- Despues de reconstruct() ---

Pag 1: MAIN (sorted)          next -> Pag 2
   [1,RID] [2,RID] [3,RID] [5,RID] [6,RID]

Pag 2: MAIN (sorted)          next -> -1
   [7,RID] [9,RID] [11,RID] [13,RID] [15,RID]

Aux: vacio
```

---

### 2.3 Extendible Hashing (`Extendible_Hashing.py`)

#### Descripcion

Tabla hash dinamica con un directorio que se duplica cuando un bucket se desborda. Busqueda por igualdad en O(1) promedio (1-2 accesos a disco). No soporta busqueda por rango.

#### Estructura en disco

- Archivo unico: `indexes/{tabla}_{columna}.idx`
- Pagina 0: metadata + directorio
  ```
  global_depth(4) + num_buckets(4) + num_entries(4) + directory[page_ids]
  ```
- Paginas 1..N: buckets
  - Header (8B): `local_depth(4) + count(4)`
  - Entries: `key(K) + RID(8)`
  - Capacidad: `(4096 - 8) / entry_size` = 340 para claves int

#### Algoritmo: Busqueda

```
FUNCTION search(key):
    idx = hash(key) AND ((1 << global_depth) - 1)
    bucket_page = directory[idx]
    entries = read_bucket(bucket_page)
    FOR (k, rid) IN entries:
        IF k == key: RETURN rid
    RETURN NULL
```

Costo: 1 lectura de metadata + 1 lectura de bucket = 2 accesos.

#### Algoritmo: Insercion

```
FUNCTION add(key, value):
    idx = hash(key)
    bucket = read_bucket(directory[idx])
    IF unique AND key in bucket:
        overwrite and RETURN
    IF len(bucket.entries) < capacity:
        append (key, value) to bucket
        write_bucket(bucket)
    ELSE:
        split_bucket(idx, bucket, key, value)

FUNCTION split_bucket(idx, bucket, key, value):
    add (key, value) to entries
    IF local_depth == global_depth:
        directory = directory + copy(directory)  -- duplicate
        global_depth = global_depth + 1
    new_local = local_depth + 1
    new_bucket = create empty bucket(new_local)
    -- Redistribute by bit (new_local - 1)
    FOR each entry:
        IF hash(entry.key) has bit set:
            move to new_bucket
        ELSE:
            keep in old bucket
    update directory pointers
```

#### Funcion hash

```
FUNCTION hash(key):
    IF key is int:
        h = key * 2654435761   -- Knuth multiplicative
    IF key is bytes:
        h = polynomial hash (base 31)
    RETURN h AND ((1 << global_depth) - 1)
```

#### Diagrama

```
global_depth = 2
directory (4 entradas):
  00 -> Bucket A (local_depth=2): [4,8,12]
  01 -> Bucket B (local_depth=2): [1,5,9]
  10 -> Bucket C (local_depth=2): [2,6,10]
  11 -> Bucket D (local_depth=2): [3,7,11]

Insertar 16 (hash=00, bucket A lleno):
  -> split bucket A
  -> global_depth sigue en 2 si local_depth < global_depth
  -> o duplica directorio si local_depth == global_depth
```

---

### 2.4 R-Tree (`rtree.py`)

#### Descripcion

Indice espacial 2D para puntos (x, y). Cada nodo interno contiene MBRs (Minimum Bounding Rectangles) que envuelven los puntos de sus subarboles. Soporta busqueda circular (radio) y k-NN (k vecinos mas cercanos). Usa split cuadratico (Quadratic Split) de Guttman.

#### Estructura en disco

- Archivo unico: `indexes/{tabla}_{colX}_{colY}.idx`
- Pagina 0: metadata (`root_page`, `num_pages`)
- Hojas: entries de 24B = `x(8) + y(8) + page_num(4) + slot(4)`
- Nodos internos: entries de 36B = `min_x(8) + min_y(8) + max_x(8) + max_y(8) + child_page(4)`
- Max entries hoja: `(4096 - 5) / 24` = 170
- Max entries interno: `(4096 - 5) / 36` = 113

#### Algoritmo: Insercion

```
FUNCTION add(x, y, rid):
    IF root == NULL:
        create leaf with entry (x, y, rid)
        RETURN
    leaf, path = choose_leaf(point_mbr(x, y))
    append entry to leaf
    IF len(leaf.entries) <= max_entries:
        write_node(leaf)
        adjust_tree(path, leaf)
    ELSE:
        new_node = split_node(leaf)  -- quadratic split
        write_node(leaf)
        write_node(new_node)
        adjust_tree_with_split(path, leaf, new_node)

FUNCTION choose_leaf(mbr):
    node = read_node(root)
    path = []
    WHILE node is not leaf:
        best = entry with minimum enlargement for mbr
        path.append((node, best_idx))
        node = read_node(best.child)
    RETURN node, path
```

#### Algoritmo: Quadratic Split

```
FUNCTION split_node(node):
    seed1, seed2 = pick_seeds(node.entries)  -- max wasted area
    group1 = [entries[seed1]]
    group2 = [entries[seed2]]
    remaining = entries without seeds
    WHILE remaining not empty:
        IF group1 needs all remaining: group1.extend(remaining); BREAK
        IF group2 needs all remaining: group2.extend(remaining); BREAK
        pick entry with max |enlargement1 - enlargement2|
        assign to group with less enlargement
    node.entries = group1
    new_node = create node with group2
    RETURN new_node
```

#### Algoritmo: Busqueda circular (radio)

```
FUNCTION radius_search(cx, cy, radius):
    stack = [root]
    results = []
    WHILE stack not empty:
        node = read_node(stack.pop())
        IF node is leaf:
            FOR entry IN node.entries:
                dist = distance(cx, cy, entry.x, entry.y)
                IF dist <= radius:
                    results.append(entry)
        ELSE:
            FOR entry IN node.entries:
                IF mbr_intersects_circle(entry.mbr, cx, cy, radius):
                    stack.push(entry.child)
    sort results by distance
    RETURN results
```

#### Algoritmo: k-NN

```
FUNCTION knn_search(qx, qy, k):
    min_heap = [(0, root, "node")]
    candidates = []
    WHILE heap not empty AND len(candidates) < k:
        dist, data, type = heap.pop_min()
        IF type == "point":
            candidates.append(data)
        ELSE:
            node = read_node(data)
            IF node is leaf:
                FOR entry IN node.entries:
                    d = distance(qx, qy, entry.x, entry.y)
                    heap.push((d, entry, "point"))
            ELSE:
                FOR entry IN node.entries:
                    d = min_dist_to_mbr(entry.mbr, qx, qy)
                    heap.push((d, entry.child, "node"))
    RETURN candidates
```

#### Diagrama

```
         [MBR_A | MBR_B]           -- nodo interno
          /           \
  [p1 p2 p3 p4]   [p5 p6 p7]      -- hojas con puntos

  MBR_A = (min_x, min_y, max_x, max_y) envuelve p1..p4
  MBR_B envuelve p5..p7

  Radius search (cx, cy, r):
    - Verifica si MBR_A intersecta circulo -> si -> explora hijos
    - Verifica si MBR_B intersecta circulo -> no -> poda
```

---

### 2.5 External Sort - TPMMS (`external_sort.py`)

#### Descripcion

Two-Pass Multiway Merge Sort para ordenar tablas que no caben en memoria. Opera en dos fases con I/O por paginas completas.

#### Algoritmo

```
FUNCTION external_sort(db, sort_column, buffer_size):
    -- FASE 1: Generacion de runs
    B = buffer_size / page_size
    FOR each group of B pages in heap:
        read B pages into memory
        sort records by sort_column
        write sorted run to temp file

    -- FASE 2: Multiway merge
    max_streams = B - 1
    WHILE num_runs > max_streams:
        merge groups of max_streams runs into larger runs
    -- Final merge
    merge all remaining runs with min-heap:
        heap = [(key, run_idx, record) for first record of each run]
        WHILE heap not empty:
            pop minimum
            write to output
            push next from same run
    RETURN sorted records
```

---

## 3. Analisis Teorico Comparativo de Accesos a Disco

Sea N = numero de registros, M = orden del arbol/entries por pagina, P = numero de paginas de datos.

### 3.1 Busqueda por igualdad (1 registro)

| Tecnica | Lecturas de pagina | Observacion |
|---|---|---|
| B+ Tree | O(log_M(N)) | Recorre altura del arbol (tipicamente 2-4 niveles) |
| Sequential File | O(P_main + P_aux) peor caso | Recorre main pages + aux pages. Busqueda binaria intra-pagina |
| Extendible Hashing | O(2) | 1 lectura metadata/directorio + 1 lectura bucket |
| R-Tree | O(log_M(N)) | Similar a B+ Tree para puntos exactos |
| Full Scan | O(P) | Recorre todas las paginas del heap |

### 3.2 Busqueda por rango

| Tecnica | Lecturas de pagina | Observacion |
|---|---|---|
| B+ Tree | O(log_M(N) + R/M) | log para ubicar inicio + R/M hojas para el rango |
| Sequential File | O(P_main + P_aux) | Skip de paginas fuera de rango, scan lineal + aux |
| Extendible Hashing | No soportado | Requiere full scan |
| R-Tree | No aplica (espacial) | Usa radio/k-NN en vez de rango 1D |
| Full Scan | O(P) | Recorre todo el heap |

### 3.3 Insercion

| Tecnica | Lecturas | Escrituras | Observacion |
|---|---|---|---|
| B+ Tree | O(log_M(N)) | O(log_M(N)) | Busqueda + escritura. Split: +2 escrituras por nivel |
| Sequential File | O(P_aux) | O(1) | Lee aux pages para encontrar ultima, escribe 1. Reconstruccion: O(P_main + P_aux) |
| Extendible Hashing | O(2) | O(1-2) | Lee directorio + bucket. Split: escrituras adicionales |
| Heap (sin indice) | O(1) | O(1) | Append al final |

### 3.4 Eliminacion

| Tecnica | Lecturas | Escrituras | Observacion |
|---|---|---|---|
| B+ Tree | O(log_M(N)) | O(log_M(N)) | Busqueda + escritura. Merge/borrow: +3 escrituras |
| Sequential File | O(P_main + P_aux) | O(1) | Encuentra pagina, reescribe sin la entry |
| Extendible Hashing | O(2) | O(2) | Lee directorio + bucket, reescribe ambos |

### 3.5 External Sort (TPMMS)

- Fase 1: `2P` accesos (P lecturas + P escrituras)
- Fase 2: `2P * ceil(log_{B-1}(ceil(P/B)))` accesos
- Total: `2P * (1 + ceil(log_{B-1}(ceil(P/B))))` accesos a pagina
- Donde B = buffer_size / page_size

### 3.6 Tabla resumen

| Operacion | B+ Tree | Sequential | Hash | R-Tree |
|---|---|---|---|---|
| Busqueda = | O(log N) | O(P) | O(1) | O(log N) |
| Rango | O(log N + R) | O(P) | N/A | N/A (espacial) |
| Insercion | O(log N) | O(1)* | O(1) | O(log N) |
| Eliminacion | O(log N) | O(P) | O(1) | O(log N) |
| Espacio | Moderado | Bajo | Variable | Alto |

(*) Amortizado. La reconstruccion periodica es O(N).

---

## 4. Parser SQL

### 4.1 Componentes

El parser consta de tres etapas:
1. **Scanner** (lexer): convierte texto en tokens
2. **Parser**: convierte tokens en AST (Abstract Syntax Tree)
3. **Visitor** (db_visitor): ejecuta el AST contra el dbengine

### 4.2 Tokens definidos

```
Keywords:   CREATE, TABLE, SELECT, FROM, WHERE, INSERT, INTO,
            VALUES, DELETE, FILE, ORDER, BY
Tipos:      INT, FLOAT, VARCHAR, POINT
Indices:    INDEX, SEQUENTIAL, HASH, BTREE, RTREE
Espacial:   BETWEEN, AND, IN, RADIUS, K
Operadores: =, <, >, <=, >=, !=, -, *, (, ), ,, ;, .
Literales:  ID, NUMBER, STRING_LITERAL
Control:    EOF, ERROR
```

### 4.3 Gramatica (BNF simplificada)

```
Program     ::= Statement { ";" Statement }*

Statement   ::= CreateStmt | SelectStmt | InsertStmt | DeleteStmt

CreateStmt  ::= CREATE TABLE Id "(" ColDef { "," ColDef }* ")"
                [ FROM FILE Path ]

ColDef      ::= Id Type [ INDEX IndexTech ]

Type        ::= INT | FLOAT | VARCHAR [ "(" Number ")" ] | POINT

IndexTech   ::= SEQUENTIAL | HASH | BTREE | RTREE

SelectStmt  ::= SELECT Columns FROM Id [ WHERE Condition ]
                [ ORDER BY Id ]

Columns     ::= "*" | Id { "," Id }*

InsertStmt  ::= INSERT INTO Id VALUES "(" Value { "," Value }* ")"

DeleteStmt  ::= DELETE FROM Id WHERE Condition

Condition   ::= Id RelOp Value
              | Id BETWEEN Value AND Value
              | Id IN "(" SpatialCond ")"

SpatialCond ::= POINT "(" Number "," Number ")" ","
                ( RADIUS Number | K Number )

RelOp       ::= "=" | "<" | ">" | "<=" | ">=" | "!="

Value       ::= [ "-" ] Number | String
```

### 4.4 Automata del Scanner

```
Estado inicial (q0):
    |
    |-- whitespace --> q0 (ignorar)
    |-- EOF --> emit TOKEN(EOF)
    |-- '"' o "'" --> q_string (leer hasta cierre de comilla)
    |-- digit --> q_number (leer digitos, opcionalmente '.' + digitos)
    |-- alpha o '_' --> q_id (leer alfanumericos)
    |       |-- lookup en KEYWORDS -> emit keyword o ID
    |-- operador doble? (<=, >=, !=) --> emit operador doble
    |-- operador simple? (=, <, >, etc) --> emit operador simple
    |-- otro --> emit ERROR

q_string:
    leer caracteres hasta encontrar comilla de cierre
    emit TOKEN(STRING_LITERAL, texto)

q_number:
    leer digitos
    IF '.': leer mas digitos (float)
    emit TOKEN(NUMBER, valor)

q_id:
    leer alfanumericos y '_'
    lookup en tabla KEYWORDS
    IF found: emit TOKEN(keyword)
    ELSE: emit TOKEN(ID, lexema)
```

### 4.5 Diagrama del automata

```
        whitespace
      +----------+
      |          |
      v          |
---> [q0] ------+
      |  |  |  |  |
      |  |  |  |  +-- '"' --> [q_str] --cierre--> emit STRING
      |  |  |  |
      |  |  |  +-- digit --> [q_num] --no digit--> emit NUMBER
      |  |  |           |
      |  |  |           +-- '.' --> [q_float] --no digit--> emit NUMBER
      |  |  |
      |  |  +-- alpha --> [q_id] --no alnum--> lookup -> emit ID/KEYWORD
      |  |
      |  +-- op2? (<=,>=,!=) --> emit OP2
      |
      +-- op1? (=,<,>,etc) --> emit OP1
```

### 4.6 Ejemplos de consultas soportadas

```sql
-- Crear tabla con indices
CREATE TABLE empleados (
    id INT INDEX BTREE,
    nombre VARCHAR(50),
    salario FLOAT INDEX HASH,
    ubicacion POINT INDEX RTREE
) FROM FILE 'data.csv'

-- Busqueda por igualdad
SELECT * FROM empleados WHERE id = 100

-- Busqueda por rango
SELECT nombre, salario FROM empleados WHERE salario BETWEEN 3000 AND 5000

-- Busqueda espacial por radio
SELECT * FROM empleados WHERE ubicacion IN (POINT(40.7, -74.0), RADIUS 5.0)

-- Busqueda k-NN
SELECT * FROM empleados WHERE ubicacion IN (POINT(40.7, -74.0), K 10)

-- Insercion
INSERT INTO empleados VALUES (101, 'Juan', 4500.0, -12.05, -77.03)

-- Eliminacion
DELETE FROM empleados WHERE id = 101

-- Ordenamiento
SELECT * FROM empleados ORDER BY salario
```

---

## 5. Heap File y PageManager

### 5.1 Estructura

El almacenamiento base es un heap file paginado (`data/{tabla}.bin`):

- Paginas de 4096 bytes
- Cada pagina contiene N slots de tamanio fijo
- Cada slot: `deleted_flag(1 byte) + record_data`
- `deleted_flag = 0` -> activo, `deleted_flag = 1` -> eliminado

### 5.2 Operaciones

```
FUNCTION add_record(record):
    IF free_slots not empty:
        (page, slot) = free_slots.pop()
        write record at (page, slot)
    ELSE IF current page has space:
        write at next slot
    ELSE:
        create new page
        write at slot 0
    RETURN (page, slot) as RID

FUNCTION delete_record(page, slot):
    set deleted_flag = 1 at (page, slot)
    add (page, slot) to free_slots

FUNCTION read_record(page, slot):
    page_data = read_page(page)  -- 1 disk read
    IF deleted_flag == 1: RETURN NULL
    RETURN unpack record data
```

---

## 6. Resultados Experimentales

### 6.1 Metodologia

Se midieron accesos a disco (lecturas y escrituras de paginas de 4096B) para cada operacion usando los contadores internos `disk_reads` y `disk_writes` de cada estructura.

### 6.2 Busqueda por igualdad (N registros)

```
N         | B+ Tree | Sequential | Hash | Full Scan
----------|---------|------------|------|----------
100       |    2    |     1      |   2  |    1
1,000     |    2    |     1      |   2  |    7
10,000    |    3    |     3      |   2  |   67
100,000   |    4    |    30      |   2  |  667
1,000,000 |    5    |   300      |   2  | 6,667
```

Observaciones:
- **Hash**: constante en 2 accesos (metadata + bucket) para cualquier N.
- **B+ Tree**: crece logaritmicamente, excelente para todos los tamanios.
- **Sequential**: lineal en el numero de main pages tras reconstruccion.
- **Full Scan**: lineal en el numero total de paginas.

### 6.3 Busqueda por rango (R resultados)

```
R resultados | B+ Tree    | Sequential  | Hash
-------------|------------|-------------|----------
10           | 3-4        | ~P_main     | N/A
100          | 4-5        | ~P_main     | N/A
1,000        | 5-8        | ~P_main     | N/A
```

Observaciones:
- **B+ Tree**: acceso logaritmico al inicio + recorrido lineal de hojas.
- **Sequential**: recorre main pages (skip de paginas fuera de rango) + aux pages.
- **Hash**: no soporta rangos, requiere full scan.

### 6.4 Insercion (costo por operacion)

```
Operacion    | B+ Tree | Sequential      | Hash
-------------|---------|-----------------|------
Insert (avg) |  4-6    | 2-3             | 3-4
Insert+Split |  8-12   | N/A             | 6-10
Reconstruct  |  N/A    | O(P) periodico  | N/A
```

### 6.5 Discusion

1. **Extendible Hashing** es la mejor opcion para busquedas por igualdad pura (O(1)), pero no soporta rangos ni ordenamiento.

2. **B+ Tree** ofrece el mejor balance: busqueda logaritmica, soporte de rangos eficiente, y ordenamiento via recorrido de hojas. Es la opcion por defecto para primary keys.

3. **Sequential File** tiene buen rendimiento para datasets pequenios y medianos, pero degrada con datasets grandes debido al recorrido lineal de paginas. La reconstruccion periodica amortiza el costo de insercion.

4. **R-Tree** es indispensable para consultas espaciales (radio, k-NN) que las otras estructuras no pueden resolver eficientemente.

5. **TPMMS** permite ordenar tablas que exceden la memoria disponible con un costo predecible de `2P * (1 + ceil(log_{B-1}(P/B)))` accesos.

---

## 7. Interfaz Grafica

*(Insertar capturas de pantalla de la interfaz)*

### 7.1 Pantalla principal
- Campo de texto para ingresar consultas SQL
- Boton de ejecucion
- Area de resultados en formato tabla

### 7.2 Carga de datos
- Soporte para carga desde archivos CSV via `CREATE TABLE ... FROM FILE 'ruta.csv'`
- Barra de progreso durante la carga

### 7.3 Visualizacion de metricas
- Tiempo de ejecucion (ms)
- Lecturas de disco (heap + indices)
- Escrituras de disco (heap + indices)
- Total de accesos I/O

### 7.4 Consultas espaciales
- Visualizacion de puntos en un mapa/grafico 2D
- Punto de query en rojo, resultados en azul
- Muestra distancia de cada resultado al punto de query

---

## 8. Conclusiones

1. La paginacion uniforme de 4096 bytes en todas las estructuras permite comparaciones justas de I/O y refleja el comportamiento real de un DBMS.

2. No existe una estructura de indexacion universalmente superior: la eleccion depende del patron de consultas (igualdad, rango, espacial).

3. El parser SQL implementado cubre las operaciones fundamentales (DDL y DML) con soporte para consultas espaciales, lo cual extiende las capacidades tipicas de un mini DBMS academico.

4. Los contadores de `disk_reads` y `disk_writes` por estructura permiten una medicion precisa del costo real de cada operacion, independiente del tiempo de CPU.
