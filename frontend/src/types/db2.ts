export type Db2Scalar = string | number | boolean | null;

export type Db2IndexType = "DEFAULT_INDEX" | "SEQUENTIAL" | "HASH" | "BTREE" | "RTREE";

export type Db2DataType = "INT" | "FLOAT" | "VARCHAR" | "POINT";

export interface Db2Column {
  name: string;
  type: Db2DataType;
  length?: number;
  index: Db2IndexType;
  nullable?: boolean;
}

export interface Db2Row {
  [key: string]: Db2Scalar;
}

export interface Db2Table {
  name: string;
  description: string;
  columns: Db2Column[];
  rows: Db2Row[];
  primaryKey?: string | null;
  indexes?: Array<{
    column: string | [string, string];
    type: string;
    unique: boolean;
  }>;
  pointColumns?: Record<string, [string, string]>;
  recordCount?: number;
}

export type Db2ComparisonOperator = "=" | "<" | ">" | "<=" | ">=" | "!=";

export interface Db2ParseContext {
  line: number;
  column: number;
}

export interface Db2ParseError {
  error: true;
  type: "SyntaxError";
  message: string;
  context: Db2ParseContext;
}

export type Db2WhereCondition =
  | {
      type: "Comparison";
      field: string;
      op: Db2ComparisonOperator;
      value: Db2Scalar;
    }
  | {
      type: "Between";
      field: string;
      min: number;
      max: number;
    }
  | {
      type: "SpatialIn";
      field: string;
      point: [number, number];
      radius?: number;
      k?: number;
    };

export type Db2Statement =
  | {
      type: "Select";
      columns: "*" | string[];
      table: string;
      where: Db2WhereCondition | null;
    }
  | {
      type: "CreateTable";
      table: string;
      columns: Array<{
        name: string;
        type: Db2DataType;
        length?: number;
        index: Db2IndexType;
        primaryKey?: boolean;
      }>;
      fromFile: string | null;
    }
  | {
      type: "Insert";
      table: string;
      values: Db2Scalar[];
    }
  | {
      type: "Delete";
      table: string;
      where: Db2WhereCondition;
    };

export interface Db2Program {
  statements: Db2Statement[];
  errors: Db2ParseError[];
}

export interface Db2Token {
  kind: "Id" | "Number" | "String" | "EOF" | "ERROR" | "Keyword" | "Operator" | "Symbol";
  lexeme: string;
  value: string;
  line: number;
  column: number;
}

export type Db2ParseResult = Db2Program;

export interface Db2Metrics {
  time_ms: number;
  heap_reads: number;
  heap_writes: number;
  index_reads: number;
  index_writes: number;
  total_reads: number;
  total_writes: number;
}

export interface Db2StatementExecutionResult {
  statement: Db2Statement;
  type?: string;
  message: string;
  columns?: string[];
  rows: Db2Row[];
  affectedRows: number;
  isSpatial?: boolean;
  spatialData?: unknown;
  rid?: number | number[];
  status?: string;
  result?: unknown;
  metrics?: Db2Metrics;
}

export interface Db2TablesEndpointResponse {
  source: "mock" | "api" | "local";
  tables: Db2Table[];
}

export interface Db2CsvFilesEndpointResponse {
  csv_files: string[];
}

export interface Db2CsvUploadResponse {
  message: string;
  filename: string;
}

export interface Db2CsvDeleteResponse {
  message: string;
}

export interface Db2ExecuteQueryRequest {
  query: string;
}

export interface Db2ExecuteQueryResponse {
  source: "mock" | "api" | "local";
  program: Db2Program;
  results: Db2StatementExecutionResult[];
  tables: Db2Table[];
}

export interface Db2QueryOutcome {
  catalog: Db2Table[];
  response: Db2ExecuteQueryResponse;
}