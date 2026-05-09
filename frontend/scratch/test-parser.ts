import { parseDb2Program } from "../src/lib/db2/parser";

const query = "CREATE TABLE table (id INT PRIMARY KEY, name VARCHAR);";
const result = parseDb2Program(query);

console.log(JSON.stringify(result, null, 2));
