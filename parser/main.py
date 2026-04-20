import sys
import os
from scanner import *

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

if __name__ == "__main__":
    main()