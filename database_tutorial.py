from utils.database import DataBase

schema = {
    "id": "int",
    "name": "char(10)"
}

db = DataBase("users", schema)

db.insert({"id": 1, "name": "Juan"})
db.insert({"id": 2, "name": "Ana"})

print(db.select_all())