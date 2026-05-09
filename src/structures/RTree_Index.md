# R-Tree: Indice Espacial 2D

## Que es un R-Tree

Un R-Tree es una estructura de datos de arbol balanceado diseñada para indexar datos espaciales multidimensionales. Agrupa objetos cercanos en **Minimum Bounding Rectangles (MBR)** jerarquicos, permitiendo descartar regiones completas del espacio durante las busquedas.

### Propiedades fundamentales

- Todas las hojas estan al **mismo nivel** de altura (arbol balanceado).
- Cada nodo contiene entre `ceil(M/2)` y `M` entradas (excepto la raiz que puede tener minimo 2).
- Los nodos hoja almacenan **puntos (x, y)** y sus **RIDs** (punteros al registro en el heap).
- Los nodos internos almacenan **MBRs** que encierran todos los puntos de su subarbol.
- La insercion minimiza el **area de enlargement** de los MBRs.

---

## Tipo de Indice: Unclustered sobre puntos 2D

### Arquitectura

```
 R-Tree Index                          Heap File (datos desordenados)
┌─────────────────────────────┐     ┌──────────────────────────────────┐
│  [Raiz: MBR Global]        │     │ Pag 0: rec_a  rec_f  rec_c      │
│     /          \            │     │ Pag 1: rec_b  rec_g  [vacio]    │
│  [MBR_izq]   [MBR_der]     │     │ Pag 2: rec_d  rec_e  rec_h      │
│    /   \       /   \        │     │                                  │
│ Hoja1 Hoja2  Hoja3 Hoja4   │     │ Cada RID = (pagina, slot)        │
│ (x,y)→RID   (x,y)→RID  ───┼────►│                                  │
└─────────────────────────────┘     └──────────────────────────────────┘
```

- El indice almacena puntos `(latitud, longitud)` con punteros RID al heap.
- El heap file (PageManager) almacena los registros completos.
- Es un indice **no agrupado**: permite multiples indices espaciales sobre la misma tabla.

---

## Layout de Pagina en Disco

Cada nodo del arbol ocupa una pagina (4096 bytes por defecto).

### Pagina 0: Metadata

```
[root_page (4B)] [num_pages (4B)]
```

### Header (5 bytes)

```
| is_leaf (1B) | num_entries (4B) |
```

### Nodo Hoja (24 bytes por entrada)

```
[HEADER 5B] [x₁(8B) y₁(8B) page(4B) slot(4B)] [x₂ y₂ page slot] ...
             ←──────── entrada 1 ──────────────→  ←── entrada 2 ──→
```

- Cada entrada: punto `(x, y)` como doubles + RID `(page_num, slot)` como ints
- Max entries por hoja: `(4096 - 5) / 24 = 170`

### Nodo Interno (36 bytes por entrada)

```
[HEADER 5B] [min_x(8B) min_y(8B) max_x(8B) max_y(8B) child(4B)] ...
             ←──────────── MBR + puntero a hijo ──────────────→
```

- Cada entrada: MBR `(min_x, min_y, max_x, max_y)` como doubles + child_page como int
- Max entries por nodo interno: `(4096 - 5) / 36 = 113`

---

## Algoritmos

### 1. Busqueda Exacta — `search(x, y)`

```
SEARCH(x, y):
    1. Si el arbol esta vacio, retornar None.
    2. stack ← [raiz]
    3. Mientras stack no este vacio:
        a. nodo ← leer nodo del stack.
        b. Si nodo es hoja:
            - Buscar entrada donde (e.x == x AND e.y == y).
            - Si se encuentra, retornar RID.
        c. Si nodo es interno:
            - Para cada entrada cuyo MBR contenga (x, y):
                - Agregar child al stack.
    4. Retornar None.
```

**Costo**: `O(h)` a `O(h * fanout)` en el peor caso, donde `h` es la altura.

### 2. Busqueda Circular — `radius_search(cx, cy, radius)`

```
RADIUS_SEARCH(cx, cy, radius):
    1. stack ← [raiz]
    2. resultados ← []
    3. Mientras stack no este vacio:
        a. nodo ← leer nodo del stack.
        b. Si nodo es hoja:
            - Para cada punto (x, y):
                - Si distance(cx, cy, x, y) <= radius:
                    - Agregar (x, y, RID, distancia) a resultados.
        c. Si nodo es interno:
            - Para cada entrada:
                - Si MBR intersecta el circulo (cx, cy, radius):
                    - Agregar child al stack.
    4. Ordenar resultados por distancia.
    5. Aplicar offset/limit (paginacion).
    6. Retornar resultados.
```

**Interseccion MBR-Circulo**: Se calcula el punto mas cercano del MBR al centro del circulo. Si la distancia es <= radio, hay interseccion.

