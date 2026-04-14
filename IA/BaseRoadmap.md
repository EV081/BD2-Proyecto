# 🚀 ROADMAP DEL PROYECTO (DB2 - Mini SGBD)

## 🧠 VISIÓN GENERAL DEL PROYECTO

Van a construir un sistema que incluye:

* Motor de almacenamiento (archivos + páginas)
* Índices: Sequential, Extendible Hashing, B+ Tree, R-Tree
* Parser SQL
* Simulador de concurrencia
* Frontend (UI)
* Evaluación experimental

👉 Esto **NO es lineal**, se trabaja en paralelo por fases.

---

# 🧩 FASE 0: ORGANIZACIÓN Y SETUP (Día 1–2)

## 🎯 Objetivo:

Tener base técnica y organización clara

## 📌 Tareas

* Crear repo GitHub
* Definir estructura del proyecto
* Setup entorno Python
* Docker base
* Definir dataset (Kaggle)

## 👥 Distribución

* **Elmer** → Setup backend base + estructura carpetas
* **Joseph** → Docker + entorno reproducible
* **Paulo** → Dataset + limpieza CSV
* **Jossue** → Investigación índices (resumen técnico)
* **Juanca** → Diseño general arquitectura (diagrama)

---

# 🧱 FASE 1: CAPA DE ALMACENAMIENTO (CRÍTICA)

## 🎯 Objetivo:

Simular disco con páginas (4KB) + contador de accesos

## 📌 Tareas

* Page Manager (read/write pages)
* Buffer básico (opcional)
* Contador de accesos a disco
* Serialización de registros

## ⚠️ IMPORTANTE

TODO debe operar por páginas (NO cargar todo en RAM)

## 👥 Trabajo simultáneo

* **Elmer** → Page Manager
* **Joseph** → Sistema de archivos (persistencia)
* **Paulo** → Formato de registros (serialización)
* **Jossue** → Contador de accesos (metrics)
* **Juanca** → Testing base + validación

---

# 🌲 FASE 2: ÍNDICES (CORE DEL PROYECTO)

## 🎯 Objetivo:

Implementar estructuras principales

## 🔹 Subfase 2.1: Sequential File

* Overflow file
* Reconstrucción

👉 **Asignación**

* Elmer + Paulo

---

## 🔹 Subfase 2.2: Extendible Hashing

* Directorio dinámico
* Split buckets

👉 **Asignación**

* Joseph + Jossue

---

## 🔹 Subfase 2.3: B+ Tree

* Nodos paginados
* Range search

👉 **Asignación**

* Juanca + Elmer

---

## 🔹 Subfase 2.4: R-Tree (espacial)

* Adaptar implementación
* Integrar con páginas
* Visualización

👉 **Asignación**

* Paulo + Jossue

---

## ⚠️ TODOS deben:

* Usar la capa de páginas
* Implementar:

  * add
  * search
  * remove
  * rangeSearch / kNN

---

# 🧾 FASE 3: PARSER SQL

## 🎯 Objetivo:

Traducir SQL → llamadas a índices

## 📌 Tareas

* Lexer (tokens)
* Parser (gramática)
* Traductor a funciones

## 👥 Distribución

* **Jossue** → Lexer
* **Joseph** → Parser (gramática)
* **Elmer** → Ejecutor (bridge a índices)
* **Paulo** → Soporte queries espaciales
* **Juanca** → Testing de queries

---

# ⚡ FASE 4: CONCURRENCIA

## 🎯 Objetivo:

Simular múltiples transacciones

## 📌 Tareas

* Simulación de threads
* Log de operaciones
* Conflictos

## ⭐ Opcional (recomendado):

* Locks (shared/exclusive)
* Deadlock detection

## 👥 Distribución

* **Joseph** → Motor de concurrencia
* **Elmer** → Integración con índices
* **Jossue** → Sistema de logs
* **Paulo** → Casos de prueba
* **Juanca** → Visualización / debugging

---

# 🖥️ FASE 5: FRONTEND

## 🎯 Objetivo:

Interfaz usable

## 📌 Debe tener:

* Editor SQL
* Tabla de resultados
* Métricas (tiempo + accesos)
* Visualización R-Tree

## 👥 Distribución

* **Juanca** → UI principal
* **Paulo** → Visualización gráfica (R-Tree)
* **Joseph** → API backend ↔ frontend
* **Elmer** → Métricas en tiempo real
* **Jossue** → Testing UI

---

# 📊 FASE 6: EVALUACIÓN EXPERIMENTAL

## 🎯 Objetivo:

Comparar rendimiento

## 📌 Tareas

* Tests con:

  * 1k
  * 10k
  * 100k datos
* Medir:

  * Accesos a disco
  * Tiempo

## 👥 Distribución

* **Paulo** → Generación datasets
* **Joseph** → Scripts de medición
* **Elmer** → Instrumentación código
* **Jossue** → Análisis resultados
* **Juanca** → Gráficos

---

# 📄 FASE 7: INFORME

## 🎯 Objetivo:

Documento técnico completo

## 📌 Secciones

* Índices (algoritmos)
* Parser (gramática)
* Resultados
* Análisis teórico vs real

## 👥 Distribución

* **Elmer** → Índices
* **Joseph** → Concurrencia + sistema
* **Paulo** → Experimentos
* **Jossue** → Parser
* **Juanca** → Redacción + formato

---

# 🎤 FASE 8: PRESENTACIÓN

## 🎯 Objetivo:

Demo clara + explicación técnica

## 👥 Roles

* **Elmer** → Arquitectura
* **Joseph** → Backend
* **Paulo** → Experimentos
* **Jossue** → Parser
* **Juanca** → Demo UI

---

# 🔁 FLUJO DE TRABAJO SEMANAL

* Daily rápido (10–15 min)
* Branch por feature
* Pull Requests obligatorios
* Testing continuo

---

# ⚠️ RIESGOS IMPORTANTES

❌ No usar páginas → pierden puntos
❌ Hacer índices en memoria → mal
❌ No medir accesos → mal
❌ Parser incompleto → baja nota

---

# 🧠 ESTRATEGIA PRO

* Empiecen por:

  1. Page Manager
  2. Sequential File (más fácil)
* Luego:

  * B+ Tree (clave)
* Dejen:

  * R-Tree y concurrencia para después

---

# 🔥 CONCLUSIÓN

Este proyecto es básicamente construir un **mini PostgreSQL desde cero**.

Si se organizan bien:

* Cada uno lidera un módulo
* Pero TODOS integran
