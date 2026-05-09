import os
import sys
import json

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api.dbengine import execute_sql
from src.storage.schema import SchemaManager

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

            columns = schema_data.get("columns", {})

            tables.append({
                "name": table_name,
                "columns": columns,
                "primary_key": schema_data.get("primary_key"),
                "indexes": schema_data.get("indexes", []),
                "point_columns": schema_data.get("point_columns", {}),
                "record_count": schema_data.get("record_count", 0),
            })

    tables.sort(key=lambda table: table["name"])
    return {"tables": tables}


@app.post("/query")
async def query(query: Query):
    result = execute_sql(query.query)

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