```
MBR_INTERSECTS_CIRCLE(mbr, cx, cy, radius):
    closest_x = clamp(cx, mbr.min_x, mbr.max_x)
    closest_y = clamp(cy, mbr.min_y, mbr.max_y)
    return distance(cx, cy, closest_x, closest_y) <= radius
```

### 3. k-NN — `knn_search(qx, qy, k)`

Usa un **min-heap** (priority queue) para explorar nodos en orden de distancia minima.

```
KNN_SEARCH(qx, qy, k):
    1. heap ← [(0.0, "node", raiz)]     // min-heap por distancia
    2. resultados ← []
    3. total_needed ← k + offset

    4. Mientras heap no vacio AND |resultados| < total_needed:
        a. (dist, tipo, data) ← heappop(heap)
        b. Si tipo == "point":
            - Agregar (x, y, RID, dist) a resultados.
        c. Si tipo == "node":
            - nodo ← leer nodo(data)
            - Si nodo es hoja:
                - Para cada punto (x, y):
                    - d ← distance(qx, qy, x, y)
                    - heappush(heap, (d, "point", (x, y, RID)))
            - Si nodo es interno:
                - Para cada entrada:
                    - d ← min_dist(MBR, qx, qy)
                    - heappush(heap, (d, "node", child))

    5. Aplicar offset (saltar primeros `offset` resultados).
    6. Retornar resultados.
```

**Por que funciona**: El min-heap garantiza que siempre procesamos el elemento mas cercano primero. Si un nodo interno tiene `min_dist = 10` pero ya encontramos un punto a distancia 5, el punto sale primero del heap. Esto es el algoritmo de **best-first search**.

**Distancia minima punto-MBR**:
```
MIN_DIST(mbr, x, y):
    dx = max(mbr.min_x - x, 0, x - mbr.max_x)
    dy = max(mbr.min_y - y, 0, y - mbr.max_y)
    return sqrt(dx² + dy²)
```

### 4. Insercion — `add(x, y, rid)`

```
ADD(x, y, rid):
    1. Si el arbol esta vacio:
        a. Crear hoja con la entrada (x, y, rid).
        b. Establecerla como raiz. FIN.

    2. CHOOSE_LEAF(point_mbr):
        a. Desde la raiz, en cada nivel elegir el hijo cuyo MBR
           requiera menor enlargement para incluir el punto.
        b. Desempate por menor area existente.
        c. Guardar path = [(nodo_padre, indice_hijo), ...].

    3. Insertar entrada en la hoja encontrada.

    4. Si la hoja tiene <= max_entries:
        a. Escribir hoja. Ajustar MBRs hacia arriba. FIN.

    5. Si la hoja desborda (> max_entries):
        a. SPLIT_NODE (Quadratic Split):
            - PICK_SEEDS: Encontrar par de entradas con mayor
              "desperdicio de area" si estuvieran juntas.
            - Asignar cada entrada restante al grupo que requiera
              menor enlargement (PICK_NEXT).
            - Garantizar minimo ceil(M/2) entradas por grupo.
        b. Escribir ambos nodos.
        c. Propagar split hacia arriba (INSERT_INTO_PARENT).
        d. Si la raiz se splitea, crear nueva raiz.
```

### 5. Eliminacion — `remove(x, y, rid)`

```
REMOVE(x, y, rid):
    1. SEARCH_WITH_PATH: Encontrar la hoja que contiene (x, y, rid),
       guardando el camino desde la raiz.

    2. Remover la entrada de la hoja.

    3. CONDENSE_TREE: Caminar desde la hoja hacia la raiz:
        a. Si un nodo queda vacio: removerlo del padre.
        b. Si un nodo tiene underflow (< min_entries):
            - Recolectar todas las entradas hoja del subarbol.
            - Remover el nodo del padre.
        c. Si no hay underflow: actualizar MBR del padre.

    4. Si la raiz tiene un solo hijo: hacer ese hijo la nueva raiz.

    5. Reinsertar todas las entradas huerfanas (de nodos con underflow).
```

**Nota**: La estrategia de reinsercion es la propuesta original de Guttman. Permite que los datos se redistribuyan naturalmente en el arbol.

---

## Complejidad

Sea:
- `N` = numero total de puntos indexados
- `M` = max entries por nodo
- `h` = altura del arbol = `ceil(log_M(N))`

| Operacion | Costo promedio (accesos a disco) |
|---|---|
| **Busqueda exacta** | `O(h)` |
| **Busqueda circular** | `O(h + nodos_que_intersectan)` |
| **k-NN** | `O(h + k * log(nodos_visitados))` |
| **Insercion** | `O(h)` (sin split) a `O(h²)` (con splits en cascada) |
| **Eliminacion** | `O(h + reinserciones)` |

