import { db2Catalog } from "@src/lib/db2/catalog";
import type {
  Db2Column,
  Db2ExecuteQueryResponse,
  Db2Program,
  Db2Row,
  Db2Scalar,
  Db2Statement,
  Db2StatementExecutionResult,
  Db2Table,
  Db2WhereCondition,
} from "@src/types/db2";

function cloneCatalog(catalog: Db2Table[]): Db2Table[] {
  return catalog.map((table) => ({
    ...table,
    columns: table.columns.map((column) => ({ ...column })),
    rows: table.rows.map((row) => ({ ...row })),
  }));
}

function toNumber(value: Db2Scalar): number | null {
  if (typeof value === "number") {
    return value;
  }

  if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
    return Number(value);
  }

  return null;
}

function compareScalar(left: Db2Scalar, operator: string, right: Db2Scalar): boolean {
  const leftNumber = toNumber(left);
  const rightNumber = toNumber(right);

  if (leftNumber !== null && rightNumber !== null) {
    switch (operator) {
      case "=":
        return leftNumber === rightNumber;
      case "<":
        return leftNumber < rightNumber;
      case ">":
        return leftNumber > rightNumber;
      case "<=":
        return leftNumber <= rightNumber;
      case ">=":
        return leftNumber >= rightNumber;
      case "!=":
        return leftNumber !== rightNumber;
      default:
        return false;
    }
  }

  const leftText = String(left).toLowerCase();
  const rightText = String(right).toLowerCase();

  switch (operator) {
    case "=":
      return leftText === rightText;
    case "!=":
      return leftText !== rightText;
    case "<":
      return leftText < rightText;
    case ">":
      return leftText > rightText;
    case "<=":
      return leftText <= rightText;
    case ">=":
      return leftText >= rightText;
    default:
      return false;
  }
}

function parsePointValue(value: Db2Scalar): [number, number] | null {
  if (typeof value !== "string") {
    return null;
  }

  const match = value.match(/-?\d+(?:\.\d+)?/g);
  if (!match || match.length < 2) {
    return null;
  }

  const x = Number(match[0]);
  const y = Number(match[1]);

  if (Number.isNaN(x) || Number.isNaN(y)) {
    return null;
  }

  return [x, y];
}

function distance(a: [number, number], b: [number, number]): number {
  return Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2);
}

function matchesWhere(row: Db2Row, where: Db2WhereCondition): boolean {
  const rowValue = row[where.field];

  if (where.type === "Comparison") {
    return compareScalar(rowValue, where.op, where.value);
  }

  if (where.type === "Between") {
    const numericValue = toNumber(rowValue);
    return numericValue !== null && numericValue >= where.min && numericValue <= where.max;
  }

  const point = parsePointValue(rowValue);
  if (!point) {
    return false;
  }

  const targetDistance = distance(point, where.point);

  if (typeof where.radius === "number") {
    return targetDistance <= where.radius;
  }

  if (typeof where.k === "number") {
    return targetDistance <= Math.max(1, where.k * 1000);
  }

  return true;
}

function projectRow(row: Db2Row, columns: "*" | string[]): Db2Row {
  if (columns === "*") {
    return { ...row };
  }

  return columns.reduce<Db2Row>((accumulator, columnName) => {
    accumulator[columnName] = row[columnName] ?? null;
    return accumulator;
  }, {});
}

function executeStatement(statement: Db2Statement, catalog: Db2Table[]): {
  result: Db2StatementExecutionResult;
  catalog: Db2Table[];
} {
  if (statement.type === "Select") {
    const table = catalog.find((currentTable) => currentTable.name === statement.table);

    if (!table) {
      return {
        catalog,
        result: {
          statement,
          message: `Table ${statement.table} does not exist.`,
          rows: [],
          affectedRows: 0,
        },
      };
    }

    const rows = table.rows.filter((row) => (statement.where ? matchesWhere(row, statement.where) : true));
    const projectedRows = rows.map((row) => projectRow(row, statement.columns));

    return {
      catalog,
      result: {
        statement,
        message: `Returned ${projectedRows.length} row${projectedRows.length === 1 ? "" : "s"} from ${table.name}.`,
        rows: projectedRows,
        affectedRows: projectedRows.length,
      },
    };
  }

  if (statement.type === "CreateTable") {
    if (catalog.some((currentTable) => currentTable.name === statement.table)) {
      return {
        catalog,
        result: {
          statement,
          message: `Table ${statement.table} already exists.`,
          rows: [],
          affectedRows: 0,
        },
      };
    }

    const newTable: Db2Table = {
      name: statement.table,
      description: statement.fromFile ? `Created from ${statement.fromFile}.` : "Created by query.",
      columns: statement.columns.map((column) => ({ ...column, nullable: true })) as Db2Column[],
      rows: [],
    };

    return {
      catalog: [newTable, ...catalog],
      result: {
        statement,
        message: `Created table ${statement.table}.`,
        rows: [],
        affectedRows: 0,
      },
    };
  }

  if (statement.type === "Insert") {
    const table = catalog.find((currentTable) => currentTable.name === statement.table);

    if (!table) {
      return {
        catalog,
        result: {
          statement,
          message: `Table ${statement.table} does not exist.`,
          rows: [],
          affectedRows: 0,
        },
      };
    }

    if (table.columns.length !== statement.values.length) {
      return {
        catalog,
        result: {
          statement,
          message: `Expected ${table.columns.length} values but received ${statement.values.length}.`,
          rows: [],
          affectedRows: 0,
        },
      };
    }

    const row = table.columns.reduce<Db2Row>((accumulator, column, index) => {
      accumulator[column.name] = statement.values[index] ?? null;
      return accumulator;
    }, {});

    table.rows = [...table.rows, row];

    return {
      catalog,
      result: {
        statement,
        message: `Inserted 1 row into ${table.name}.`,
        rows: [row],
        affectedRows: 1,
      },
    };
  }

  const table = catalog.find((currentTable) => currentTable.name === statement.table);

  if (!table) {
    return {
      catalog,
      result: {
        statement,
        message: `Table ${statement.table} does not exist.`,
        rows: [],
        affectedRows: 0,
      },
    };
  }

  const remainingRows = table.rows.filter((row) => !matchesWhere(row, statement.where));
  const deletedRows = table.rows.length - remainingRows.length;
  table.rows = remainingRows;

  return {
    catalog,
    result: {
      statement,
      message: `Deleted ${deletedRows} row${deletedRows === 1 ? "" : "s"} from ${table.name}.`,
      rows: [],
      affectedRows: deletedRows,
    },
  };
}

export function executeDb2Program(program: Db2Program, catalog: Db2Table[] = cloneCatalog(db2Catalog)): Db2ExecuteQueryResponse {
  const workingCatalog = cloneCatalog(catalog);
  const results: Db2StatementExecutionResult[] = [];

  for (const statement of program.statements) {
    const execution = executeStatement(statement, workingCatalog);
    workingCatalog.splice(0, workingCatalog.length, ...execution.catalog.map((table) => ({
      ...table,
      columns: table.columns.map((column) => ({ ...column })),
      rows: table.rows.map((row) => ({ ...row })),
    })));
    results.push(execution.result);
  }

  return {
    source: "mock",
    program,
    results,
    tables: workingCatalog,
  };
}