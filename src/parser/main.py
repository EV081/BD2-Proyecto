import sys
import os
import json

from .scanner import *
from .parser import Parser, ParserError
from .visitor import TraceVisitor
from .db_visitor import DBVisitor
from src.api.dbengine import execute_sql


def collect_tokens(scanner):
    tokens = []
    while True:
        token = scanner.next_token()
        tokens.append(token)
        if token.type in (TokenType.EOF, TokenType.ERROR):
            break
    return tokens


def execute_parser(scanner, input_path, output_dir=None, persist_ast=True):
    tokens = collect_tokens(scanner)

    if tokens and tokens[-1].type == TokenType.ERROR:
        error = {
            "success": False,
            "error": {
                "type": "LexicalError",
                "message": f"No se pudo analizar la entrada por un error léxico: {tokens[-1]}",
                "phase": "scan",
            },
        }
        print(error["error"]["message"])
        return error

    parser = Parser(tokens)
    output_path = build_ast_output_path(input_path, output_dir) if persist_ast else None
    execution_results = []

    def _normalize_result(node, result):
        statement = node.to_dict()
        metrics = None

        if isinstance(result, dict) and "metrics" in result:
            metrics = result.pop("metrics")

        if statement.get("type") == "select" and isinstance(result, dict):
            if result.get("is_spatial"):
                res = {
                    "statement": statement,
                    "type": "select",
                    "table": statement.get("table"),
                    "is_spatial": True,
                    "spatial_data": result.get("spatial_data"),
                }
                if metrics is not None:
                    res["metrics"] = metrics
                return res
            elif "columns" in result and "rows" in result:
                res = {
                    "statement": statement,
                    "type": "select",
                    "table": statement.get("table"),
                    "columns": result["columns"],
                    "rows": result["rows"],
                }
                if metrics is not None:
                    res["metrics"] = metrics
                return res

        if isinstance(result, list):
            res = {
                "statement": statement,
                "type": "select" if statement.get("type") == "select" else "rows",
                "columns": statement.get("columns", []) if statement.get("type") == "select" else [],
                "rows": result,
            }
            if metrics is not None:
                res["metrics"] = metrics
            return res

        if isinstance(result, int):
            if statement.get("type") == "insert":
                return {
                    "statement": statement,
                    "type": "insert",
                    "affected_rows": 1,
                    "rid": result,
                }
            if statement.get("type") == "delete":
                return {
                    "statement": statement,
                    "type": "delete",
                    "affected_rows": result,
                }

        if statement.get("type") == "insert" and isinstance(result, dict) and "rid" in result:
            res = {
                "statement": statement,
                "type": "insert",
                "affected_rows": 1,
                "rid": result["rid"],
            }
            if metrics is not None:
                res["metrics"] = metrics
            return res

        if statement.get("type") == "delete" and isinstance(result, dict) and "deleted" in result:
            res = {
                "statement": statement,
                "type": "delete",
                "affected_rows": result["deleted"],
            }
            if metrics is not None:
                res["metrics"] = metrics
            return res

        if result is None:
            if statement.get("type") == "create_table":
                res = {
                    "statement": statement,
                    "type": "create_table",
                    "status": "ok",
                    "table": statement.get("name"),
                }
                if metrics is not None:
                    res["metrics"] = metrics
                return res
            return {
                "statement": statement,
                "type": statement.get("type"),
                "status": "ok",
            }

        if statement.get("type") == "create_table":
            res = {
                "statement": statement,
                "type": "create_table",
                "status": "ok",
                "table": statement.get("name"),
            }
            if metrics is not None:
                res["metrics"] = metrics
            return res

        if isinstance(result, (dict, str, int, float, bool)) or result is None:
            res = {
                "statement": statement,
                "type": statement.get("type"),
                "result": result,
            }
            if metrics is not None:
                res["metrics"] = metrics
            return res

        res = {
            "statement": statement,
            "type": statement.get("type"),
            "result": str(result),
        }
        if metrics is not None:
            res["metrics"] = metrics
        return res

    try:
        ast_nodes = parser.parse_program()

        # --- TraceVisitor: muestra SQL + descripcion (debug/traza) ---
        print("Traza:")
        tracer = TraceVisitor()
        for node in ast_nodes:
            node.accept(tracer)

        # --- DBVisitor: ejecuta realmente contra el motor de BD ---
        print("\nEjecucion:")
        db_visitor = DBVisitor()
        for node in ast_nodes:
            result = node.accept(db_visitor)
            execution_results.append(_normalize_result(node, result))

        # --- Serialización JSON ---
        if persist_ast and output_path is not None:
            write_ast_file(output_path, [node.to_dict() for node in ast_nodes])
            print("\nParser exitoso")
            print(f"AST guardado en: {output_path}")
        else:
            print("\nParser exitoso")
        return {
            "success": True,
            "ast": [node.to_dict() for node in ast_nodes],
            "results": execution_results,
        }
    except ParserError as error:
        payload = {
            "success": False,
            "error": {
                "type": error.__class__.__name__,
                "message": str(error),
                "phase": "parse",
            },
        }
        print(f"Parser no exitoso: {error}")
        return payload
    except Exception as error:
        payload = {
            "success": False,
            "error": {
                "type": error.__class__.__name__,
                "message": str(error),
                "phase": "execution",
            },
        }
        print(f"Ejecucion no exitosa: {error.__class__.__name__}: {error}")
        return payload


def build_ast_output_path(input_path, output_dir=None):
    base_name = os.path.basename(input_path)
    name, _ = os.path.splitext(base_name)
    if output_dir:
        if name.startswith("input"):
            idx = name[5:]
            return os.path.join(output_dir, f"ast_{idx}.json")
        return os.path.join(output_dir, f"{name}_ast.json")
    else:
        return f"{name}_ast.json"


def write_ast_file(output_path, ast):
    with open(output_path, 'w', encoding='utf-8') as out_file:
        json.dump(ast, out_file, indent=4, ensure_ascii=False)
        out_file.write("\n")


def main():
    if len(sys.argv) < 2:
        print("Número incorrecto de argumentos.")
        print(f"Uso: python {sys.argv[0]} <archivo_de_entrada> [carpeta_salida]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        with open(input_path, 'r', encoding='utf-8') as infile:
            input_content = infile.read()
    except FileNotFoundError:
        print(f"No se pudo abrir el archivo: {input_path}")
        sys.exit(1)

    scanner_inst = Scanner(input_content)
    execute_scanner(scanner_inst, input_path, output_dir)

    # Inicializamos un nuevo scanner exclusivo para el parser
    parser_inst = Scanner(input_content)
    parser_ok = execute_parser(parser_inst, input_path, output_dir)

    if not parser_ok:
        sys.exit(1)
    sys.exit(0)


def moduled_main(query):
    return execute_sql(query)


if __name__ == "__main__":
    main()