### Ejemplo con numeros reales

Con `page_size = 4096`:
- Leaf entries: `170 por hoja` (24 bytes/entrada)
- Internal entries: `113 por nodo` (36 bytes/entrada)
- Para **1 millon de puntos**: `h = log_113(1,000,000) ≈ 2.9` → **3 niveles**
- k-NN con k=10: ~**4-6 accesos a disco**

---

## Quadratic Split

El algoritmo de split cuadratico (Guttman, 1984) divide un nodo desbordado en dos:

1. **Pick Seeds**: Encontrar las 2 entradas que, juntas, generan el mayor MBR desperdiciado:
   ```
   waste(i, j) = area(MBR_union(i, j)) - area(MBR_i) - area(MBR_j)
   ```

2. **Pick Next**: Para cada entrada restante, calcular la diferencia de enlargement entre los dos grupos. Asignar la entrada con mayor diferencia al grupo que la prefiere.

3. **Balance**: Si un grupo necesita todas las entradas restantes para cumplir el minimo (`ceil(M/2)`), asignarlas directamente.

**Complejidad del split**: `O(M²)` por las comparaciones de pick seeds.

---

## Soporte para Puntos Duplicados

El R-Tree permite multiples entradas con las mismas coordenadas pero diferentes RIDs:

```python
idx = RTree("spatial.idx")
idx.add(5.0, 5.0, (0, 0))   # punto (5,5) → RID (0,0)
idx.add(5.0, 5.0, (0, 1))   # punto (5,5) → RID (0,1) (coexisten)

idx.search_all(5.0, 5.0)     # retorna ambos
idx.remove(5.0, 5.0, rid=(0, 0))  # elimina solo el primero
```

---

## Respuesta JSON para Frontend

Las busquedas espaciales retornan JSON con puntos coloreados para visualizacion:

```json
{
    "query_point": {
        "x": -12.04,
        "y": -77.03,
        "color": "red"
    },
    "results": [
        {
            "x": -12.04,
            "y": -77.03,
            "rid": {"page": 0, "slot": 0},
            "distance": 0.0,
            "color": "blue"
        },
        {
            "x": -0.18,
            "y": -78.47,
            "rid": {"page": 0, "slot": 4},
            "distance": 11.93,
            "color": "blue"
        }
    ],
    "total": 2
}
```

- **Rojo**: punto de query (centro de busqueda)
- **Azul**: puntos resultado

---

## Integracion con el Sistema

```
                    ┌─────────────────┐
  SQL Query ──────► │   DB Engine      │
                    │  (dbengine.py)   │
                    └───┬──────┬──┬───┘
                        │      │  │
             ┌──────────▼─┐ ┌─▼──▼────────┐
             │  B+ Tree    │ │  R-Tree      │
             │  (1D keys)  │ │  (2D points) │
             │ (bplus.py)  │ │ (rtree.py)   │
             └─────┬───────┘ └──────┬───────┘
                   │                │
             ┌─────▼───────┐       │
             │ indexes/     │◄──────┘
             │ *.idx files  │
             └──────────────┘
                                ┌──────────────┐
                                │ PageManager   │
                                │ (Heap File)   │
                                └──────┬───────┘
                                       │
                                ┌──────▼───────┐
                                │ data/         │
                                │ tabla.bin     │
                                └──────────────┘
```

### Uso desde dbengine

```python
db = DataBase("ciudades", schema={
    "id": "int", "lat": "float", "lon": "float", "nombre": "char(20)"
})

# Crear indice espacial
db.create_index(("lat", "lon"), index_type="rtree")

# Insertar
db.insert({"id": 1, "lat": -12.04, "lon": -77.03, "nombre": "Lima"})

# k-NN: 5 ciudades mas cercanas
registros = db.select_knn("lat", "lon", -12.04, -77.03, k=5)

# Busqueda circular: ciudades dentro de radio 10
registros = db.select_radius("lat", "lon", -12.04, -77.03, radius=10.0)

# JSON para frontend
json_data = db.select_knn_json("lat", "lon", -12.04, -77.03, k=5)
```

### Operaciones

1. **INSERT**: Insertar registro en heap → obtener RID → insertar `(lat, lon, RID)` en R-Tree.
2. **k-NN**: Buscar en R-Tree con min-heap → obtener RIDs → leer registros del heap.
3. **RADIUS**: Buscar en R-Tree con filtro circular → obtener RIDs → leer registros del heap.
4. **DELETE**: Buscar RID (via B+Tree u otro indice) → eliminar del heap → eliminar `(lat, lon, RID)` del R-Tree.
