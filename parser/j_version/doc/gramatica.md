# Gramática del lenguaje

Este documento describe la gramática inferida a partir de `parser/lexer_token.py` y de los archivos de ejemplo en `parser/inputs/`.

## 1. Léxico

### Palabras reservadas

`CREATE`, `TABLE`, `SELECT`, `FROM`, `WHERE`, `INSERT`, `INTO`, `VALUES`, `DELETE`, `FILE`, `INDEX`, `SEQUENTIAL`, `HASH`, `BPLUS`, `RTREE`, `BETWEEN`, `AND`, `IN`, `POINT`, `RADIUS`, `K`

### Símbolos

`=`, `<`, `>`, `*`, `,`, `(`, `)`, `;`, `"`, `'`, `[`, `]`, `.`

### Tokens de dato

`ID`, `NUMBER`, `STRING_LITERAL`, `EOF`, `ERROR`

## 2. Gramática sintáctica

La gramática se expresa en una forma cercana a EBNF.

```ebnf
Program           ::= Statement EOF

Statement         ::= CreateTableStmt
                    | SelectStmt
                    | InsertStmt
                    | DeleteStmt

CreateTableStmt   ::= CREATE TABLE ID "(" ColumnDef { "," ColumnDef } ")" [ FromFileClause ] ";"

ColumnDef         ::= ID DataType [ IndexClause ]

DataType          ::= ID

IndexClause       ::= INDEX IndexTechnique

FromFileClause    ::= FROM FILE FilePath

FilePath          ::= StringLiteral

SelectStmt        ::= SELECT "*" FROM ID [ WhereClause ] ";"

WhereClause       ::= WHERE Condition

Condition         ::= Comparison
                    | BetweenCondition
                    | InCondition

Comparison        ::= ID ComparisonOperator Value

ComparisonOperator ::= "=" | "<" | ">"

BetweenCondition  ::= ID BETWEEN Value AND Value

InCondition       ::= ID IN "(" InValueList ")"

InValueList       ::= InValue "," InValue

InValue           ::= PointPredicate | SpatialPredicate

PointPredicate    ::= POINT "(" NUMBER "," NUMBER ")"

SpatialPredicate  ::= RADIUS NUMBER
                    | K NUMBER

InsertStmt        ::= INSERT INTO ID VALUES "(" ValueList ")" ";"

DeleteStmt        ::= DELETE FROM ID WHERE Comparison ";"

ValueList         ::= Value { "," Value }

Value             ::= NUMBER
                    | StringLiteral
                    | ID
                    | FilePath

IndexTechnique    ::= SEQUENTIAL
                    | HASH
                    | BPLUS
                    | RTREE

StringLiteral     ::= STRING_LITERAL
```

## 3. Propuesta de creacion de tablas

La forma de `CREATE TABLE` que se documenta aqui es mas tradicional y cumple el formato minimo requerido. Cada columna puede declarar o no una tecnica de indexacion local con `INDEX <tecnica>`. Si no se indica, el sistema debe aplicar un metodo por defecto.

Propuesta:

```sql
CREATE TABLE users (id INT INDEX BPLUS, name TEXT, age INT) FROM FILE "users.txt";
```

Comportamiento sugerido:

- Si una columna incluye `INDEX <tecnica>`, esa tecnica se usa para esa columna.
- Si una columna no incluye `INDEX <tecnica>`, el sistema aplica un indice por defecto definido internamente.
- Si la sentencia incluye `FROM FILE <path>`, los datos de inicializacion se cargan desde ese archivo.
- El indice por defecto puede ser `SEQUENTIAL` o `BPLUS`, segun la politica que se adopte para el motor.

## 4. Reglas observadas en los ejemplos

- `CREATE TABLE` usa un nombre de tabla, una lista de columnas y puede cargar datos desde archivo.
- `SELECT` usa `*`, `FROM` y opcionalmente `WHERE`.
- `WHERE` admite comparaciones simples, `BETWEEN` e `IN` con predicados espaciales.
- `INSERT` inserta una lista de valores separados por comas.
- `DELETE` elimina filas filtrando con una condicion simple.

## 5. Ejemplos validos

```sql
CREATE TABLE users (id INT INDEX BPLUS, name TEXT, age INT) FROM FILE "users.txt";
CREATE TABLE customers (customer_id INT INDEX HASH, city TEXT, balance NUMBER);
CREATE TABLE geo_points (point_id INT INDEX RTREE, x NUMBER, y NUMBER) FROM FILE "geo.txt";
CREATE TABLE audit_log (log_id INT, event TEXT, created_at TEXT) FROM FILE "audit.log";
SELECT * FROM testTB WHERE animes = "Wistoris";
SELECT * FROM users;
SELECT * FROM products WHERE price > 100;
SELECT * FROM music WHERE likes BETWEEN 1200 AND 4000;
SELECT * FROM games WHERE ranked IN (POINT(2, 3), RADIUS 20);
SELECT * FROM backdoors WHERE ips IN (POINT(3, 9), K 12);
INSERT INTO chatgpt VALUES ("try", "to", "solve", "this", "bug");
INSERT INTO logs VALUES (1, 2, 3, 4);
INSERT INTO books VALUES ("clean code", "martin", 2008);
DELETE FROM brain WHERE emotion = "peace";
DELETE FROM sessions WHERE id = 15;
```

## 6. Observacion tecnica

El archivo `parser/scanner.py` actualmente tokeniza identificadores, numeros y operadores, pero no construye todavia una rutina especifica para cargas desde archivo como `FROM FILE <path>` si el path viene sin comillas, ni una rutina especifica para cadenas completas entre comillas como `STRING_LITERAL`. Si se quiere que la gramatica quede implementada de forma completa, conviene extender el scanner para reconocer esos casos antes de usar esta propuesta como contrato de analisis.