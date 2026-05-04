# EBNF

$$
\begin{aligned}
\textit{Program} \quad &::= \quad \textit{StmtList} \\
\textit{StmtList} \quad &::= \quad \textit{Stmt} \ \{ \text{ ; } \ \textit{Stmt} \}^* \ [ \text{ ; } ] \\
\textit{Stmt} \quad &::= \quad \textit{CreateStmt} \ | \ \textit{SelectStmt} \ | \ \textit{InsertStmt} \ | \ \textit{DeleteStmt} \\
\\
\textit{CreateStmt} \quad &::= \quad \text{ CREATE TABLE } \ \textit{Id} \ \text{ (} \ \textit{ColDef} \ \{ \text{ , } \ \textit{ColDef} \}^* \ \text{ )} \ [ \text{ FROM FILE } \ \textit{Path} ] \\
\textit{ColDef} \quad &::= \quad \textit{Id} \ \textit{Type} \ [ \text{ INDEX } \ \textit{IndexTech} ] \\
\textit{IndexTech} \quad &::= \quad \text{ SEQUENTIAL } \ | \ \text{ HASH } \ | \ \text{ BTREE } \ | \ \text{ RTREE } \\
\\
\textit{SelectStmt} \quad &::= \quad \text{ SELECT } \ \textit{Cols} \ \text{ FROM } \ \textit{Id} \ \text{ WHERE } \ \textit{Condition} \\
\textit{Cols} \quad &::= \quad \text{ * } \ | \ \textit{Id} \ \{ \text{ , } \ \textit{Id} \}^* \\
\textit{Condition} \quad &::= \quad \textit{Id} \ \text{ RelOp } \ \textit{Value} \\
& | \quad \textit{Id} \ \text{ BETWEEN } \ \textit{Value} \ \text{ AND } \ \textit{Value} \\
& | \quad \textit{Id} \ \text{ IN } \ \text{ ( } \ \textit{SpatialCond} \ \text{ ) } \\
\textit{SpatialCond} \quad &::= \quad \text{ POINT } \ \text{ ( } \ \textit{Number} \ \text{ , } \ \textit{Number} \ \text{ ) } \ \text{ , } \ ( \text{ RADIUS } \ \textit{Number} \ | \ \text{ K } \ \textit{Number} ) \\
\\
\textit{InsertStmt} \quad &::= \quad \text{ INSERT INTO } \ \textit{Id} \ \text{ VALUES } \ \text{ ( } \ \textit{Value} \ \{ \text{ , } \ \textit{Value} \}^* \ \text{ ) } \\
\textit{DeleteStmt} \quad &::= \quad \text{ DELETE FROM } \ \textit{Id} \ \text{ WHERE } \ \textit{Id} \ \textit{RelOp} \ \textit{Value} \\
\\
\textit{RelOp} \quad &::= \quad \text{ = } \ | \ \text{ < } \ | \ \text{ > } \ | \ \text{ <= } \ | \ \text{ >= } \ | \ \text{ != } \\
\textit{Type} \quad &::= \quad \text{ INT } \ | \ \text{ FLOAT } \ | \ \text{ VARCHAR } \\
\textit{Value} \quad &::= \quad \textit{Number} \ | \ \textit{String} \\
\end{aligned}
$$

# Ejemplos

CREATE TABLE Estudiantes (id INT INDEX BTREE, nombre VARCHAR, nota FLOAT) FROM FILE "data/alumnos.csv";

CREATE TABLE Usuarios (user_id INT INDEX HASH, username VARCHAR);

CREATE TABLE Locales (id INT, ubicacion POINT INDEX RTREE) FROM FILE "data/puntos_interes.csv";

SELECT * FROM Estudiantes WHERE id = 105;

SELECT * FROM Estudiantes WHERE nota BETWEEN 11 AND 20;

SELECT * FROM Locales WHERE ubicacion IN (POINT(-12.04, -77.02), RADIUS 500);

SELECT * FROM Locales WHERE ubicacion IN (POINT(-12.04, -77.02), K 5);

INSERT INTO Estudiantes VALUES (110, "Juan Perez", 15.5);

DELETE FROM Usuarios WHERE user_id = 500;