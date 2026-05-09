import "server-only";

import { db2Catalog } from "@src/lib/db2/catalog";
import { executeDb2Program } from "@src/lib/db2/executor";
import { parseDb2Program } from "@src/lib/db2/parser";
import type {
  Db2Column,
  Db2ExecuteQueryResponse,
  Db2Program,
  Db2Row,
  Db2Scalar,
  Db2Statement,
  Db2StatementExecutionResult,
  Db2Table,
  Db2TablesEndpointResponse,
  Db2WhereCondition,
} from "@src/types/db2";

type ApiError = {
  status: number;
  detail: {
    type: string;
    message: string;
    phase?: "scan" | "parse" | "execution";
  };
};

type RemoteTablesResponse = {
  tables: Array<{
    name: string;
    description?: string;
    columns: Record<string, string>;
    primary_key?: string | null;
    indexes?: Array<{ column: string; type: string; unique: boolean }>;
    point_columns?: Record<string, [string, string]>;
    record_count?: number;
    rows?: Db2Row[];
  }>;
};

type RemoteQueryResponse = {
  success: true;
  ast: Array<Record<string, unknown>>;
  results: Array<{
    statement: Record<string, unknown>;
    type: string;
    columns?: string[];
    rows?: Array<Array<Db2Scalar>>;
    affected_rows?: number;
    rid?: number | number[];
    status?: string;
    table?: string;
    result?: unknown;
    message?: string;
    is_spatial?: boolean;
    spatial_data?: unknown;
    metrics?: {
      time_ms: number;
      heap_reads: number;
      heap_writes: number;
      index_reads: number;
      index_writes: number;
      total_reads: number;
      total_writes: number;
    };
  }>;
};

let localCatalog: Db2Table[] = cloneCatalog(db2Catalog);

function cloneCatalog(catalog: Db2Table[]): Db2Table[] {
  return catalog.map((table) => ({
    ...table,
    columns: table.columns.map((column) => ({ ...column })),
    rows: table.rows.map((row) => ({ ...row })),
  }));
}

function getApiUrl(pathname: string): string | null {
  const baseUrl = process.env.API_URL;
  return baseUrl ? new URL(pathname, baseUrl).toString() : null;
}

function shouldUseRemoteBackend(requestUrl: string): boolean {
  const apiUrl = process.env.API_URL;

  if (!apiUrl) {
    return false;
  }

  try {
    return new URL(apiUrl).origin !== new URL(requestUrl).origin;
  } catch {
    return true;
  }
}

function makeApiError(status: number, type: string, message: string, phase?: "scan" | "parse" | "execution"): ApiError {
  return { status, detail: { type, message, phase } };
}

async function parseErrorResponse(response: Response): Promise<ApiError | null> {
  try {
    const payload = (await response.json()) as { detail?: { type?: string; message?: string; phase?: "scan" | "parse" | "execution" } };
    if (typeof payload.detail?.type !== "string" || typeof payload.detail?.message !== "string") {
      return null;
    }

    return {
      status: response.status,
      detail: {
        type: payload.detail.type,
        message: payload.detail.message,
        phase: payload.detail.phase,
      },
    };
  } catch {
    return null;
  }
}

function resultColumns(statement: Db2Statement, tables: Db2Table[]): string[] {
  if (statement.type !== "Select") {
    return [];
  }

  if (statement.columns === "*") {
    return tables.find((table) => table.name === statement.table)?.columns.map((column) => column.name) ?? [];
  }

  return statement.columns;
}

function rowsToObjects(rows: Array<Array<Db2Scalar>> | Db2Row[], columns: string[]): Db2Row[] {
  if (!rows.length) {
    return [];
  }

  if (typeof rows[0] === "object" && !Array.isArray(rows[0])) {
    return rows as Db2Row[];
  }

  return (rows as Array<Array<Db2Scalar>>).map((row) => {
    const record: Db2Row = {};
    columns.forEach((column, index) => {
      record[column] = row[index] ?? null;
    });
    return record;
  });
}

function mapExecutionResult(result: Db2StatementExecutionResult): Db2StatementExecutionResult {
  const columns = result.statement.type === "Select" ? resultColumns(result.statement, localCatalog) : undefined;

  return {
    statement: result.statement,
    message: result.message,
    columns,
    rows: result.rows,
    affectedRows: result.affectedRows,
  };
}

function normalizeLocalQuery(query: string): Db2ExecuteQueryResponse {
  const program = parseDb2Program(query);

  if (program.errors.length) {
    throw makeApiError(400, "ParserError", program.errors[0].message, "parse");
  }

  const execution = executeDb2Program(program, localCatalog);
  localCatalog = execution.tables;

  return {
    source: "local",
    program,
    results: execution.results.map(mapExecutionResult),
    tables: cloneCatalog(execution.tables),
  };
}

