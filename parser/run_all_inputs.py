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

for i in range(1, 8):
    filename = f"input{i}.txt"
    filepath = os.path.join(input_dir, filename)
    
    if os.path.isfile(filepath):
        print(f"Procesando: {filename}...", end=" ")
        
        result = subprocess.run(
            [sys.executable, main_script, filepath],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("[+] OK")
        else:
            print("[!] ERROR")
            print(result.stderr)
    else:
        print(f"Aviso: {filename} no encontrado en '{input_dir}'")

print("\n--- End testing ---")