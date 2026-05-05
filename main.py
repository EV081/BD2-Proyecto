import os
import sys
import json

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dbms.parser.main import moduled_main
from dbms.utils.schema import SchemaManager

UPLOADED_FILES_DIR = os.path.join(PROJECT_ROOT, "uploaded_files")


class Query(BaseModel):
    query: str


app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/query")
async def query_status():
    return {"message": "Query received"}


@app.get("/tables")
async def list_tables():
    schema_folder = SchemaManager.SCHEMA_FOLDER

    if not os.path.isdir(schema_folder):
        return {"tables": []}

    tables = []
    for filename in os.listdir(schema_folder):
        if filename.endswith(".json"):
            table_name = os.path.splitext(filename)[0]
            schema_path = os.path.join(schema_folder, filename)

            try:
                with open(schema_path, "r", encoding="utf-8") as schema_file:
                    schema_data = json.load(schema_file)
            except (OSError, json.JSONDecodeError):
                continue

            tables.append({
                "name": table_name,
                "columns": schema_data.get("columns", {}),
                "primary_key": schema_data.get("primary_key"),
                "indexes": schema_data.get("indexes", []),
                "point_columns": schema_data.get("point_columns", {}),
            })

    tables.sort(key=lambda table: table["name"])
    return {"tables": tables}


@app.post("/query")
async def query(query: Query):
    result = moduled_main(query.query)

    if not result.get("success", False):
        error = result.get("error", {})
        error_type = error.get("type", "ExecutionError")
        status_code = 400 if error_type in {"LexicalError", "ParserError", "ValueError", "RuntimeError", "NotImplementedError"} else 500
        raise HTTPException(status_code=status_code, detail=error)

    return result


@app.get("/csv/data")
async def get_csv_data_list():
    if not os.path.isdir(UPLOADED_FILES_DIR):
        return {"csv_files": []}

    csv_files = []
    for filename in os.listdir(UPLOADED_FILES_DIR):
        if filename.endswith(".csv"):
            csv_files.append(filename)

    csv_files.sort()
    return {"csv_files": csv_files}


@app.post("/csv/data")
async def upload_csv_data(file: UploadFile = File(...)):
    os.makedirs(UPLOADED_FILES_DIR, exist_ok=True)

    filename = file.filename or "unnamed.csv"
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail={"type": "InvalidFileName", "message": "Filename must end with .csv"})
    filename = filename.replace("/", "_").replace("\\", "_")

    file_path = os.path.join(UPLOADED_FILES_DIR, filename)

    try:
        content = await file.read()
        with open(file_path, "wb") as out_file:
            out_file.write(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail={"type": "FileUploadError", "message": f"Error saving file: {str(e)}"})

    return {"message": f"File '{filename}' uploaded successfully.", "filename": filename}


@app.delete("/csv/data/{filename}")
async def delete_csv_data(filename: str):
    file_path = os.path.join(UPLOADED_FILES_DIR, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail={"type": "FileNotFoundError", "message": f"File '{filename}' not found."})

    try:
        os.remove(file_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail={"type": "FileDeletionError", "message": f"Error deleting file: {str(e)}"})

    return {"message": f"File '{filename}' deleted successfully."}


class CreateTableFromCSV(BaseModel):
    table_name: str
    filename: str
    columns: list[dict]  # [{"name": "col1", "type": "INT", "index": "BTREE"}, ...]


@app.post("/tables/from-csv")
async def create_table_from_csv(body: CreateTableFromCSV):
    """
    Crea una tabla a partir de un CSV previamente subido a uploaded_files/.

    Body:
      - table_name: nombre de la tabla
      - filename: nombre del archivo CSV en uploaded_files/
      - columns: lista de columnas con name, type, y opcionalmente index
        Ejemplo: [{"name": "id", "type": "INT", "index": "BTREE"}, {"name": "nombre", "type": "VARCHAR"}]
    """
    csv_path = os.path.join(UPLOADED_FILES_DIR, body.filename)
    if not os.path.isfile(csv_path):
        raise HTTPException(status_code=404, detail={
            "type": "FileNotFoundError",
            "message": f"CSV file '{body.filename}' not found in uploaded_files/."
        })

    # Construir la query SQL CREATE TABLE ... FROM FILE
    col_defs = []
    for col in body.columns:
        col_def = f"{col['name']} {col['type']}"
        if col.get("index"):
            col_def += f" INDEX {col['index']}"
        col_defs.append(col_def)

    columns_sql = ", ".join(col_defs)
    query_sql = f"CREATE TABLE {body.table_name} ({columns_sql}) FROM FILE '{body.filename}'"

    result = moduled_main(query_sql)

    if not result.get("success", False):
        error = result.get("error", {})
        raise HTTPException(status_code=400, detail=error)

    return result

