import os
import subprocess
import sys

# Configuración
input_dir = "inputs"
main_script = "main.py"

print("--- Starting tests ---")

if not os.path.exists(input_dir):
    print(f"Error: No se encontró la carpeta '{input_dir}'")
    sys.exit(1)

for i in range(1, 9):
    filename = f"input{i}.txt"
    filepath = os.path.join(input_dir, filename)
    ast_filepath = os.path.join(input_dir, f"input{i}_ast.json")
    
    if os.path.isfile(filepath):
        print(f"Procesando: {filename}...", end=" ")

        if os.path.isfile(ast_filepath):
            os.remove(ast_filepath)
        
        result = subprocess.run(
            [sys.executable, main_script, filepath],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and os.path.isfile(ast_filepath):
            print("[+] OK")
        else:
            print("[!] ERROR")
            if not os.path.isfile(ast_filepath):
                print(f"No se generó el AST en {ast_filepath}")
            print(result.stderr)
    else:
        print(f"Aviso: {filename} no encontrado en '{input_dir}'")

print("\n--- End testing ---")