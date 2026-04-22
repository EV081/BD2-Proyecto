"""
Archivo hecho para que puedan ver el funcionamiento de SchemaManager
Forma de usarlo:
 - $ python schema_tutorial.py
"""

from utils.schema import SchemaManager

# Digamos que esta es la formacion de metadatos de nuestra tabla students
# Hay mas metodos en schema.py como update y delete (Casi como operaciones CRUD)

schema = {
    "table_name": "students",
    "columns": {
        "id": "int",
        "name": "str",
        "age": "int"
    },
    "primary_key": "id",
    "index_type": "bplus"
}

# Crea dentro de la carpeta "schemas" un archivo llamado "students.json" (igual que la tabla)
manager = SchemaManager("students", schema)

# Guarda los metadatos dentro del archivo "students.json" creado en "schemas"
manager.create_schema()

# Carga la metada (se usa para si cambiamos de tabla recuperar la metadata)
loaded = manager.get_schema()

# Para ver que se cargo
print(loaded)

