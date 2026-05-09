# B+ Tree: Indice No Agrupado (Unclustered)

## Que es un B+ Tree

Un B+ Tree es una estructura de datos de arbol auto-balanceada optimizada para operaciones de E/S en disco. Agrupa multiples claves en cada nodo (pagina) para reducir la altura del arbol y minimizar los accesos a disco.

### Propiedades fundamentales

- Todas las hojas estan al **mismo nivel** de altura.
- Los nodos hoja almacenan los datos (pares clave-RID) y estan **enlazados como lista enlazada**.
- Los nodos internos solo contienen claves de direccion y punteros a hijos (**indice disperso**).
- Cada nodo debe estar al menos **medio lleno**: `ceil(max_keys / 2)` entradas minimas.
- Solo las hojas apuntan a los registros reales en el archivo de datos.

---

## Tipo de Indice: Unclustered (No Agrupado)

### Arquitectura

```
 Indice B+Tree (non-clustered)           Heap File (datos desordenados)
┌──────────────────────────┐          ┌────────────────────────────────┐
│    [Nodos Internos]      │          │ Pag 0: rec_a  rec_f  rec_c    │
│      (directorio)        │          │ Pag 1: rec_b  rec_g  [vacio]  │
├──────────────────────────┤          │ Pag 2: rec_d  rec_e  rec_h    │
│ Hoja: key=5  → (0,0)  ──┼─────────►│                                │
│       key=10 → (2,1)  ──┼─────────►│  Los registros NO estan        │
│       key=15 → (1,0)  ──┼─────────►│  ordenados por la clave.       │
│       key=20 → (0,2)  ──┼─────────►│  Cada RID = (pagina, slot)     │
└──────────────────────────┘          └────────────────────────────────┘
```

- **El indice** es una estructura separada que almacena `(clave → RID)`.
- **El heap file** (PageManager) almacena los registros en orden de insercion.
- Los RIDs `(page_num, slot)` son punteros al registro fisico en el heap.

### Por que Unclustered y no Clustered

| Aspecto | Clustered | Unclustered (elegido) |
|---|---|---|
| Indices por tabla | Maximo **1** | **Multiples** |
| Datos | Ordenados fisicamente por la clave | Desordenados (heap) |
| Range scan | Lectura secuencial (optimo) | Random I/O (mitigable) |
| Insercion | Puede causar page splits en el heap | Solo afecta al indice |
| Arquitectura | Indice y datos mezclados | Separacion limpia |
| Flexibilidad | Una sola columna indexada | N columnas indexables |

**Razon principal**: permite crear multiples indices sobre diferentes columnas de la misma tabla, manteniendo una separacion limpia entre el indice y los datos.

---

## Layout de Pagina en Disco

Cada nodo del arbol ocupa exactamente una pagina (4096 bytes por defecto).

### Header (9 bytes)

```
| is_leaf (1B) | num_keys (4B) | next_leaf (4B) |
```

- `is_leaf`: 1 si es hoja, 0 si es interno.
- `num_keys`: cantidad de claves almacenadas.
- `next_leaf`: page_id de la siguiente hoja (-1 si no hay). Solo relevante para hojas.

### Nodo Hoja

```
[HEADER 9B] [key_1][key_2]...[key_n]  [RID_1][RID_2]...[RID_n]
             ←── area de claves ──→    ←── area de valores ──→
```

Cada RID tiene 8 bytes: `(page_num: int, slot: int)`.

### Nodo Interno

```
[HEADER 9B] [key_1][key_2]...[key_n]  [child_0][child_1]...[child_n]
             ←── area de claves ──→    ←── area de punteros a hijos ──→
```

Cada child es un page_id de 4 bytes. Un nodo con `n` claves tiene `n+1` hijos.

### Pagina 0: Metadata

```
[root_page (4B)] [num_pages (4B)]
```

---

## Algoritmos

### 1. Busqueda Exacta — `search(key)`

```
SEARCH(key):
    1. Si el arbol esta vacio (root == -1), retornar None.
    2. nodo ← leer nodo raiz desde disco.
    3. Mientras nodo NO sea hoja:
        a. Encontrar i tal que key < nodo.keys[i] (o i = num_keys).
        b. nodo ← leer nodo hijo nodo.children[i].
    4. En la hoja, buscar key en nodo.keys[].
    5. Si se encuentra en posicion i, retornar nodo.values[i] (el RID).
    6. Si no se encuentra, retornar None.
```

