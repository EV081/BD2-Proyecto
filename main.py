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
