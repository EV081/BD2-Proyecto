# Guía de Implementación: B+ Tree y Concurrencia

Hola Elmer, aquí tienes los detalles de lo que debes implementar según los requisitos del proyecto.

## 1. B+ Tree sobre Memoria Secundaria

El objetivo es implementar un índice **B+ Tree** donde cada nodo represente una **página de tamaño fijo** (por ejemplo, 4KB) en el disco.

### Requisitos Específicos:
- **Páginas de tamaño fijo:** Los nodos (tanto internos como hojas) deben almacenarse en páginas. No puedes cargar todo el árbol en memoria.
- **Estructura del Nodo:**
    - **Nodos Internos:** Almacenan claves y punteros (IDs de página) a otros nodos.
    - **Nodos Hoja:** Almacenan claves y punteros (u offsets) a los registros reales, además de un puntero a la siguiente hoja (para `rangeSearch`).
- **Operaciones:**
    - `add(key, value)`: Inserción con división de nodos (split) cuando se llenan.
    - `search(key)`: Búsqueda exacta bajando desde la raíz.
    - `rangeSearch(begin_key, end_key)`: Buscar la primera hoja y recorrer las hojas enlazadas.
    - `remove(key)`: Eliminación con fusión (merge) o redistribución de nodos cuando quedan por debajo del 50% de ocupación.

---

## 2. Simulador de Acceso Concurrente

Debes crear un entorno que permita simular que **múltiples transacciones** acceden al índice al mismo tiempo.

### Componentes:
- **Transacciones:** Clase o hilos que realicen operaciones (Insert, Select) simultáneamente.
- **Log de Operaciones:** Un archivo o registro en consola que muestre el orden exacto de ejecución.
    - Ejemplo: `[TX1] Iniciando búsqueda de clave 10... [TX2] Insertando clave 15... [TX1] Página 5 leída.`
- **Opcional (+2 puntos):** Implementar bloqueos (**Locks**).
    - **Shared Lock (S):** Para lecturas. Varios pueden leer al mismo tiempo.
    - **Exclusive Lock (X):** Para escrituras. Solo uno puede escribir y nadie más puede leer mientras tanto.

---

## 3. Explicación de Concurrencia en SGBD

La **concurrencia** es la capacidad de un Sistema Gestor de Bases de Datos (SGBD) para permitir que varios usuarios o procesos realicen operaciones sobre los mismos datos **al mismo tiempo**, sin que la base de datos se vuelva inconsistente.

### ¿Por qué es necesaria?
En la vida real, miles de personas usan una base de datos a la vez (ej. un banco o una red social). Si solo permitiéramos una operación por segundo, el sistema sería lentísimo.

### Problemas comunes (Conflictos):
1.  **Lectura Sucia (Dirty Read):** Leer datos que otra transacción modificó pero aún no ha confirmado (commit).
2.  **Lectura No Repetible:** Leer un dato dos veces y obtener valores distintos porque alguien lo cambió en el medio.
3.  **Escritura Perdida:** Dos personas intentan actualizar el mismo dato y una sobreescribe a la otra.

### ¿Cómo se resuelve?
Se usan **Protocolos de Control de Concurrencia**. El más común es el **2PL (Two-Phase Locking)**:
- **Fase de Crecimiento:** La transacción solicita todos los bloqueos que necesita (Shared para leer, Exclusive para escribir).
- **Fase de Liberación:** Una vez que termina de operar, libera los bloqueos.

**En tu simulador:**
Deberías mostrar cómo dos "transacciones" intentan leer/escribir. Si implementas los bloqueos, verás que una transacción debe "esperar" si otra tiene un bloqueo exclusivo (X) sobre la misma página.
