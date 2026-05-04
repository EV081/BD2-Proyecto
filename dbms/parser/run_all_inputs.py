import os
import subprocess
import sys
import shutil

# Configuración
input_dir = "inputs"
output_dir = "outputs"
main_script = "main.py"

print("--- Starting tests ---")

if not os.path.exists(input_dir):
    print(f"Error: No se encontró la carpeta '{input_dir}'")
    sys.exit(1)

os.makedirs(output_dir, exist_ok=True)

for i in range(1, 9):
    filename = f"input{i}.txt"
    filepath = os.path.join(input_dir, filename)
    ast_filepath = os.path.join(input_dir, f"input{i}_ast.json")
    output_file = os.path.join(output_dir, f"output{i}.txt")

    if os.path.isfile(filepath):
        print(f"Procesando: {filename}...", end=" ")

        # Limpiar salidas previas
        if os.path.isfile(ast_filepath):
            os.remove(ast_filepath)

        result = subprocess.run(
            [sys.executable, main_script, filepath, output_dir],
            capture_output=True,
            text=True
        )

        # Guardar stdout y stderr en outputs/outputN.txt
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=== STDOUT ===\n")
            f.write(result.stdout)
            f.write("\n=== STDERR ===\n")
            f.write(result.stderr)

        # Verificar si el script retornó 0 (indicativo de éxito general)
        if result.returncode == 0:
            print("[+] OK")
        else:
            print("[!] ERROR")
            if result.stdout.strip():
                print("    - Salida estándar (stdout):")
                for line in result.stdout.strip().split('\n'):
                    print(f"      {line}")
            if result.stderr.strip():
                print("    - Error estándar (stderr):")
                for line in result.stderr.strip().split('\n'):
                    print(f"      {line}")
            print("-" * 40)
    else:
        print(f"Aviso: {filename} no encontrado en '{input_dir}'")

print("\n--- End testing ---")
print(f"\nResultados guardados en '{output_dir}/'")