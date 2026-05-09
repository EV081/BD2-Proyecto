import type {
  Db2CsvDeleteResponse,
  Db2CsvFilesEndpointResponse,
  Db2CsvUploadResponse,
  Db2ExecuteQueryResponse,
  Db2QueryOutcome,
  Db2Row,
  Db2Table,
  Db2TablesEndpointResponse,
  Db2StatementExecutionResult,
} from "@src/types/db2";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  const payload = await response.json();

  if (!response.ok) {
    const message = typeof payload === "object" && payload && "detail" in payload
      ? String((payload as { detail?: { message?: string } }).detail?.message ?? "DB2 request failed.")
      : "DB2 request failed.";
    throw new Error(message);
  }

  return payload as T;
}

async function fetchCsvAction<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    cache: "no-store",
  });

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const message = typeof payload === "object" && payload && "detail" in payload
      ? String((payload as { detail?: { message?: string } }).detail?.message ?? "CSV request failed.")
      : "CSV request failed.";
    throw new Error(message);
  }

  return payload as T;
}

function normalizeCatalog(response: Db2TablesEndpointResponse): Db2Table[] {
  return response.tables.map((table) => ({
    name: table.name,
    description: table.description,
    columns: table.columns.map((column) => ({ ...column })),
    rows: table.rows ? table.rows.map((row) => ({ ...row })) : [],
    primaryKey: table.primaryKey ?? null,
    indexes: table.indexes ? table.indexes.map((index) => ({ ...index })) : undefined,
    pointColumns: table.pointColumns ? { ...table.pointColumns } : undefined,
    recordCount: table.recordCount,
  }));
}

function normalizeQueryRows(rows: unknown[], columns?: string[]): Db2Row[] {
  if (!rows.length) {
    return [];
  }

  if (!columns?.length) {
    return rows.filter((row): row is Db2Row => Boolean(row) && typeof row === "object" && !Array.isArray(row));
  }

  return rows.map((row) => {
    if (Array.isArray(row)) {
      return columns.reduce<Db2Row>((record, columnName, columnIndex) => {
        record[columnName] = row[columnIndex] ?? null;
        return record;
      }, {});
    }

    if (row && typeof row === "object") {
      return row as Db2Row;
    }

    return {};
  });
}

function normalizeQueryResponse(response: Db2ExecuteQueryResponse): Db2ExecuteQueryResponse {
  return {
    ...response,
    results: response.results.map((result): Db2StatementExecutionResult => ({
      ...result,
      rows: normalizeQueryRows(result.rows as unknown[], result.columns),
    })),
  };
}

export async function getInitialCatalog(): Promise<Db2Table[]> {
  const response = await fetchJson<Db2TablesEndpointResponse>("/api/tables");
  return normalizeCatalog(response);
}

export async function refreshDb2Catalog(): Promise<Db2Table[]> {
  return getInitialCatalog();
}

export async function getCsvFiles(): Promise<string[]> {
  const response = await fetchJson<Db2CsvFilesEndpointResponse>("/api/csv/files");
  return response.csv_files;
}

export async function uploadCsvFile(file: File): Promise<Db2CsvUploadResponse> {
  const formData = new FormData();
  formData.append("file", file, file.name);
  return fetchCsvAction<Db2CsvUploadResponse>("/api/csv/files", {
    method: "POST",
    body: formData,
  });
}

export async function deleteCsvFile(filename: string): Promise<Db2CsvDeleteResponse> {
  return fetchCsvAction<Db2CsvDeleteResponse>(`/api/csv/files/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  });
}

export async function runDb2Query(query: string): Promise<Db2QueryOutcome> {
  const response = normalizeQueryResponse(
    await fetchJson<Db2ExecuteQueryResponse>("/api/query", {
    method: "POST",
    body: JSON.stringify({ query }),
    }),
  );

  const catalog = await getInitialCatalog();

  return {
    catalog,
    response,
  };
}

export function resetDb2Catalog(): void {
  // The mock state was removed; the backend is now the source of truth.
}

