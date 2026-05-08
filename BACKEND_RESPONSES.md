# Contrato de respuestas del backend

Este documento describe los endpoints que existen en el backend actual, qué reciben y qué devuelven.

## Errores comunes

Cuando el backend lanza `HTTPException`, la respuesta sigue esta forma:

```json
{
  "detail": {
    "type": "NombreDelError",
    "message": "Descripción del problema",
    "phase": "scan | parse | execution"
  }
}
```

El campo `phase` es opcional. En errores de validación de FastAPI, la respuesta no usa este formato.

## `GET /`

Recibe: nada.

Retorna:

```json
{
  "message": "Hello World"
}
```

Tipo: `{ message: string }`.

## `GET /query`

Recibe: nada.

Retorna:

```json
{
  "message": "Query received"
}
```

Tipo: `{ message: string }`.

## `GET /tables`

Recibe: nada.

Retorna:

```json
{
  "tables": [
    {
      "name": "HarderNya",
      "columns": {
        "id": "int",
        "nombre": "char(255)",
        "nota": "float"
      },
      "primary_key": "id",
      "indexes": [
        {
          "column": "id",
          "type": "bplus",
          "unique": false
        }
      ],
      "point_columns": {}
    }
  ]
}
```

Tipado sugerido:

```ts
type SchemaIndex = {
  column: string | [string, string]
  type: string
  unique: boolean
}

type SchemaTable = {
  name: string
  columns: Record<string, string>
  primary_key: string | null
  indexes: SchemaIndex[]
  point_columns: Record<string, [string, string]>
}

type TablesResponse = {
  tables: SchemaTable[]
}
```

Si no existe la carpeta de esquemas, retorna:

```json
{
  "tables": []
}
```

## `POST /query`

Recibe:

```json
{
  "query": "SELECT * FROM HarderNya"
}
```

Retorna en éxito:

```json
{
  "success": true,
  "ast": [
    {
      "type": "select",
      "columns": ["*"],
      "table": "HarderNya",
      "where": null
    }
  ],
  "results": [
    {
      "statement": {
        "type": "select",
        "columns": ["*"],
        "table": "HarderNya",
        "where": null
      },
      "type": "select",
      "columns": ["id", "nombre", "nota"],
      "rows": [
        [1, "Ana", 8.5],
        [2, "Carlos", 7.25]
      ]
    }
  ]
}
```

Tipado sugerido:

```ts
type ComparisonCond = {
  type: "comparison"
  left: string
  operator: string
  right: unknown
}

type BetweenCond = {
  type: "between"
  left: string
  lower: unknown
  upper: unknown
}

type SpatialPointCond = {
  type: "spatial_point"
  x: number
  y: number
  search_type: "radius" | "k"
  search_value: unknown
}

type InSpatialCond = {
  type: "in_spatial"
  left: string
  spatial_condition: SpatialPointCond
}

type CreateTableAst = {
  type: "create_table"
  name: string
  columns: Array<{
    name: string
    data_type: string
    index: string | null
  }>
  file: string | null
}

type SelectAst = {
  type: "select"
  columns: string[]
  table: string
  where: ComparisonCond | BetweenCond | InSpatialCond | null
}

type InsertAst = {
  type: "insert"
  table: string
  values: unknown[]
}

type DeleteAst = {
  type: "delete"
  table: string
  where: ComparisonCond
}

type QueryAst = CreateTableAst | SelectAst | InsertAst | DeleteAst

type SelectResult = {
  statement: SelectAst
  type: "select"
  columns: string[]
  rows: unknown[][]
}

type InsertResult = {
  statement: InsertAst
  type: "insert"
  affected_rows: 1
  rid: number
}

type DeleteResult = {
  statement: DeleteAst
  type: "delete"
  affected_rows: number
}

type CreateTableResult = {
  statement: CreateTableAst
  type: "create_table"
  status: "ok"
  table: string | null
}

type GenericResult = {
  statement: QueryAst
  type: string
  result?: unknown
  status?: "ok"
}

type QueryResponse = {
  success: true
  ast: QueryAst[]
  results: Array<SelectResult | InsertResult | DeleteResult | CreateTableResult | GenericResult>
}
```

El campo `results` es heterogéneo. Según la sentencia puede devolver:

- `SELECT`: `{ type: "select", columns: string[], rows: unknown[][] }`
- `INSERT`: `{ type: "insert", affected_rows: 1, rid: number }`
- `DELETE`: `{ type: "delete", affected_rows: number }`
- `CREATE TABLE`: `{ type: "create_table", status: "ok", table: string | null }`
- Otros casos: `{ type: string, result: unknown }` o `{ type: string, status: "ok" }`

En caso de error, el backend responde con `400` para `LexicalError`, `ParserError`, `ValueError`, `RuntimeError` y `NotImplementedError`, o `500` para otros errores.

## `GET /csv/data`

Recibe: nada.

Retorna:

```json
{
  "csv_files": ["HarderNya.csv"]
}
```

Tipo: `{ csv_files: string[] }`.

Si no existe `uploaded_files`, retorna:

```json
{
  "csv_files": []
}
```

## `POST /csv/data`

Recibe: multipart form-data con el campo `file`.

Retorna:

```json
{
  "message": "File 'HarderNya.csv' uploaded successfully.",
  "filename": "HarderNya.csv"
}
```

Tipo: `{ message: string, filename: string }`.

Errores:

- `400` si el nombre no termina en `.csv`.
- `500` si falla el guardado.

## `DELETE /csv/data/{filename}`

Recibe: `filename` en la ruta.

Retorna:

```json
{
  "message": "File 'HarderNya.csv' deleted successfully."
}
```

Tipo: `{ message: string }`.

Errores:

- `404` si el archivo no existe.
- `500` si falla el borrado.

## Errores estándar de FastAPI

- `422 Unprocessable Entity`: validación fallida de entrada.
- `405 Method Not Allowed`: método HTTP no permitido.
- `500 Internal Server Error`: excepción no controlada.
