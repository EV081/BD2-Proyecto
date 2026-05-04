import os
import sys

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dbms.parser.main import moduled_main


class Query(BaseModel):
    query: str


app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/query")
async def query_status():
    return {"message": "Query received"}


@app.post("/query")
async def query(query: Query):
    result = moduled_main(query.query)

    if not result.get("success", False):
        error = result.get("error", {})
        error_type = error.get("type", "ExecutionError")
        status_code = 400 if error_type in {"LexicalError", "ParserError", "ValueError", "RuntimeError", "NotImplementedError"} else 500
        raise HTTPException(status_code=status_code, detail=error)

    return result