function normalizeRemoteTables(response: RemoteTablesResponse): Db2TablesEndpointResponse {
  return {
    source: "api",
    tables: response.tables.map((table) => ({
      name: table.name,
      description: table.description ?? `Table ${table.name}`,
      primaryKey: table.primary_key ?? null,
      indexes: table.indexes?.map((index) => ({
        ...index,
        column: index.column,
      })),
      pointColumns: table.point_columns,
      recordCount: table.record_count,
      columns: Object.entries(table.columns).map(([name, type]) => ({
        name,
        type: type as Db2Column["type"],
        index: (table.indexes?.find((index) => index.column === name)?.type ?? "DEFAULT_INDEX") as Db2Column["index"],
        nullable: true,
      })),
      rows: table.rows ?? [],
    })),
  };
}

function normalizeRemoteQuery(response: RemoteQueryResponse): Db2ExecuteQueryResponse {
  const program: Db2Program = parseDb2Program("");
  const tables = cloneCatalog(localCatalog);

  return {
    source: "api",
    program,
    results: response.results.map((result) => {
      const statementType = String(result.statement.type ?? "").toLowerCase();
      const statement: Db2Statement =
        statementType === "select"
          ? {
              type: "Select",
              table: String(result.statement.table ?? ""),
              columns: Array.isArray(result.statement.columns) ? (result.statement.columns as string[]) : "*",
              where: null,
            }
          : statementType === "create_table"
            ? {
                type: "CreateTable",
                table: String(result.statement.name ?? result.statement.table ?? ""),
                columns: Array.isArray(result.statement.columns)
                  ? (result.statement.columns as Array<{ name: string; type: Db2Column["type"]; index: Db2Column["index"] }>)
                  : [],
                fromFile: typeof result.statement.file_path === "string" ? result.statement.file_path : null,
              }
            : statementType === "insert"
              ? {
                  type: "Insert",
                  table: String(result.statement.table ?? ""),
                  values: Array.isArray(result.statement.values) ? (result.statement.values as Db2Scalar[]) : [],
                }
              : {
                  type: "Delete",
                  table: String(result.statement.table ?? ""),
                  where: { type: "Comparison", field: "", op: "=", value: null } as Db2WhereCondition,
                };

      const columns = result.columns ?? resultColumns(statement, tables);
      const rows = rowsToObjects(result.rows ?? [], columns);

      return {
        statement,
        type: result.type ?? statementType,
        message: result.message ?? result.status ?? "Query executed.",
        columns: result.columns ?? (statement.type === "Select" ? columns : undefined),
        rows,
        affectedRows: typeof result.affected_rows === "number" ? result.affected_rows : rows.length,
        isSpatial: result.is_spatial,
        spatialData: result.spatial_data,
        rid: result.rid,
        status: result.status,
        result: result.result,
        metrics: result.metrics,
      };
    }),
    tables,
  };
}

export async function fetchTables(requestUrl: string): Promise<Db2TablesEndpointResponse> {
  if (!shouldUseRemoteBackend(requestUrl)) {
    return { source: "local", tables: cloneCatalog(localCatalog) };
  }

  const apiUrl = getApiUrl("/tables");
  if (!apiUrl) {
    return { source: "local", tables: cloneCatalog(localCatalog) };
  }

  const response = await fetch(apiUrl, { cache: "no-store" });

  if (!response.ok) {
    const apiError = await parseErrorResponse(response);
    if (apiError) {
      throw apiError;
    }

    throw makeApiError(response.status, "TablesFetchError", "Unable to fetch tables.");
  }

  return normalizeRemoteTables((await response.json()) as RemoteTablesResponse);
}

export async function runQuery(requestUrl: string, query: string): Promise<Db2ExecuteQueryResponse> {
  if (!shouldUseRemoteBackend(requestUrl)) {
    return normalizeLocalQuery(query);
  }

  const apiUrl = getApiUrl("/query");
  if (!apiUrl) {
    return normalizeLocalQuery(query);
  }

  const response = await fetch(apiUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
    cache: "no-store",
  });

  if (!response.ok) {
    const apiError = await parseErrorResponse(response);
    if (apiError) {
      throw apiError;
    }

    throw makeApiError(response.status, "QueryError", "Unable to execute query.", "execution");
  }

  return normalizeRemoteQuery((await response.json()) as RemoteQueryResponse);
}

export function resetLocalCatalog(): void {
  localCatalog = cloneCatalog(db2Catalog);
}
