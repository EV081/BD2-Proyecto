import os
import sys
import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dbms.parser.main import moduled_main
from dbms.utils.schema import SchemaManager


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
    data_folder = os.path.join(PROJECT_ROOT, "uploaded_files")

    if not os.path.isdir(data_folder):
        return {"csv_files": []}

    csv_files = []
    for filename in os.listdir(data_folder):
        if filename.endswith(".csv"):
            csv_files.append(filename)

    csv_files.sort()
    return {"csv_files": csv_files}

@app.post("/csv/data")
async def upload_csv_data(file: bytes, filename: str):
    data_folder = os.path.join(PROJECT_ROOT, "uploaded_files")

    if not os.path.isdir(data_folder):
        os.makedirs(data_folder)
        
    #normalize the filename, and if it has an invalidad name, raise an error
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail={"type": "InvalidFileName", "message": "Filename must end with .csv"})
    filename = filename.replace("/", "_").replace("\\", "_")  # Prevent directory traversal
    
    file_path = os.path.join(data_folder, filename)

    try:
        with open(file_path, "wb") as out_file:
            out_file.write(file)
    except OSError as e:
        raise HTTPException(status_code=500, detail={"type": "FileUploadError", "message": f"Error saving file: {str(e)}"})

    return {"message": f"File '{filename}' uploaded successfully."}

@app.delete("/csv/data/{filename}")
async def delete_csv_data(filename: str):
    data_folder = os.path.join(PROJECT_ROOT, "uploaded_files")
    file_path = os.path.join(data_folder, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail={"type": "FileNotFoundError", "message": f"File '{filename}' not found."})

    try:
        os.remove(file_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail={"type": "FileDeletionError", "message": f"Error deleting file: {str(e)}"})

    return {"message": f"File '{filename}' deleted successfully."}

