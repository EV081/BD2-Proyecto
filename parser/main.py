import sys
import os
import json
from scanner import *
from parser import Parser, ParserError

def collect_tokens(scanner):
    tokens = []

    while True:
        token = scanner.next_token()
        tokens.append(token)

        if token.type in (TokenType.EOF, TokenType.ERROR):
            break

    return tokens

def execute_parser(scanner, input_path):
    tokens = collect_tokens(scanner)

    if tokens and tokens[-1].type == TokenType.ERROR:
        print(f"No se pudo analizar la entrada por un error léxico: {tokens[-1]}")
        return False

    parser = Parser(tokens)
    output_path = build_ast_output_path(input_path)

    try:
        ast = parser.parse_program() 
        
        write_ast_file(output_path, ast)
        print("Parser exitoso")
        print(f"AST guardado en: {output_path}")
        return True
    except ParserError as error:
        print(f"Parser no exitoso: {error}")
        return False

def build_ast_output_path(input_path):
    base_name, _ = os.path.splitext(input_path)
    return f"{base_name}_ast.json"

def write_ast_file(output_path, ast):
    with open(output_path, 'w', encoding='utf-8') as out_file:
        json.dump(ast, out_file, indent=4, ensure_ascii=False)
        out_file.write("\n")

def main():
    if len(sys.argv) != 2:
        print("Número incorrecto de argumentos.")
        print(f"Uso: python {sys.argv[0]} <archivo_de_entrada>")
        sys.exit(1)

    input_path = sys.argv[1]

    try:
        with open(input_path, 'r', encoding='utf-8') as infile:
            input_content = infile.read()
    except FileNotFoundError:
        print(f"No se pudo abrir el archivo: {input_path}")
        sys.exit(1)

    scanner_inst = Scanner(input_content)
    execute_scanner(scanner_inst, input_path)

    # Inicializamos un nuevo scanner exclusivo para el parser
    parser_inst = Scanner(input_content)
    parser_ok = execute_parser(parser_inst, input_path)

    if not parser_ok:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()