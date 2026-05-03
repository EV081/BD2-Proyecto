import sys
import os
import json
from scanner import *
from parser import Parser, ParserError
from visitor import PrintVisitor, ExecuteVisitor


def collect_tokens(scanner):
    tokens = []
    while True:
        token = scanner.next_token()
        tokens.append(token)
        if token.type in (TokenType.EOF, TokenType.ERROR):
            break
    return tokens


def execute_parser(scanner, input_path, output_dir=None):
    tokens = collect_tokens(scanner)

    if tokens and tokens[-1].type == TokenType.ERROR:
        print(f"No se pudo analizar la entrada por un error léxico: {tokens[-1]}")
        return False

    parser = Parser(tokens)
    output_path = build_ast_output_path(input_path, output_dir)

    try:
        ast_nodes = parser.parse_program()

        # --- PrintVisitor: reconstruye y muestra el SQL (Codigo) ---
        print("Codigo:")
        printer = PrintVisitor()
        for node in ast_nodes:
            node.accept(printer)

        # --- ExecuteVisitor: muestra qué haría la BD (Ejecucion) ---
        print("\nEjecucion:")
        executor = ExecuteVisitor()
        for node in ast_nodes:
            node.accept(executor)

        # --- Serialización JSON ---
        write_ast_file(output_path, [node.to_dict() for node in ast_nodes])
        print("\nParser exitoso")
        print(f"AST guardado en: {output_path}")
        return True
    except ParserError as error:
        print(f"Parser no exitoso: {error}")
        return False


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


if __name__ == "__main__":
    main()