**Costo**: `O(h)` accesos a disco, donde `h = log_{ceil(R/2)}(M)` es la altura del arbol.

### 2. Busqueda por Rango — `range_search(begin, end)`

```
RANGE_SEARCH(begin, end):
    1. Usar SEARCH para encontrar la hoja que contiene begin.
    2. resultados ← []
    3. Desde esa hoja, recorrer las claves:
        a. Para cada clave k en la hoja:
            - Si k > end: retornar resultados.
            - Si k >= begin: agregar RID a resultados.
        b. Si hoja.next_leaf != -1:
            - hoja ← leer siguiente hoja (next_leaf).
            - Repetir paso 3a.
        c. Si no hay mas hojas, retornar resultados.
```

**Costo**: `O(h + hojas_del_rango)` accesos a disco. Aprovecha la **lista enlazada de hojas** para recorrer secuencialmente sin volver a los nodos internos.

### 3. Busqueda Exacta (Non-unique) — `search_all(key)`

```
SEARCH_ALL(key):
    1. Encontrar la hoja que contiene key (mismo que SEARCH).
    2. resultados ← []
    3. Recorrer hojas consecutivas:
        a. Para cada clave k en la hoja:
            - Si k == key: agregar RID a resultados.
            - Si k > key: retornar resultados.
        b. Avanzar a la siguiente hoja via next_leaf.
    4. Retornar resultados.
```

Util para indices no-unicos donde multiples registros comparten la misma clave.

### 4. Insercion — `add(key, value)`

```
ADD(key, value):
    1. Si el arbol esta vacio:
        a. Crear una hoja con la entrada (key, RID).
        b. Establecerla como raiz. FIN.

    2. Encontrar la hoja L donde deberia ir key (_find_leaf).
       Guardar el camino path = [(nodo_padre, indice_hijo), ...].

    3. Si key ya existe en L y el indice es unico:
        a. Sobreescribir el RID existente. FIN.

    4. Insertar (key, RID) en L en posicion ordenada.

    5. Si L tiene <= max_keys entradas:
        a. Escribir L a disco. FIN.

    6. Si L desborda (> max_keys):
        a. SPLIT_LEAF(L):
            - mid ← len(keys) // 2
            - Crear nueva hoja R con keys[mid:] y values[mid:].
            - L se queda con keys[:mid] y values[:mid].
            - R.next_leaf ← L.next_leaf; L.next_leaf ← R.
            - Escribir L y R a disco.
            - COPY-UP: insertar R.keys[0] en el padre.

    7. INSERT_INTO_PARENT(left, key_sep, right, path):
        a. Si no hay padre (path vacio):
            - Crear nueva raiz con [left, key_sep, right].
        b. Si el padre tiene espacio:
            - Insertar key_sep y puntero a right.
        c. Si el padre desborda:
            - SPLIT_INTERNAL(padre):
                - mid ← len(keys) // 2
                - PUSH-UP: keys[mid] sube al abuelo.
                - Crear nuevo nodo derecho con keys[mid+1:].
                - Repetir INSERT_INTO_PARENT (cascada).
```

**Diferencia clave entre split de hoja e interno**:
- **Hoja**: la clave se **copia** al padre (copy-up). La clave sigue existiendo en la hoja derecha.
- **Interno**: la clave se **sube** al padre (push-up). La clave desaparece del nodo original.

### 5. Eliminacion — `remove(key)`

