"""
Schema Manager
Administra la metadata de las tablas
 - Nombre de columnas
 - Tipos
 - Indices
 - Llaves
"""

import json
import os

class SchemaManager:

    SCHEMA_FOLDER = "schemas"
    
    def __init__(self, table_name, schema=None):
        self.table_name = table_name
        self.schema_filename = os.path.join(
            self.SCHEMA_FOLDER,
            f"{table_name}.json"
        )
        self.schema = schema

    def create_schema(self):
        """
        Guarda el schema en un archivo JSON
        """
        if self.schema is None:
            raise ValueError("No existe un schema.")
        
        os.makedirs(self.SCHEMA_FOLDER, exist_ok=True)

        with open(self.schema_filename, "w", encoding="utf-8") as file:
            json.dump(self.schema, file, indent=4)
        
        return True

    def get_schema(self):
        """
        Lee y retorna el schema desde disco
        """
        if not os.path.exists(self.schema_filename):
            raise FileNotFoundError(
                f"Schema para la table '{self.table_name}' no existe."
            )
            
        with open(self.schema_filename, "r", encoding="utf-8") as file:
            self.schema = json.load(file)
        
        return self.schema

    def update_schema(self, new_schema):
        """
        Reemplaza el schema actual
        """
        self.schema = new_schema
        return self.create_schema()

    def delete_schema(self):
        """
        Elimina el archivo de schema
        """
        if os.path.exists(self.schema_filename):
            os.remove(self.schema_filename)
            return True

        return false

    def schema_exists(self):
        """
        Verifica si exista el schema
        """
        return os.path.exists(self.schema_filename)

