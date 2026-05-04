from fastapi import FastAPI
from pydantic import BaseModel

class Query(BaseModel):
    query: str

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/query")
async def query():
    return {"message": "Query received"}

@app.post("/query")
async def query(query: Query):
    return {"message": "Query received", "query": query.query}