```
REMOVE(key, value=None):
    1. Si el arbol esta vacio, retornar False.

    2. Encontrar la hoja L que contiene key (_find_leaf).

    3. Buscar key en L (opcionalmente matchear RID especifico).
       Si no se encuentra, retornar False.

    4. Remover la entrada (key, RID) de L.

    5. Si L es la raiz:
        a. Si L quedo vacia, root ← -1.
        b. Escribir L. FIN.

    6. Si L tiene >= min_keys entradas:
        a. Escribir L. FIN.

    7. Si L tiene < min_keys (UNDERFLOW):
        a. Intentar REDISTRIBUIR desde hermano izquierdo:
            - Si hermano_izq tiene > min_keys:
                - Mover ultima clave del hermano a L.
                - Actualizar separador en padre.
                - FIN.

        b. Intentar REDISTRIBUIR desde hermano derecho:
            - Si hermano_der tiene > min_keys:
                - Mover primera clave del hermano a L.
                - Actualizar separador en padre.
                - FIN.

        c. FUSIONAR (MERGE) con un hermano:
            - Combinar L + hermano en un solo nodo.
            - Actualizar enlace next_leaf.
            - Remover separador del padre.
            - Si el padre tiene underflow, repetir (cascada hacia arriba).
```

---

## Complejidad

Sea:
- `M` = numero total de claves en el indice
- `R` = max_keys (factor de ramificacion)
- `D` = costo promedio de una operacion de I/O a disco
- `h` = altura del arbol = `ceil(log_{R/2}(M))`

| Operacion | Costo (accesos a disco) |
|---|---|
| **Scan completo** | `O(M/R)` (todas las hojas) |
| **Busqueda exacta** | `O(D * h)` = `O(D * log_{R/2}(M))` |
| **Busqueda por rango** | `O(D * h + hojas del rango)` |
| **Insercion** | `O(D * h + splits en cascada)` |
| **Eliminacion** | `O(D * h + merges en cascada)` |

### Ejemplo con numeros reales

Con `page_size = 4096`, `key_size = 4` (int), `val_size = 8` (RID):
- `max_keys = (4096 - 9) / (4 + 8) = 340` entradas por hoja
- Para **1 millon de registros**: `h = log_{170}(1,000,000) ≈ 2.7` → **3 niveles**
- Busqueda exacta: **3 accesos a disco**

---

## Soporte para Claves Duplicadas (Indice Non-Unique)

Cuando `unique=False`, el arbol permite multiples entradas con la misma clave, cada una apuntando a un RID diferente. Esto es necesario para indexar columnas no-unicas (ej: `edad`, `departamento`).

```python
# Indice unico (default): una entrada por clave
idx_pk = BPlusTree("idx_id.bin", unique=True)
idx_pk.add(100, (0, 0))   # key=100 → RID (0,0)
idx_pk.add(100, (1, 2))   # sobreescribe: key=100 → RID (1,2)

# Indice no-unico: multiples entradas por clave
idx_edad = BPlusTree("idx_edad.bin", unique=False)
idx_edad.add(25, (0, 0))  # edad=25 → RID (0,0)
idx_edad.add(25, (1, 2))  # edad=25 → RID (1,2) (ambas coexisten)
idx_edad.search_all(25)    # retorna [(0,0), (1,2)]
```

Para eliminar una entrada especifica en un indice no-unico, se pasa el RID:
```python
idx_edad.remove(25, value=(1, 2))  # elimina solo la entrada con RID (1,2)
```

---

## Integracion con el Sistema

```
                    ┌─────────────────┐
  SQL Query ──────► │   DB Engine      │
                    │  (dbengine.py)   │
                    └────┬────────┬───┘
                         │        │
              ┌──────────▼──┐  ┌──▼──────────┐
              │  B+ Tree     │  │ PageManager  │
              │  Index       │  │ (Heap File)  │
              │ (bplus.py)   │  │              │
              └──────┬───────┘  └──────┬───────┘
                     │                 │
              ┌──────▼───────┐  ┌──────▼───────┐
              │ idx_tabla.bin │  │ tabla.bin     │
              │ (archivo de  │  │ (archivo de   │
              │  indice)     │  │  datos/heap)  │
              └──────────────┘  └──────────────┘
```

1. **INSERT**: Insertar registro en heap (`PageManager.add_record`) → obtener RID → insertar `(key, RID)` en B+ Tree.
2. **SELECT by key**: Buscar en B+ Tree → obtener RID → leer registro del heap (`PageManager.read_record`).
3. **DELETE**: Buscar en B+ Tree → obtener RID → eliminar del heap y del indice.
4. **RANGE SELECT**: Range search en B+ Tree → obtener lista de RIDs → leer registros del heap.
