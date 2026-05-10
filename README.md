# Informe Tecnico: Mini Sistema de Gestion de Bases de Datos

**Proyecto 1 — Base de Datos II (CS2042)**
**Universidad de Ingenieria y Tecnologia (UTEC)**

---

Presentación grabada en: [Grabación](https://drive.google.com/file/d/1h8ZmYeeNjYH2g-VXkvrgvBhSr_cELIAv/view?usp=drive_link)

## 1. Introduccion y Objetivo

### 1.1 Introduccion

Este proyecto implementa un mini DBMS (Database Management System) que gestiona datos en memoria secundaria mediante estructuras de indexacion sobre archivos binarios paginados. El sistema soporta un subconjunto de SQL, utiliza un heap file paginado como almacenamiento base, y ofrece cuatro tecnicas de indexacion implementadas desde cero: B+ Tree, Sequential File, Extendible Hashing y R-Tree.

Toda la persistencia se realiza sobre paginas de tamanio fijo de **4096 bytes**, lo que permite una comparacion justa del costo de I/O entre las distintas tecnicas. El sistema incluye ademas un parser SQL con analisis lexico y sintactico, un modulo de concurrencia con Strict 2PL y deteccion de deadlocks, y un ordenamiento externo (TPMMS).

### 1.2 Objetivos

- Implementar y comparar tecnicas de indexacion sobre memoria secundaria con paginas de tamanio fijo (4096 bytes).
- Construir un parser SQL completo (scanner + parser recursivo descendente) que traduzca consultas a operaciones sobre el motor de base de datos.
- Medir y analizar los accesos a disco (lecturas y escrituras de paginas) de cada tecnica con datasets de 1K, 10K y 100K registros.
- Implementar un modulo de concurrencia con bloqueos a nivel de pagina y deteccion de deadlocks.
- Proveer una API REST y una interfaz grafica para interactuar con el sistema.

### 1.3 Arquitectura General

![arquitectura](docs/img/arquitectura.png)

El frontend mapea las consultas y las envia al backen, el cual inicia el siguiente flujo de ejecucion:

1. **Parser** (RAM): El scanner tokeniza la consulta SQL, el parser construye un AST, y el DBVisitor lo ejecuta.
2. **Orquestador** (RAM): `DataBase` (dbengine.py) coordina la interaccion entre almacenamiento, indices y metadata.
3. **Storage + Indices** (RAM <-> Disco): PageManager realiza I/O de paginas de 4096B; cada estructura de indexacion serializa/deserializa sus nodos sobre estas paginas.

![flujo](docs/img/flujo.png)

---

## 2. Tecnicas de Indexacion

### 2.1 B+ Tree (`bplus.py`)

Es un árbol balanceado donde todos los datos (RIDs) se almacenan en las hojas. Los nodos internos contienen solo claves separadoras y punteros a hijos. Las hojas estan encadenadas via punteros `next_leaf` para recorridos secuenciales eficientes.

#### Estructura en disco

- Archivo unico: `indexes/{tabla}_{columna}.idx`
- **Pagina 0**: metadata (`root_page`, `num_pages`)
- **Paginas 1..N**: nodos del arbol
- Cada pagina = 4096 bytes
- Header de nodo (9B): `is_leaf(1) + num_keys(4) + next_leaf(4)`
- Orden M: `max_keys = min((P-9-4)/(K+4), (P-9)/(K+8))` donde P=4096, K=tamaño de clave

Para claves `int` (4 bytes): max_keys = 340, min_keys = 170.

#### Algoritmo: Busqueda

```
FUNCTION search(key):
    IF root == NULL: 
        RETURN NULL
    node = read_node(root)
    WHILE node is not leaf:
        i = 0
        WHILE i < len(node.keys) AND key >= node.keys[i]:
            i = i + 1
        node = read_node(node.children[i])    //1 lectura de pagina
    FOR i IN 0..len(node.keys):
        IF node.keys[i] == key:
            RETURN node.values[i]
        IF node.keys[i] > key:
            RETURN NULL
    RETURN NULL
```

**Costo**: O(log_M(N)) lecturas de pagina, donde M = orden del árbol. Para 100K registros con M=340, la altura es 2-3 niveles = 3-4 accesos.

#### Algoritmo: Inserción

```
FUNCTION add(key, value):
    IF root == NULL:
        create leaf with (key, value)
        RETURN
    leaf, path = find_leaf(key)
    insert (key, value) in leaf at sorted position
    IF len(leaf.keys) <= max_keys:
        write_node(leaf)                       // 1 escritura
    ELSE:
        split_leaf(leaf, path)                 // 2-3 escrituras

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

#### Algoritmo: Busqueda por rango

```
FUNCTION range_search(begin, end):
    leaf = find_leaf(begin)                    // O(log_M(N)) lecturas
    results = []
    WHILE leaf != NULL:
        FOR (k, v) IN leaf.entries:
            IF k > end: RETURN results
            IF k >= begin: results.append(v)
        leaf = read_node(leaf.next_leaf)       // 1 lectura por hoja
    RETURN results
```

**Costo**: O(log_M(N) + R/M) donde R = número de resultados.

#### Algoritmo: Eliminacion

```
FUNCTION remove(key):
    leaf, path = find_leaf(key)
    idx = find key in leaf
    IF idx == NULL: 
        RETURN FALSE
    remove leaf.keys[idx] and leaf.values[idx]
    IF leaf is root OR len(leaf.keys) >= min_keys:
        write_node(leaf)
    ELSE:
        handle_underflow(leaf, path)           // borrow or merge
    RETURN TRUE
```

#### Consideraciones de implementación

- **Páginas de tamaño fijo (4096B)**: Cada nodo ocupa exactamente una página. El header del nodo (9B: `is_leaf(1) + num_keys(4) + next_leaf(4)`) reduce el espacio útil a 4087B. El orden M se calcula en función del tamaño de la clave K: para INT (K=4B), M=340 claves por nodo.
- **Busqueda por rango via hojas encadenadas**: Las hojas mantienen un puntero `next_leaf` que encadena todas las hojas de izquierda a derecha. `range_search(begin, end)` ubica la hoja de `begin` en O(log_M(N)) y luego recorre las hojas encadenadas hasta superar `end`. Solo se leen las hojas del rango, no todo el árbol.
- **Split de nodos**: Cuando una hoja supera M claves, se divide en dos: la mitad izquierda se queda, la derecha va a un nuevo nodo. La clave separadora sube al padre. Si el padre tambien se desborda, el split se propaga hacia arriba (potencialmente creando una nueva raiz y aumentando la altura).
- **Indice secundario vs primario**: El B+ Tree almacena pares `(key, RID)` donde RID = (page_num, slot) apunta al HeapFile. Es un indice no-clustered: el orden de los datos en el heap no coincide con el orden de las claves en el árbol.

#### Diagrama

![B+ Tree](docs/img/diagramabplus.png)

---

### 2.2 Sequential File Paginado (`sequentialfile.py`)

#### Descripcion

El Sequential File se organiza en un unico archivo paginado con dos zonas bien diferenciadas:
- **Area principal (main)**: contiene paginas contiguas con entradas ordenadas por clave. Esto permite hacer busqueda binaria sobre paginas y mantener un acceso eficiente.
- **Area auxiliar (aux)**: actua como zona de overflow para inserciones recientes. Sus paginas tambien mantienen orden local y se enlazan como una lista.

Cuando el area auxiliar alcanza `max_aux` entradas, el sistema ejecuta una **reconstruccion** para fusionar ambas zonas y volver a dejar las paginas main ordenadas.

El indice puede trabajar en dos modos:
- **Clustered**: almacena el registro completo y actua como almacenamiento primario.
- **Index**: almacena pares `(key, RID)` y funciona como indice secundario sobre el HeapFile.

#### Estructura en disco

- Archivo unico: `indexes/{tabla}_{columna}.idx`
- **Pagina 0 - Metadata (28B)**:
  ```
  num_main(4) + num_aux(4) + head_page(4) + num_pages(4)
  + max_aux(4) + first_aux(4) + num_deleted(4)
  ```
- **Data pages - Header (8B)**: `num_entries(4) + next_page(4)`
- **Entry**: `key(K) + value(V)` (registro completo en clustered, RID en index)
- Entradas por pagina: `(4096 - 8) / entry_size`

#### Algoritmo: Busqueda (search)

Despues de una reconstruccion, las paginas main quedan contiguas en el rango `[head_page, head_page + N - 1]`. Eso permite hacer busqueda binaria usando directamente los numeros de pagina:

```
FUNCTION search(key):
    -- Fase 1: Binary search sobre paginas main contiguas
    nmp = num_main_pages()
    lo = head_page
    hi = head_page + nmp - 1
    WHILE lo <= hi:
        mid = (lo + hi) / 2
        entries = read_data_page(mid)          -- 1 lectura de pagina
        IF key < entries[0].key:
            hi = mid - 1
        ELIF key > entries[-1].key:
            lo = mid + 1
        ELSE:
            idx = binary_search(entries, key)  -- busqueda binaria intra-pagina
            IF entries[idx].key == key:
                RETURN entries[idx].value
            BREAK
    -- Fase 2: Scan lineal en aux pages (linked list)
    page_id = first_aux
    WHILE page_id != -1:
        entries, next = read_data_page(page_id)  -- 1 lectura por pagina aux
        idx = binary_search(entries, key)
        IF entries[idx].key == key:
            RETURN entries[idx].value
        page_id = next
    RETURN NULL
```

**Costo**: O(log(P_main)) + O(P_aux) lecturas de pagina. Para 100K registros con P_main ~200 paginas: ~8 accesos a main + pocas paginas aux.

#### Algoritmo: Insercion (add)

```
FUNCTION add(key, value):
    -- Verificar duplicado en main (binary search sobre paginas)
    result = find_main_page(key)
    IF unique AND result != NULL:
        page_id, entries, next = result
        idx = binary_search(entries, key)
        IF entries[idx].key == key:
            entries[idx].value = value         -- update in place
            write_data_page(page_id, entries)  -- 1 escritura
            RETURN

    -- Verificar duplicado en aux (scan lineal)
    IF unique:
        FOR each aux_page:
            IF key found: update in place, RETURN

    -- Insertar en ultima pagina aux (sorted dentro de la pagina)
    IF first_aux == -1:
        pid = alloc_page()
        write_data_page(pid, [(key, value)])
        first_aux = pid
        last_aux = pid                         -- cache para O(1)
    ELIF last_aux page has space:
        idx = bisect_left(entries, key)
        entries.insert(idx, (key, value))      -- mantener orden intra-pagina
        write_data_page(last_aux, entries)     -- 1 escritura
    ELSE:
        new_pid = alloc_page()
        write_data_page(new_pid, [(key, value)])
        link last_aux -> new_pid
        last_aux = new_pid                     -- actualizar cache

    num_aux += 1
    IF num_aux >= max_aux:
        reconstruct()                          -- merge main + aux
```

**Costo**: O(log(P_main) + P_aux) para chequeo de duplicados + O(1) para el append. Reconstruct periodico es O(N) cada max_aux inserciones.

#### Algoritmo: Reconstruccion (reconstruct)

Cuando `num_aux >= max_aux`, se fusionan las areas main y aux en nuevas paginas main ordenadas:

```
FUNCTION reconstruct():
    -- Fase 1: Recolectar todas las entradas activas
    all_entries = []
    FOR each main_page (traverse linked list):
        FOR each entry in page:
            IF NOT deleted: all_entries.append(entry)
    FOR each aux_page (traverse linked list):
        FOR each entry in page:
            IF NOT deleted: all_entries.append(entry)

    -- Fase 2: Ordenar por clave
    sort(all_entries, by key)

    -- Fase 3: Escribir paginas main nuevas (contiguas)
    num_pages = 1                              -- reservar pag 0 para metadata
    FOR i = 0 TO len(all_entries) STEP entries_per_page:
        chunk = all_entries[i : i + entries_per_page]
        pid = alloc_page()
        next = pid + 1 si hay mas, sino -1
        write_data_page(pid, chunk, next)

    -- Fase 4: Actualizar metadata
    head_page = 1 (primera main page)
    num_main = len(all_entries)
    num_aux = 0, first_aux = -1, last_aux = -1
    num_deleted = 0                            -- compaction completa
    truncate file (eliminar paginas sobrantes)

    -- Fase 5: Notificar indices secundarios (modo clustered)
    IF clustered AND on_reconstruct callback:
        on_reconstruct()                       -- reconstruir indices secundarios
```

**Costo total**: O(P_main + P_aux) lecturas + O(N/M) escrituras + O(N log N) en RAM.

**Consideracion de implementacion**: El umbral `max_aux` controla la frecuencia de reconstruccion. Un valor alto (e.g., N/10) reduce reconstrucciones pero aumenta el costo de busqueda en aux. Un valor bajo (e.g., `entries_per_page`) reconstruye frecuentemente pero mantiene aux pequenio. En la practica se usa `max(62, N/10)`.

#### Algoritmo: Busqueda por rango (rangeSearch)

```
FUNCTION range_search(begin_key, end_key):
    results = []

    -- Fase 1: Binary search en main para primera pagina con last_key >= begin_key
    nmp = num_main_pages()
    lo = head_page
    hi = head_page + nmp - 1
    start_page = NULL
    WHILE lo <= hi:
        mid = (lo + hi) / 2
        entries = read_data_page(mid)
        IF entries[-1].key >= begin_key:
            start_page = mid
            hi = mid - 1                       -- buscar mas a la izquierda
        ELSE:
            lo = mid + 1

    -- Fase 2: Scan secuencial desde start_page hasta end_key
    IF start_page != NULL:
        page_id = start_page
        WHILE page_id < head_page + nmp:
            entries = read_data_page(page_id)  -- 1 lectura por pagina contigua
            IF entries[0].key > end_key: BREAK -- poda: ya pasamos el rango
            idx = bisect_left(entries, begin_key)
            WHILE idx < len(entries) AND entries[idx].key <= end_key:
                IF NOT deleted: results.append(entries[idx])
                idx += 1
            page_id += 1                       -- paginas contiguas, acceso secuencial

    -- Fase 3: Scan lineal en aux (no esta ordenado, orden de llegada hasta llenar max_aux)
    page_id = first_aux
    WHILE page_id != -1:
        entries, next = read_data_page(page_id)
        idx = bisect_left(entries, begin_key)
        WHILE idx < len(entries) AND entries[idx].key <= end_key:
            IF NOT deleted: results.append(entries[idx])
            idx += 1
        page_id = next

    sort(results, by key)                      -- merge de main + aux
    RETURN results
```

**Costo**: O(log(P_main)) para ubicar inicio + O(k) paginas contiguas del rango + O(P_aux). Para rangos pequenios (span=500), solo se leen las paginas que contienen el rango. La localidad espacial de las paginas contiguas hace que este sea el metodo mas eficiente para rangos sobre datos ordenados.

**Ventaja clave**: A diferencia del B+ Tree que sigue punteros `next_leaf` (potencialmente dispersos en disco), el Sequential File tiene las paginas main fisicamente contiguas, lo que maximiza la localidad de acceso — 17 accesos vs 341 del B+ Tree para 100K registros con span=500.

#### Algoritmo: Eliminacion (remove)

```
FUNCTION remove(key):
    -- Fase 1: Buscar en main pages (binary search sobre paginas)
    result = find_main_page(key)
    IF result != NULL:
        page_id, entries, next_page = result
        FOR i IN entries WHERE entries[i].key == key:
            IF clustered mode:
                entries[i] = (key, DELETED(entries[i].value))  -- soft delete
                write_data_page(page_id, entries, next_page)
                num_deleted += 1
            ELSE:
                entries.remove(i)              -- eliminacion fisica
                write_data_page(page_id, entries, next_page)
                num_main -= 1
            save_metadata()
            RETURN TRUE

    -- Fase 2: Buscar en aux pages (scan lineal)
    page_id = first_aux
    prev = -1
    WHILE page_id != -1:
        entries, next = read_data_page(page_id)
        FOR i IN entries WHERE entries[i].key == key:
            IF clustered mode:
                entries[i] = (key, DELETED(entries[i].value))
                write_data_page(page_id, entries, next)
                num_deleted += 1
            ELSE:
                entries.remove(i)
                IF entries empty:
                    unlink page from chain (prev.next = next)
                ELSE:
                    write_data_page(page_id, entries, next)
                num_aux -= 1
            save_metadata()
            RETURN TRUE
        prev = page_id
        page_id = next

    RETURN FALSE
```

**Costo**: O(log(P_main)) + O(P_aux) lecturas + O(1) escritura.

**Consideracion de implementacion (modo clustered)**: Se usa **soft delete** (flag byte por slot) para mantener los RIDs estables. Los indices secundarios que apuntan a (page_id, slot) no necesitan actualizarse al eliminar — simplemente ven un flag de borrado al leer el slot. Las entradas eliminadas se compactan durante la proxima reconstruccion.

#### Consideraciones de implementacion

- **Overflow del area aux**: Cuando la ultima pagina aux se llena, se aloca una nueva pagina y se encadena via `next_page`. Se mantiene un **cache `_last_aux`** que evita recorrer toda la linked list en cada insercion (O(1) en vez de O(P_aux) para localizar la ultima pagina).
- **Reconstruccion cuando K registros**: En esta implementación, el umbral `max_aux` corresponde al número máximo de entradas permitidas en el área auxiliar antes de ejecutar una reconstrucción. Para registros de tamaño fijo `S bytes`.
```
entry_size = S+1
max_aux = (PAGE_SIZE-8) // (S+1)
```
Ej. Para un record de S = 175B (ejemplo de la demo) la reconstrucción ocurre aproximadamente cada `max_aux = 23` inserciones.
- **Mantenimiento de punteros**: En modo clustered, la reconstruccion invalida todos los (page_id, slot) de indices secundarios. Se usa un callback `on_reconstruct` para notificar al `DataBase` que reconstruya los indices B+ Tree, Hash y R-Tree que apuntan a la tabla.
- **Página 0 Metadata global**: En la página 0 se guardan valores necesarios para mantener la información necesaria del sequential file:
```
- num_main    : Cantidad total de entradas en el area main
- num_aux     : Cantidad actual de entradas en el area aux 
- head_page   : Número de la primera pagina main
- num_pages   : Total de paginas reservadas en el archivo
- max_aux     : Umbral maximo de entradas permitidas en aux antes de reconstruir
- first_aux   : Numero de la pagina auxiliar (-1 si no existe)
- num_deleted : Cantidad de registros marcados como deleted (soft deleted)
- 
```

#### Diagrama

Por convenciones:
 - **Clustered**: Lo que guarda en cada record del `sequential_file` -> `[index_key, record_info]`
 - **Unclusterd**: Lo que guarda en cada record del `sequential_file` -> `[index_key, (page_id, slot)]`
 Para mostrar un ejemplo de creación, usaremos `[index_key, record_info]` para representar ambos casos.

```
+-------------------------------------------------+
| Pag 0: METADATA                                  |
|  head_page=1, first_aux=3, num_main=8, num_aux=2 |
|  max_aux=4, num_deleted=0                        |
+-------------------------------------------------+
| Pag 1: MAIN (sorted, contigua)    next -> Pag 2  |
|   [1,RI] [3,RI] [5,RI] [7,RI]                    |
+-------------------------------------------------+
| Pag 2: MAIN (sorted, contigua)    next -> -1     |
|   [9,RI] [11,RI] [13,RI] [15,RI]                 |
+-------------------------------------------------+
| Pag 3: AUX (heap input)           next -> -1     |
|   [2,RI] [6,RI]                                  |
+-------------------------------------------------+

  Binary search: clave 11
    mid = pag 1: [1..7] -> 11 > 7 -> lo = 2
    mid = pag 2: [9..15] -> 9 <= 11 <= 15 -> FOUND
    bisect dentro de pag 2 -> slot 1

--- Agregando records con index_key = [6, 8] ---
--- Despues de reconstruct() ---

+-------------------------------------------------+
| Pag 1: MAIN   [1,2,3,5]        next -> Pag 2    |
+-------------------------------------------------+
| Pag 2: MAIN   [6,7,8,9]        next -> -3       |
+-------------------------------------------------+
| Pag 3: MAIN   [11,13,15]       next -> -1       |
+-------------------------------------------------+
Aux: vacio, archivo truncado, paginas contiguas
```

---

### 2.3 Extendible Hashing (`Extendible_Hashing.py`)

#### Descripcion

Tabla hash dinamica con un directorio que se duplica cuando un bucket se desborda. Busqueda por igualdad en O(1) promedio (2 accesos a disco). No soporta busqueda por rango.

#### Estructura en disco

- Archivo unico: `indexes/{tabla}_{columna}.idx`
- **Pagina 0**: metadata + directorio
  ```
  global_depth(4) + num_buckets(4) + num_entries(4) + directory[page_ids]
  ```
- **Paginas 1..N**: buckets
  - Header (8B): `local_depth(4) + count(4)`
  - Entries: `key(K) + RID(8)`
  - Capacidad: `(4096 - 8) / entry_size` = 340 para claves int

#### Algoritmo: Busqueda

```
FUNCTION search(key):
    idx = hash(key) AND ((1 << global_depth) - 1)
    bucket_page = directory[idx]
    entries = read_bucket(bucket_page)          -- 1 lectura
    FOR (k, rid) IN entries:
        IF k == key: RETURN rid
    RETURN NULL
```

**Costo**: 1 lectura de metadata/directorio + 1 lectura de bucket = **2 accesos constantes**.

#### Algoritmo: Insercion con split

```
FUNCTION add(key, value):
    idx = hash(key)
    bucket = read_bucket(directory[idx])
    IF unique AND key in bucket:
        overwrite and RETURN
    IF len(bucket.entries) < capacity:
        append (key, value); write_bucket
    ELSE:
        split_bucket(idx, bucket, key, value)

FUNCTION split_bucket(idx, bucket, key, value):
    add (key, value) to entries
    IF local_depth == global_depth:
        directory = directory + copy(directory)    -- duplicar
        global_depth += 1
    new_local = local_depth + 1
    new_bucket = create empty bucket(new_local)
    -- Redistribuir por bit (new_local - 1)
    FOR each entry:
        IF hash(entry.key) has bit set: move to new_bucket
        ELSE: keep in old bucket
    update directory pointers
```

#### Algoritmo: Eliminacion (remove)

```
FUNCTION remove(key):
    -- Paso 1: Calcular indice del directorio
    idx = hash(key) AND ((1 << global_depth) - 1)
    bucket_page = directory[idx]

    -- Paso 2: Leer bucket
    local_depth, entries = read_bucket(bucket_page)    -- 1 lectura

    -- Paso 3: Buscar y eliminar la entrada
    FOR i IN 0..len(entries):
        IF entries[i].key == key:
            entries.remove(i)                          -- eliminacion fisica
            write_bucket(bucket_page, local_depth, entries) -- 1 escritura
            num_entries -= 1
            save_metadata()                            -- 1 escritura
            RETURN TRUE

    RETURN FALSE                                       -- clave no encontrada
```

**Costo**: 1 lectura de metadata/directorio + 1 lectura de bucket + 1 escritura = **3 accesos constantes**. No se realiza merge de buckets al eliminar (el directorio no se contrae).

#### Funcion hash

```
FUNCTION hash(key):
    IF key is int:
        h = key * 2654435761          -- Knuth multiplicative hash
    IF key is bytes:
        h = polynomial hash (base 31)
    RETURN h AND ((1 << global_depth) - 1)
```

La mascara `(1 << global_depth) - 1` extrae los `global_depth` bits menos significativos del hash, determinando la entrada del directorio.

#### Consideraciones de implementacion

- **Directorio dinamico**: El directorio reside en la pagina 0 del archivo como un arreglo de `page_ids`. Cuando un bucket se desborda y `local_depth == global_depth`, el directorio se **duplica** (de 2^d a 2^(d+1) entradas). Multiples entradas del directorio pueden apuntar al mismo bucket (cuando `local_depth < global_depth`).
- **No soporta rangeSearch**: Al distribuir las claves por hash, se pierde el orden. Una busqueda por rango requeriria escanear **todos** los buckets (O(B)), equivalente a un full scan. Por esta razon, el sistema lanza `NotImplementedError` en `range_search`.
- **Bucket split**: Cuando un bucket supera `bucket_capacity` (340 entries para claves INT), se crea un nuevo bucket con `local_depth + 1` y se redistribuyen las entries segun el bit `local_depth` del hash completo. Si despues del split un bucket sigue lleno (todas las claves colisionan en los mismos bits), se realiza un split recursivo.
- **Capacidad del bucket**: `(4096 - 8) / entry_size`. Para claves INT (4B) + RID (8B) = 12B por entry: 340 entries por bucket. Esto hace que las colisiones sean muy raras en la practica.

#### Diagrama

```mermaid
flowchart TB
    GD[global_depth = 2]

    subgraph DIR [Directory - 4 entries]
        D00["00 -> Bucket A
        local_depth = 2
        [4, 8, 12]"]
        D01["01 -> Bucket B
        local_depth = 2
        [1, 5, 9]"]
        D10["10 -> Bucket C
        local_depth = 2
        [2, 6, 10]"]
        D11["11 -> Bucket D
        local_depth = 2
        [3, 7, 11]"]
    end

    GD --> DIR

    Q["search(key = 5)"] --> H["hash(5) AND 0b11 = 01"]
    H --> D01
    D01 --> F["Scan bucket B and find 5"]

    I["insert key = 16
    (hash = 00)"] --> A["Bucket A full"]
    A --> C{"local_depth == global_depth?"}
    C -- yes --> U["Duplicate directory
    4 -> 8 entries"]
    U --> GD3["global_depth = 3"]
    GD3 --> R["Redistribute entries by bit 2"]
    R --> N["Update directory pointers for Bucket A"]
```

---

### 2.4 R-Tree (`rtree.py`)

#### Descripcion

Indice espacial 2D para puntos (x, y). Cada nodo interno contiene MBRs (Minimum Bounding Rectangles) que envuelven los puntos de sus subarboles. Soporta búsqueda circular (radio) y k-NN (k vecinos mas cercanos). Usa **Quadratic Split** de Guttman para particion de nodos.

#### Estructura en disco

- Archivo único: `indexes/{tabla}_{colX}_{colY}.idx`
- **Pagina 0**: metadata (`root_page`, `num_pages`)
- **Hojas**: entries de 24B = `x(8) + y(8) + page_num(4) + slot(4)`
- **Nodos internos**: entries de 36B = `min_x(8) + min_y(8) + max_x(8) + max_y(8) + child_page(4)`
- Max entries hoja: `(4096 - 5) / 24` = 170
- Max entries interno: `(4096 - 5) / 36` = 113

#### Algoritmo: Insercion con Quadratic Split

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
        new_node = quadratic_split(leaf)
        adjust_tree_with_split(path, leaf, new_node)

FUNCTION quadratic_split(node):
    seed1, seed2 = pick_seeds(entries)        // max wasted area
    group1 = [seed1], group2 = [seed2]
    WHILE remaining not empty:
        pick entry with max |enlargement1 - enlargement2|
        assign to group with less enlargement
    RETURN new_node with group2
```

#### Algoritmo: Busqueda por radio

```
FUNCTION radius_search(cx, cy, radius):
    stack = [root]
    results = []
    WHILE stack not empty:
        node = read_node(stack.pop())
        IF node is leaf:
            FOR entry IN node.entries:
                IF distance(cx, cy, entry.x, entry.y) <= radius:
                    results.append(entry)
        ELSE:
            FOR entry IN node.entries:
                IF mbr_intersects_circle(entry.mbr, cx, cy, radius):
                    stack.push(entry.child)    // poda: solo explora MBRs relevantes
    RETURN results sorted by distance
```

#### Algoritmo: k-NN (k vecinos mas cercanos)

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

#### Consideraciones de implementacion

- **Clave compuesta (longitude, latitude)**: Cada punto se almacena como dos FLOAT (8B cada uno). La columna de tipo `POINT` en la tabla se serializa como `(x, y)` y se indexa en el R-Tree. El indice almacena `x(8) + y(8) + page_num(4) + slot(4) = 24B` por entrada en las hojas.
- **Quadratic Split de Guttman**: Cuando un nodo supera `max_entries` (170 para hojas, 113 para internos), se ejecuta el algoritmo de particion cuadratica:
  1. `pick_seeds`: selecciona las dos entries cuyo MBR combinado desperdicia más area.
  2. Iterativamente asigna cada entry restante al grupo cuyo MBR se agranda menos.
  3. Complejidad: O(n^2) por split, donde n = entries del nodo.
- **Poda por MBR**: Tanto `radius_search` como `knn_search` usan `mbr_intersects_circle` para descartar ramas enteras del arbol sin leerlas. Esto reduce drasticamente los accesos a disco para consultas localizadas.
- **Visualizacion grafica**: Los resultados de consultas espaciales incluyen la distancia al punto de query, permitiendo renderizar circulos de radio y marcar los k vecinos mas cercanos en un mapa.

#### Diagrama

![RTree](docs/img/diagramartree.png)
---

### 2.5 External Sort — TPMMS (`external_sort.py`)

#### Descripcion

Two-Pass Multiway Merge Sort para ordenar tablas que no caben en memoria. Opera en dos fases con I/O por paginas completas. Se activa con la clausula `ORDER BY` del SQL.

#### Algoritmo

```
FUNCTION external_sort(db, sort_column, buffer_size):
    -- FASE 1: Generacion de runs
    B = buffer_size / page_size
    FOR each group of B pages in heap:
        read B pages into memory                -- B lecturas
        sort records by sort_column in RAM
        write sorted run to temp file           -- B escrituras

    -- FASE 2: Multiway merge
    max_streams = B - 1
    WHILE num_runs > max_streams:
        merge groups of max_streams runs
    -- Final merge con min-heap:
        heap = [(key, run_idx, record) for first record of each run]
        WHILE heap not empty:
            pop minimum, write to output
            push next from same run
    RETURN sorted records
```

#### Costo

- Fase 1: `2P` accesos (P lecturas + P escrituras)
- Fase 2: `2P * ceil(log_{B-1}(ceil(P/B)))` accesos
- **Total**: `2P * (1 + ceil(log_{B-1}(ceil(P/B))))` accesos a pagina

---

## 3. Analisis Teorico Comparativo de Accesos a Disco

Sea N = numero de registros, M = orden del arbol/entries por pagina, P = numero de paginas de datos.

### 3.1 Busqueda por igualdad (1 registro)

| Tecnica | Lecturas de pagina | Observacion |
|---|---|---|
| B+ Tree | O(log_M(N)) | Recorre altura del arbol (2-4 niveles) |
| Sequential File | O(log(P_main) + P_aux) | Binary search sobre main pages + scan de aux |
| Extendible Hashing | O(2) | 1 lectura directorio + 1 lectura bucket |
| R-Tree | O(log_M(N)) | Similar a B+ Tree para puntos exactos |
| Full Scan | O(P) | Recorre todas las paginas del heap |

### 3.2 Busqueda por rango

| Tecnica | Lecturas de pagina | Observacion |
|---|---|---|
| B+ Tree | O(log_M(N) + R/M) | log para ubicar inicio + R/M hojas encadenadas |
| Sequential File | O(log(P_main) + k + P_aux) | Binary search inicio + k paginas contiguas + aux |
| Extendible Hashing | No soportado | Requiere full scan O(P) |
| R-Tree | No aplica (espacial) | Usa radio/k-NN en vez de rango 1D |

### 3.3 Insercion

| Tecnica | Lecturas | Escrituras | Observacion |
|---|---|---|---|
| B+ Tree | O(log_M(N)) | O(log_M(N)) | Busqueda + escritura. Split: +2 escrituras |
| Sequential File | O(log(P_main) + P_aux) | O(1) | Chequeo duplicados + append a aux. Reconstruct: O(N) periodico |
| Extendible Hashing | O(2) | O(1-2) | Lee directorio + bucket. Split: escrituras adicionales |
| Heap (sin indice) | O(0) | O(1) | Append al final |

### 3.4 Eliminacion

| Tecnica | Lecturas | Escrituras | Observacion |
|---|---|---|---|
| B+ Tree | O(log_M(N)) | O(log_M(N)) | Busqueda + reescritura. Merge/borrow posible |
| Sequential File | O(log(P_main) + P_aux) | O(1) | Soft delete (marca flag), sin desplazar |
| Extendible Hashing | O(2) | O(2) | Lee directorio + bucket, reescribe ambos |

### 3.5 Tabla resumen

| Operacion | B+ Tree | Sequential File | Ext. Hashing | R-Tree |
|---|---|---|---|---|
| Busqueda = | O(log N) | O(log P + P_aux) | **O(1)** | O(log N) |
| Rango | O(log N + R) | O(log P + k + P_aux) | N/A | N/A (espacial) |
| Insercion | O(log N) | O(1) amortizado* | **O(1)** | O(log N) |
| Eliminacion | O(log N) | O(log P + P_aux) | O(1) | O(log N) |
| Espacio | Moderado | Bajo | Variable | Alto |

(*) La reconstruccion periodica del Sequential File es O(N), pero se amortiza sobre max_aux inserciones.

---

## 4. Parser SQL

### 4.1 Componentes

El parser consta de tres etapas secuenciales:

![flujo-parser](docs/img/fparser.png)

1. **Scanner** (`scanner.py`): analisis lexico — convierte texto en tokens.
2. **Parser** (`parser.py`): analisis sintactico — convierte tokens en AST (Abstract Syntax Tree) usando **descenso recursivo**.
3. **DBVisitor** (`db_visitor.py`): patron Visitor — recorre el AST y ejecuta operaciones contra `DataBase`.

### 4.2 Tokens definidos

```
Keywords:   CREATE, TABLE, SELECT, FROM, WHERE, INSERT, INTO,
            VALUES, DELETE, FILE, ORDER, BY, PRIMARY, KEY
Tipos:      INT, FLOAT, VARCHAR, POINT
Indices:    INDEX, SEQUENTIAL, HASH, BTREE, RTREE
Espacial:   BETWEEN, AND, IN, RADIUS, K
Operadores: =, <, >, <=, >=, !=, -, *, (, ), ,, ;, .
Literales:  ID, NUMBER, STRING_LITERAL
Control:    EOF, ERROR
```

40 palabras reservadas mapeadas via diccionario `KEYWORDS` en `lexer_token.py`.

### 4.3 Gramatica EBNF

```
Program     ::= StmtList
StmtList    ::= Stmt { ";" Stmt }* [ ";" ]
Stmt        ::= CreateStmt | SelectStmt | InsertStmt | DeleteStmt

CreateStmt  ::= CREATE TABLE Id "(" ColDef { "," ColDef }* ")"
                [ FROM FILE Path ]
ColDef      ::= Id Type [ PRIMARY KEY ] [ INDEX IndexTech ]
IndexTech   ::= SEQUENTIAL | HASH | BTREE | RTREE

SelectStmt  ::= SELECT Columns FROM Id [ WHERE Condition ] [ ORDER BY Id ]
Columns     ::= "*" | Id { "," Id }*

InsertStmt  ::= INSERT INTO Id VALUES "(" Value { "," Value }* ")"

DeleteStmt  ::= DELETE FROM Id WHERE Id RelOp Value

Condition   ::= Id RelOp Value
              | Id BETWEEN Value AND Value
              | Id IN "(" SpatialCond ")"
SpatialCond ::= POINT "(" SignedNum "," SignedNum ")" ","
                ( RADIUS Number | K Number )

RelOp       ::= "=" | "<" | ">" | "<=" | ">=" | "!="
Type        ::= INT | FLOAT | VARCHAR [ "(" Number ")" ] | POINT
Value       ::= [ "-" ] Number | String
SignedNum   ::= [ "-" ] Number
```

### 4.4 Automata del Scanner

El scanner implementa un automata finito determinista:

![afd](docs/img/afd.png)

### 4.5 Parser recursivo descendente

El parser implementa una funcion por cada no-terminal de la gramatica. Ejemplo del metodo `parse_select`:

```python
def parse_select(self):
    self.expect(TokenType.SELECT)
    columns = self.parse_columns()
    self.expect(TokenType.FROM)
    table = self.expect(TokenType.ID).text
    condition = None
    if self.match(TokenType.WHERE):
        condition = self.parse_condition()
    order_by = None
    if self.match(TokenType.ORDER):
        self.expect(TokenType.BY)
        order_by = self.expect(TokenType.ID).text
    return SelectStmt(columns, table, condition, order_by)
```

### 4.6 Ejemplos de consultas soportadas

```sql
-- Crear tabla con PRIMARY KEY e indices
CREATE TABLE empleados (
    id INT PRIMARY KEY,
    nombre VARCHAR(50),
    salario FLOAT INDEX HASH,
    ubicacion POINT INDEX RTREE
) FROM FILE 'data.csv';

-- Busqueda por igualdad
SELECT * FROM empleados WHERE id = 100;

-- Busqueda por rango
SELECT nombre, salario FROM empleados WHERE salario BETWEEN 3000 AND 5000;

-- Busqueda espacial por radio
SELECT * FROM empleados WHERE ubicacion IN (POINT(-12.04, -77.02), RADIUS 500);

-- Busqueda k-NN
SELECT * FROM empleados WHERE ubicacion IN (POINT(-12.04, -77.02), K 10);

-- Insercion
INSERT INTO empleados VALUES (101, 'Juan', 4500.0, -12.05, -77.03);

-- Eliminacion
DELETE FROM empleados WHERE id = 101;

-- Ordenamiento
SELECT * FROM empleados ORDER BY salario;
```

Se implementa lógica en `run_all_inputs.py` para testear solo el parser y verificar su correcto funcionamiento. 

---

## 5. Resultados Experimentales

### 5.1 Metodologia

- **Dataset**: `cities.csv` con columnas `id(INT), country_id(INT), latitude(FLOAT), longitude(FLOAT), name(CHAR(40))`.
- **Tamanios**: N = 1,000 / 10,000 / 100,000 registros.
- **Metricas**: accesos a disco (lecturas + escrituras de paginas de 4096B) y tiempo en milisegundos.
- **Consultas**: 200 busquedas puntuales aleatorias y 200 busquedas por rango (span=500).
- **Medicion**: contadores internos `disk_reads` / `disk_writes` de cada estructura.

### 5.2 Insercion masiva

#### Accesos a disco totales

![Insercion: Accesos a disco totales](docs/img/insert_disk_total.png)

| N | B+ Tree | Sequential File | Ext. Hashing |
|---|---|---|---|
| 1,000 | 5,665 | 6,578 | 5,007 |
| 10,000 | 59,735 | 152,687 | 50,091 |
| 100,000 | 618,023 | 8,153,681 | 501,531 |

#### Accesos a disco por registro

![Insercion: Accesos por registro](docs/img/insert_disk_per_record.png)

| N | B+ Tree | Sequential File | Ext. Hashing |
|---|---|---|---|
| 1,000 | 5.67 | 6.58 | **5.01** |
| 10,000 | 5.97 | 15.27 | **5.01** |
| 100,000 | 6.18 | 81.54 | **5.02** |

#### Tiempo total de insercion

![Insercion: Tiempo total](docs/img/insert_time.png)

| N | B+ Tree | Sequential File | Ext. Hashing |
|---|---|---|---|
| 1,000 | 191 ms | 147 ms | 171 ms |
| 10,000 | 2,278 ms | 3,569 ms | 2,103 ms |
| 100,000 | 26,712 ms | 170,667 ms | 23,157 ms |

### 5.3 Busqueda puntual

#### Accesos a disco promedio por consulta

![Busqueda puntual: Accesos a disco](docs/img/search_disk.png)

| N | B+ Tree | Sequential File | Ext. Hashing |
|---|---|---|---|
| 1,000 | 3.00 | 3.17 | **2.00** |
| 10,000 | 3.00 | 6.18 | **2.00** |
| 100,000 | 4.00 | 9.24 | **2.00** |

#### Tiempo promedio por consulta

![Busqueda puntual: Tiempo](docs/img/search_time.png)

| N | B+ Tree | Sequential File | Ext. Hashing |
|---|---|---|---|
| 1,000 | 0.07 ms | 0.06 ms | 0.06 ms |
| 10,000 | 0.08 ms | 0.13 ms | 0.09 ms |
| 100,000 | 0.13 ms | 0.19 ms | **0.05 ms** |

### 5.4 Busqueda por rango (span=500)

#### Accesos a disco promedio por consulta

![Busqueda por rango: Accesos a disco](docs/img/range_disk.png)

| N | B+ Tree | Sequential File | Ext. Hashing |
|---|---|---|---|
| 1,000 | 6.38 | **6.03** | N/A (full scan: 1,065) |
| 10,000 | 37.52 | **9.68** | N/A (full scan: 10,011) |
| 100,000 | 340.73 | **17.28** | N/A (full scan: 100,039) |

#### Tiempo promedio por consulta

![Busqueda por rango: Tiempo](docs/img/range_time.png)

| N | B+ Tree | Sequential File | Ext. Hashing |
|---|---|---|---|
| 1,000 | 0.08 ms | 0.12 ms | N/A |
| 10,000 | 0.28 ms | 0.24 ms | N/A |
| 100,000 | 2.12 ms | **0.58 ms** | N/A |

### 5.5 Discusion de resultados

1. **Extendible Hashing** domina en busqueda puntual: **2 accesos constantes** independiente de N. Su costo por insercion es tambien el mas bajo (~5 paginas/registro). Sin embargo, no soporta rangos — una busqueda por rango requiere full scan (100K accesos para N=100K).

2. **B+ Tree** ofrece el mejor balance general:
   - Busqueda puntual en O(log N): 3-4 accesos para 100K registros.
   - Busqueda por rango eficiente: recorre solo las hojas del rango via `next_leaf`.
   - Insercion estable: ~6 accesos/registro independiente de N.
   - Es la opcion por defecto para primary keys.

3. **Sequential File** tiene un comportamiento interesante:
   - **Ventaja en rangos**: gracias a la localidad espacial de las paginas contiguas (17 accesos vs 341 del B+ Tree para N=100K, span=500). Los datos estan fisicamente ordenados, por lo que un rango requiere leer pocas paginas contiguas.
   - **Desventaja en insercion**: las reconstrucciones periodicas generan un costo cuadratico. Con N=100K, el costo por registro sube a 81.5 accesos (vs 6.2 del B+ Tree).
   - La busqueda binaria sobre paginas contiguas mantiene la busqueda puntual en O(log P): 9.24 accesos para 100K.

4. **Trade-off insercion vs consulta**: El Sequential File sacrifica rendimiento de insercion a cambio de excelente localidad de datos para rangos. En escenarios de carga masiva seguida de consultas (OLAP), esto puede ser ventajoso.

---

## 6. Concurrencia

### 6.1 Protocolo

El sistema implementa **Strict Two-Phase Locking (S2PL)** con bloqueos a nivel de pagina:

- **SHARED (S)**: multiples transacciones pueden leer la misma pagina simultaneamente.
- **EXCLUSIVE (X)**: una sola transaccion puede escribir, sin lectores concurrentes.
- **Upgrade S -> X**: permitido solo si la TX es el unico holder del lock.
- **Liberacion**: los locks se liberan unicamente en `COMMIT` o `ABORT` (strict 2PL garantiza serializabilidad).

### 6.2 Deteccion de deadlocks

Se usa un **grafo wait-for** con deteccion de ciclos via BFS:

```mermaid
sequenceDiagram
    participant TX1
    participant DB as Recurso (Page 0 & 1)
    participant TX2

    Note over TX1, TX2: Paso 1: Adquisición inicial de Locks
    TX1->>DB: X-lock en Page 0 (Concedido)
    TX2->>DB: X-lock en Page 1 (Concedido)

    Note over TX1, TX2: Paso 2: Peticiones cruzadas (Bloqueo)
    TX1->>DB: Solicita X-lock en Page 1
    DB-->>TX1: Esperando a TX2...
    
    TX2->>DB: Solicita X-lock en Page 0
    DB-->>TX2: Esperando a TX1...

    Note over TX1, TX2: ¡DEADLOCK DETECTADO!

    Note over TX1, TX2: Paso 3: Resolución (TX2 elegida como víctima)
    TX2->>TX2: DeadlockError & ABORT
    TX2->>DB: Libera X-lock en Page 1
    DB-->>TX1: X-lock en Page 1 (Concedido)
    Note over TX1: TX1 continúa
```

```mermaid
graph LR
    subgraph Wait_For_Graph [Grafo de Espera]
        T1((TX1))
        T2((TX2))

        T1 -- "espera lock en Page 1" --> T2
        T2 -- "espera lock en Page 0" --> T1
    end

    style T1 fill:#f9f,stroke:#333
    style T2 fill:#fff,stroke:#f66,stroke-dasharray: 5 5
    
    linkStyle 0,1 stroke:#ff0000,stroke-width:2px;
```

### 6.3 Reporte de conflictos

El sistema genera un reporte persistido en `logs/concurrency_report.txt` que incluye:
- Protocolo utilizado y parametros
- Timeline completo de operaciones por transaccion
- Locks adquiridos por pagina (con deteccion de contention)
- Conflictos R-W y W-W detectados
- Deadlocks y aborts con timestamps

---

## 7. Interfaz Grafica

### 7.1 API REST

El sistema expone una API REST via FastAPI (`main.py`):

- `POST /query`: ejecuta una consulta SQL y retorna resultados con metricas.
- `POST /csv/data`: carga archivos CSV para poblar tablas.
- Documentacion interactiva en `http://localhost:8000/docs` (Swagger UI).

### 7.2 Pantalla principal

- Campo de texto para ingresar consultas SQL.
- Boton de ejecucion.
- Area de resultados en formato tabla.

### 7.3 Visualizacion de metricas

Cada operacion reporta:
- Tiempo de ejecucion (ms)
- Lecturas de disco (heap + indices)
- Escrituras de disco (heap + indices)
- Total de accesos I/O

### 7.4 Consultas espaciales

- Soporte para busqueda por radio y k-NN sobre columnas POINT.
- Los resultados incluyen distancia al punto de query.

---

## 8. Conclusiones

1. **No existe una estructura universalmente superior**: la eleccion depende del patron de consultas. Extendible Hashing domina en igualdad (O(1)), B+ Tree ofrece el mejor balance (igualdad + rangos), y Sequential File tiene la mejor localidad para rangos sobre datos ordenados.

2. **La paginacion uniforme de 4096 bytes** en todas las estructuras permite comparaciones justas de I/O y refleja el comportamiento real de un DBMS. Los contadores de `disk_reads` / `disk_writes` miden el costo real independiente del tiempo de CPU.

3. **El Sequential File muestra un trade-off claro**: excelente rendimiento en rangos (17 accesos vs 341 del B+ Tree para 100K registros) a costa de inserciones mas lentas por las reconstrucciones. La busqueda binaria sobre paginas contiguas lo hace competitivo en busquedas puntuales (9 accesos para 100K).

4. **El parser SQL** cubre operaciones DDL y DML con extensiones para consultas espaciales y ordenamiento externo (TPMMS). La arquitectura Scanner -> Parser -> AST -> Visitor permite separar claramente el analisis de la ejecucion.

5. **Strict 2PL con deteccion de deadlocks** garantiza serializabilidad de transacciones concurrentes a nivel de pagina, con reportes persistidos para analisis post-mortem.
