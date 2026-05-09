"use client";

import Editor, { type BeforeMount, type OnMount } from "@monaco-editor/react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import type * as MonacoEditor from "monaco-editor";

const SpatialMap = dynamic(
  () => import("@src/components/spatial-map"),
  {
    ssr: false,
    loading: () => (
      <div className="h-[420px] w-full animate-pulse rounded-lg border border-slate-200 bg-slate-50 flex items-center justify-center text-slate-400">
        Loading map...
      </div>
    ),
  }
);
import type { SpatialQueryContext } from "@src/components/spatial-map";
import { CsvFileManager } from "@src/components/csv-file-manager";

import { parseDb2Program } from "@src/lib/db2/grammar";
import {
  DB2_DATA_TYPES,
  DB2_INDEX_TYPES,
  DB2_KEYWORDS,
  DB2_LANGUAGE_SNIPPETS,
  DB2_OPERATORS,
} from "@src/lib/db2/language";
import { refreshDb2Catalog, runDb2Query } from "@src/services/db2.service";
import type { Db2ExecuteQueryResponse, Db2Program, Db2Row, Db2Statement, Db2Table, Db2WhereCondition } from "@src/types/db2";

const DEFAULT_QUERY = "SELECT * FROM users WHERE age BETWEEN 30 AND 42;";
const LANGUAGE_ID = "db2";
const THEME_ID = "db2-light";
const DARK_THEME_ID = "db2-dark";

let db2LanguageConfigured = false;
let db2CompletionCatalog: Db2Table[] = [];

function setDb2CompletionCatalog(catalog: Db2Table[]) {
  db2CompletionCatalog = catalog;
}

function getDb2CompletionTables() {
  return db2CompletionCatalog.map((table) => table.name);
}

function getDb2CompletionColumns() {
  return Array.from(
    new Set(db2CompletionCatalog.flatMap((table) => table.columns.map((column) => column.name))),
  );
}

function configureDb2Language(monaco: Parameters<BeforeMount>[0]) {
  if (db2LanguageConfigured) {
    return;
  }

  monaco.languages.register({ id: LANGUAGE_ID });
  monaco.languages.setLanguageConfiguration(LANGUAGE_ID, {
    brackets: [
      ["(", ")"],
      ["[", "]"],
    ],
    autoClosingPairs: [
      { open: "(", close: ")" },
      { open: "[", close: "]" },
      { open: '"', close: '"' },
      { open: "'", close: "'" },
    ],
  });
  monaco.languages.setMonarchTokensProvider(LANGUAGE_ID, {
    tokenizer: {
      root: [
        [/[;,.]/, "delimiter"],
        [/\(|\)/, "delimiter.parenthesis"],
        [/\b(?:INT|FLOAT|VARCHAR|POINT)\b/i, "type"],
        [/\b(?:CREATE|TABLE|SELECT|FROM|WHERE|INSERT|INTO|VALUES|DELETE|FILE|INDEX|SEQUENTIAL|HASH|BTREE|RTREE|BETWEEN|AND|IN|POINT|RADIUS|K|DEFAULT_INDEX|PRIMARY|KEY)\b/i, "keyword"],
        [/<=|>=|!=|=|<|>/, "operator"],
        [/\b\d+(?:\.\d+)?\b/, "number"],
        [/"([^"\\]|\\.)*"/, "string"],
        [/'([^'\\]|\\.)*'/, "string"],
        [/[a-zA-Z_][\w$]*/, "identifier"],
        [/--.*$/, "comment"],
        [/\s+/, "white"],
      ],
    },
  });

  monaco.languages.registerCompletionItemProvider(LANGUAGE_ID, {
    triggerCharacters: [" ", ".", "(", "=", ","],
    provideCompletionItems: (
      model: MonacoEditor.editor.ITextModel,
      position: MonacoEditor.Position,
    ) => {
      const linePrefix = model.getValueInRange({
        startLineNumber: position.lineNumber,
        startColumn: 1,
        endLineNumber: position.lineNumber,
        endColumn: position.column,
      });
      const word = model.getWordUntilPosition(position);
      const completionRange: MonacoEditor.IRange = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      };
      const completionKind = monaco.languages.CompletionItemKind;
      const insertRules = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;
      const keywordSuggestions: MonacoEditor.languages.CompletionItem[] = DB2_KEYWORDS.map((keyword) => ({
        label: keyword,
        kind: completionKind.Keyword,
        insertText: keyword,
        detail: "DB2 keyword",
        range: completionRange,
      }));

      const snippetSuggestions: MonacoEditor.languages.CompletionItem[] = DB2_LANGUAGE_SNIPPETS.map((snippet) => ({
        label: snippet.label,
        kind: completionKind.Snippet,
        insertText: snippet.insertText,
        insertTextRules: insertRules,
        detail: snippet.detail,
        range: completionRange,
      }));

      const tableSuggestions: MonacoEditor.languages.CompletionItem[] = getDb2CompletionTables().map((tableName) => ({
        label: tableName,
        kind: completionKind.Class,
        insertText: tableName,
        detail: "Table name",
        range: completionRange,
      }));

      const columnSuggestions: MonacoEditor.languages.CompletionItem[] = getDb2CompletionColumns().map((columnName) => ({
        label: columnName,
        kind: completionKind.Field,
        insertText: columnName,
        detail: "Column name",
        range: completionRange,
      }));

      const typeSuggestions: MonacoEditor.languages.CompletionItem[] = DB2_DATA_TYPES.map((dataType) => ({
        label: dataType,
        kind: completionKind.TypeParameter,
        insertText: dataType,
        detail: "DB2 data type",
        range: completionRange,
      }));

      const indexSuggestions: MonacoEditor.languages.CompletionItem[] = DB2_INDEX_TYPES.map((indexType) => ({
        label: indexType,
        kind: completionKind.EnumMember,
        insertText: indexType,
        detail: "Index type",
        range: completionRange,
      }));

      const operatorSuggestions: MonacoEditor.languages.CompletionItem[] = DB2_OPERATORS.map((operator) => ({
        label: operator,
        kind: completionKind.Operator,
        insertText: operator,
        detail: "Comparison operator",
        range: completionRange,
      }));

      const fileSnippet: MonacoEditor.languages.CompletionItem = {
        label: 'FROM FILE "path"',
        kind: completionKind.Snippet,
        insertText: 'FROM FILE "${1:path}"',
        insertTextRules: insertRules,
        detail: "Load rows from a file",
        range: completionRange,
      };

      let suggestions: MonacoEditor.languages.CompletionItem[] = [...snippetSuggestions, ...keywordSuggestions];

      if (/\b(?:FROM|INTO|TABLE)\s+[\w$]*$/i.test(linePrefix)) {
        suggestions = [...tableSuggestions, ...suggestions];
      } else if (/\bWHERE\s+[\w$]*$/i.test(linePrefix) || /\bAND\s+[\w$]*$/i.test(linePrefix)) {
        suggestions = [...columnSuggestions, ...operatorSuggestions, ...suggestions];
      } else if (/\bINDEX\s+[\w$]*$/i.test(linePrefix) || /\bINDEX\s*$/i.test(linePrefix)) {
        suggestions = [...indexSuggestions, ...suggestions];
      } else if (/\bFILE\s*["']?[^"']*$/i.test(linePrefix)) {
        suggestions = [fileSnippet, ...suggestions];
      } else if (/\bCREATE\s+TABLE\s+[\w$]*$/i.test(linePrefix)) {
        suggestions = [...tableSuggestions, ...suggestions];
      } else if (/\b(?:CREATE\s+TABLE\s+\w+\s*\(|,\s*)[\w$]*$/i.test(linePrefix)) {
        suggestions = [...columnSuggestions, ...typeSuggestions, ...suggestions];
      } else if (/\bVALUES\s*\([^)]*$/i.test(linePrefix)) {
        suggestions = [...columnSuggestions, ...suggestions];
      } else if (/\bSELECT\s+[\w,\s]*$/i.test(linePrefix)) {
        suggestions = [...columnSuggestions, ...suggestions];
      }

      return {
        suggestions,
      };
    },
  });

  monaco.editor.defineTheme(THEME_ID, {
    base: "vs",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "1d4ed8", fontStyle: "bold" },
      { token: "type", foreground: "0e7490", fontStyle: "bold" },
      { token: "string", foreground: "0f766e" },
      { token: "number", foreground: "9333ea" },
      { token: "identifier", foreground: "111827" },
      { token: "operator", foreground: "475569" },
      { token: "delimiter", foreground: "64748b" },
      { token: "comment", foreground: "94a3b8", fontStyle: "italic" },
    ],
    colors: {
      "editor.background": "#f8fafc",
      "editor.foreground": "#0f172a",
      "editor.lineHighlightBackground": "#e2e8f0",
      "editorLineNumber.foreground": "#94a3b8",
      "editorLineNumber.activeForeground": "#334155",
      "editorIndentGuide.background": "#e2e8f0",
      "editorIndentGuide.activeBackground": "#cbd5e1",
      "editorWidget.background": "#ffffff",
      "editorWidget.border": "#cbd5e1",
    },
  });

  monaco.editor.defineTheme(DARK_THEME_ID, {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "79c0ff", fontStyle: "bold" },
      { token: "type", foreground: "56d364", fontStyle: "bold" },
      { token: "string", foreground: "a5d6ff" },
      { token: "number", foreground: "d2a8ff" },
      { token: "identifier", foreground: "e6edf3" },
      { token: "operator", foreground: "ff7b72" },
      { token: "delimiter", foreground: "8b949e" },
      { token: "comment", foreground: "6e7681", fontStyle: "italic" },
    ],
    colors: {
      "editor.background": "#0d1117",
      "editor.foreground": "#e6edf3",
      "editor.lineHighlightBackground": "#161b22",
      "editorLineNumber.foreground": "#6e7681",
      "editorLineNumber.activeForeground": "#c9d1d9",
      "editorIndentGuide.background": "#21262d",
      "editorIndentGuide.activeBackground": "#30363d",
      "editorWidget.background": "#161b22",
      "editorWidget.border": "#30363d",
    },
  });

  db2LanguageConfigured = true;
}

interface Db2PlaygroundProps {
  initialCatalog: Db2Table[];
}

export function Db2Playground({ initialCatalog }: Db2PlaygroundProps) {
  const [catalog, setCatalog] = useState<Db2Table[]>(initialCatalog);
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [selectedTableName, setSelectedTableName] = useState(initialCatalog[0]?.name ?? "");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [execution, setExecution] = useState<Db2ExecuteQueryResponse | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("db2-theme");
    const prefersDark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    setIsDark(prefersDark);
    document.documentElement.setAttribute("data-theme", prefersDark ? "dark" : "light");
  }, []);

  function toggleTheme() {
    setIsDark((prev) => {
      const next = !prev;
      document.documentElement.setAttribute("data-theme", next ? "dark" : "light");
      localStorage.setItem("db2-theme", next ? "dark" : "light");
      return next;
    });
  }

  const activeMonacoTheme = isDark ? DARK_THEME_ID : THEME_ID;

  const selectedTable = useMemo(() => catalog.find((table) => table.name === selectedTableName) ?? catalog[0] ?? null, [catalog, selectedTableName]);
  const liveParse = useMemo<Db2Program>(() => parseDb2Program(query), [query]);

  useEffect(() => {
    setDb2CompletionCatalog(catalog);
  }, [catalog]);

  const parseError = liveParse.errors[0] ?? null;
  const summaryStatement = liveParse.statements[0] ?? null;
  const latestResult = execution?.results[execution.results.length - 1] ?? null;

  function getStatementTableName(statement: Db2Statement): string {
    return statement.table;
  }

  const latestExecutionTable = latestResult
    ? execution?.tables.find((table) => table.name === getStatementTableName(latestResult.statement)) ?? null
    : null;

  function isWildcardColumns(columns?: string[] | null): boolean {
    return Array.isArray(columns) && columns.length === 1 && columns[0] === "*";
  }

  function getSpatialQueryContext(statement: Db2Statement | null): SpatialQueryContext | undefined {
    if (!statement || statement.type !== "Select" || !statement.where) return undefined;
    const where = statement.where as Db2WhereCondition;
    if (where.type !== "SpatialIn") return undefined;
    return {
      mode: where.radius != null ? "radius" : where.k != null ? "knn" : "unknown",
      center: where.point as [number, number],
      radius: where.radius,
      k: where.k,
    };
  }

  function getTableRecordCount(table: Db2Table | null | undefined): number {
    return table?.recordCount ?? table?.rows.length ?? 0;
  }

  function getTablePrimaryKey(table: Db2Table | null | undefined): string {
    return table?.primaryKey ?? "—";
  }

  function getTableIndexLabels(table: Db2Table | null | undefined): string[] {
    if (!table) {
      return [];
    }

    if (table.indexes?.length) {
      return table.indexes.map((index) =>
        typeof index.column === "string" ? `${index.column} · ${index.type}` : `${index.column.join(" / ")} · ${index.type}`,
      );
    }

    return table.columns
      .filter((column) => column.index !== "DEFAULT_INDEX")
      .map((column) => `${column.name} · ${column.index}`);
  }

  function getTablePointColumns(table: Db2Table | null | undefined): string[] {
    if (!table?.pointColumns) {
      return [];
    }

    return Object.keys(table.pointColumns);
  }

  function normalizeRowsForDisplay(rows: unknown[], columns: Db2Table["columns"]): Db2Row[] {
    if (!rows.length || !columns.length) {
      return [];
    }

    return rows.map((row) => {
      if (Array.isArray(row)) {
        return columns.reduce<Db2Row>((record, column, columnIndex) => {
          record[column.name] = row[columnIndex] ?? null;
          return record;
        }, {});
      }

      if (row && typeof row === "object") {
        const typedRow = row as Record<string, unknown>;
        const directMatch = columns.reduce<Db2Row>((record, column) => {
          record[column.name] = (typedRow[column.name] as Db2Row[string]) ?? null;
          return record;
        }, {});

        const hasAnyValue = columns.some((column) => directMatch[column.name] !== null);
        if (hasAnyValue) {
          return directMatch;
        }

        return columns.reduce<Db2Row>((record, column, columnIndex) => {
          const indexedValue = typedRow[String(columnIndex)];
          record[column.name] = (indexedValue as Db2Row[string]) ?? null;
          return record;
        }, {});
      }

      return columns.reduce<Db2Row>((record, column) => {
        record[column.name] = null;
        return record;
      }, {});
    });
  }

  async function handleRunQuery() {
    setIsRunning(true);
    setExecutionError(null);

    try {
      const outcome = await runDb2Query(query);
      setCatalog(outcome.catalog);
      setExecution(outcome.response);

      if (selectedTableName && !outcome.catalog.some((table: Db2Table) => table.name === selectedTableName)) {
        setSelectedTableName(outcome.catalog[0]?.name ?? "");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Query execution failed.";
      setExecutionError(message);
    } finally {
      setIsRunning(false);
    }
  }

  function handleClearEditor() {
    setQuery("");
    setExecution(null);
    setExecutionError(null);
  }

  async function handleRefreshTables() {
    const restoredCatalog = await refreshDb2Catalog();

    setCatalog(restoredCatalog);
    setSelectedTableName(restoredCatalog[0]?.name ?? "");
    setExecutionError(null);
    setExecution({
      source: "mock",
      program: { statements: [], errors: [] },
      results: [],
      tables: restoredCatalog,
    });
  }

  const resultColumns =
    isWildcardColumns(latestResult?.columns)
      ? latestExecutionTable?.columns ?? selectedTable?.columns ?? []
      : latestResult?.columns?.length
      ? latestResult.columns.map((column) => ({
          name: column,
          type: "VARCHAR" as const,
          index: "DEFAULT_INDEX" as const,
          nullable: true,
        })) as Db2Table["columns"]
      : latestExecutionTable?.columns ?? selectedTable?.columns ?? [];
  const resultRows = normalizeRowsForDisplay(latestResult?.rows ?? selectedTable?.rows ?? [], resultColumns);
  const displayedTable = latestExecutionTable ?? selectedTable;
  const displayedTableRecordCount = getTableRecordCount(displayedTable);
  const displayedTableIndexLabels = getTableIndexLabels(displayedTable);
  const displayedTablePointColumns = getTablePointColumns(displayedTable);

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside
        className={`db2-scrollbar flex shrink-0 flex-col border-r border-(--border) bg-(--surface-subtle) transition-[width] duration-200 ${sidebarCollapsed ? "w-16" : "w-72"}`}
      >
        <div className="flex items-center justify-between gap-3 border-b border-(--border) px-4 py-4">
          <div className={sidebarCollapsed ? "sr-only" : "block"}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-(--muted)">DB2 Playground</p>
            <h1 className="mt-1 text-sm font-semibold text-foreground">Tables</h1>
          </div>
          <button
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-(--border) bg-(--surface) text-(--muted) transition hover:border-(--border) hover:text-foreground"
            onClick={() => setSidebarCollapsed((value) => !value)}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {sidebarCollapsed ? "+" : "−"}
          </button>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-3">
          {catalog.map((table) => {
            const isSelected = table.name === selectedTableName;
            const tableRows = getTableRecordCount(table);

            return (
              <button
                key={table.name}
                type="button"
                onClick={() => setSelectedTableName(table.name)}
                className={`w-full rounded-lg border px-3 py-3 text-left transition ${isSelected ? "border-blue-200/40 bg-blue-600/10 shadow-sm" : "border-transparent bg-transparent hover:border-(--border) hover:bg-(--surface)"}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className={`truncate text-sm font-semibold ${isSelected ? "text-(--accent)" : "text-foreground"}`}>
                      {sidebarCollapsed ? table.name.slice(0, 2).toUpperCase() : table.name}
                    </p>
                    <p className={`mt-1 text-xs ${isSelected ? "text-(--accent)/80" : "text-(--muted)"}`}>
                      {sidebarCollapsed ? `${tableRows}` : table.description}
                    </p>
                  </div>
                  {!sidebarCollapsed ? (
                    <span className="rounded-full border border-(--border) bg-(--surface) px-2 py-0.5 text-[11px] font-medium text-(--muted)">
                      {tableRows} rows
                    </span>
                  ) : null}
                </div>

                {!sidebarCollapsed ? (
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-(--muted)">
                    <span className="rounded-full bg-(--surface) px-2 py-0.5 ring-1 ring-(--border)">
                      PK {getTablePrimaryKey(table)}
                    </span>
                    <span className="rounded-full bg-(--surface) px-2 py-0.5 ring-1 ring-(--border)">
                      {table.columns.length} cols
                    </span>
                    <span className="rounded-full bg-(--surface) px-2 py-0.5 ring-1 ring-(--border)">
                      {tableRows} rows
                    </span>
                  </div>
                ) : null}
              </button>
            );
          })}

          {!sidebarCollapsed ? <CsvFileManager /> : null}
        </div>
      </aside>

      <main className="db2-scrollbar flex min-w-0 flex-1 flex-col">
        <header className="border-b border-(--border) bg-(--surface)/90 px-4 py-3 backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-(--muted)">Query workspace</p>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-(--muted)">
                <span className="font-semibold text-foreground">{selectedTable?.name ?? "No table selected"}</span>
                <span className="h-1 w-1 rounded-full bg-(--border)" />
                <span>{catalog.length} tables loaded</span>
                <span className="h-1 w-1 rounded-full bg-(--border)" />
                <span>{isRunning ? "Running query..." : liveParse.errors.length ? `Parser errors: ${liveParse.errors.length}` : `Parsed ${liveParse.statements.length} statements`}</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <ActionButton variant="primary" onClick={handleRunQuery} disabled={isRunning}>
                Run query
              </ActionButton>
              <ActionButton variant="secondary" onClick={handleClearEditor}>
                Clear editor
              </ActionButton>
              <ActionButton variant="secondary" onClick={handleRefreshTables}>
                Refresh tables
              </ActionButton>
              <ThemeToggle isDark={isDark} onToggle={toggleTheme} />
            </div>
          </div>
        </header>

        <div className="grid flex-1 gap-4 p-4 xl:grid-cols-[minmax(0,1.6fr)_360px]">
          <section className="flex min-h-140 flex-col overflow-hidden rounded-xl border border-(--border) bg-(--surface) shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="flex items-center justify-between gap-3 border-b border-(--border) px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Editor</h2>
                <p className="mt-0.5 text-xs text-(--muted)">
                  Supports SELECT, CREATE TABLE, INSERT, and DELETE statements.
                </p>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${liveParse.errors.length ? "bg-rose-500/10 text-rose-500" : "bg-emerald-500/10 text-emerald-500"}`}>
                {liveParse.errors.length ? "Syntax error" : `${liveParse.statements.length} statement${liveParse.statements.length === 1 ? "" : "s"}`}
              </span>
            </div>

            <div className="flex-1 bg-(--surface-subtle)">
              <Editor
                beforeMount={configureDb2Language}
                onMount={((editor, monaco) => {
                  configureDb2Language(monaco);
                  monaco.editor.setTheme(activeMonacoTheme);
                  editor.focus();
                }) as OnMount}
                value={query}
                onChange={(value) => setQuery(value ?? "")}
                language={LANGUAGE_ID}
                theme={activeMonacoTheme}
                height="100%"
                options={{
                  automaticLayout: true,
                  minimap: { enabled: false },
                  fontFamily: "var(--font-geist-mono), monospace",
                  fontSize: 13,
                  lineHeight: 20,
                  scrollBeyondLastLine: false,
                  roundedSelection: false,
                  renderLineHighlight: "all",
                  wordWrap: "off",
                  padding: { top: 16, bottom: 16 },
                  lineNumbers: "on",
                  guides: {
                    indentation: true,
                  },
                }}
              />
            </div>

            <div className="grid gap-2 border-t border-(--border) px-4 py-3 text-xs text-(--muted) md:grid-cols-3">
              <Metric label="Statements" value={`${liveParse.statements.length} parsed`} />
              <Metric label="Errors" value={`${liveParse.errors.length} issue${liveParse.errors.length === 1 ? "" : "s"}`} />
              <Metric label="Mode" value={summaryStatement?.type ?? "Program"} />
            </div>
          </section>

          <aside className="flex min-h-140 flex-col gap-4">
            <section className="overflow-hidden rounded-xl border border-(--border) bg-(--surface) shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
              <div className="border-b border-(--border) px-4 py-3">
                <h2 className="text-sm font-semibold text-foreground">Table details</h2>
                <p className="mt-0.5 text-xs text-(--muted)">Schema and catalog metadata for the selected table.</p>
              </div>

              <div className="space-y-4 p-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-(--muted)">Schema</p>
                  <div className="mt-3 space-y-2">
                    {displayedTable?.columns.map((column) => (
                      <div
                        key={column.name}
                        className="flex items-center justify-between gap-3 rounded-lg border border-(--border) bg-(--surface-subtle) px-3 py-2"
                      >
                        <div>
                          <p className="text-sm font-medium text-foreground">{column.name}</p>
                          <p className="text-xs text-(--muted)">{column.type}</p>
                        </div>
                        <span className="rounded-full bg-(--surface) px-2 py-0.5 text-[11px] font-medium text-(--muted)">
                          {column.index}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-(--muted)">Catalog snapshot</p>
                  <div className="mt-3 space-y-3 rounded-lg border border-(--border) bg-(--surface-subtle) p-3">
                    <div className="grid gap-2 sm:grid-cols-2">
                      <InfoTile label="Records" value={`${displayedTableRecordCount}`} />
                      <InfoTile label="Primary key" value={getTablePrimaryKey(displayedTable)} />
                      <InfoTile label="Indexed columns" value={`${displayedTableIndexLabels.length}`} />
                      <InfoTile label="Point columns" value={`${displayedTablePointColumns.length}`} />
                    </div>

                    <div className="rounded-lg border border-(--border) bg-(--surface) px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-(--muted)">Indexed column map</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {displayedTableIndexLabels.length ? (
                          displayedTableIndexLabels.map((label) => (
                            <span key={label} className="rounded-full bg-(--surface-subtle) px-2.5 py-1 text-xs text-foreground">
                              {label}
                            </span>
                          ))
                        ) : (
                          <span className="text-sm text-(--muted)">No index metadata available yet.</span>
                        )}
                      </div>
                    </div>

                    <div className="rounded-lg border border-(--border) bg-(--surface) px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-(--muted)">Point columns</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {displayedTablePointColumns.length ? (
                          displayedTablePointColumns.map((columnName) => (
                            <span key={columnName} className="rounded-full bg-blue-500/10 px-2.5 py-1 text-xs text-(--accent)">
                              {columnName}
                            </span>
                          ))
                        ) : (
                          <span className="text-sm text-(--muted)">No point-indexed columns yet.</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </aside>
        </div>

        <section className="border-t border-(--border) bg-(--surface) px-4 py-4">
          <div className="overflow-hidden rounded-xl border border-(--border) bg-(--surface-subtle)">
            <div className="flex items-center justify-between gap-3 border-b border-(--border) px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Results</h2>
                <p className="mt-0.5 text-xs text-(--muted)">
                  Latest query output or a table preview when no query has been executed.
                </p>
              </div>
              <span
                className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${executionError ? "bg-rose-500/10 text-rose-500" : latestResult ? "bg-blue-500/10 text-blue-400" : "bg-(--surface-subtle) text-(--muted)"}`}
              >
                {executionError ?? latestResult?.message ?? "Waiting for execution"}
              </span>
            </div>

            {executionError ? (
              <div className="border-b border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-400">
                {executionError}
              </div>
            ) : null}

            <div className="overflow-x-auto">
              {latestResult?.isSpatial ? (
                <div className="px-4 py-6">
                  <div className="mb-4 flex items-center justify-between">
                    <p className="text-sm font-medium text-foreground">Spatial data view</p>
                  </div>
                  <div className="grid gap-4 lg:grid-cols-2">
                    <SpatialMap
                      data={latestResult.spatialData}
                      queryContext={getSpatialQueryContext(latestResult.statement)}
                    />
                    <pre className="db2-scrollbar max-h-[420px] overflow-y-auto rounded-lg border border-(--border) bg-(--surface-subtle) p-4 text-xs font-mono text-foreground">
                      {JSON.stringify(latestResult.spatialData, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : latestResult?.type === "create_table" ? (
                <div className="px-4 py-6 text-sm text-(--muted)">
                  Table <span className="font-semibold text-foreground">{latestResult.statement.table ?? "unknown"}</span> created successfully.
                </div>
              ) : latestResult?.type === "insert" || latestResult?.type === "delete" ? (
                <div className="px-4 py-6 text-sm text-(--muted)">
                  {latestResult.affectedRows} row{latestResult.affectedRows !== 1 ? "s" : ""} affected.
                  {latestResult.rid && (
                    <span className="mt-2 block text-xs text-(--muted)">
                      Record IDs: {Array.isArray(latestResult.rid) ? latestResult.rid.join(", ") : latestResult.rid}
                    </span>
                  )}
                </div>
              ) : latestResult?.result !== undefined ? (
                <div className="px-4 py-6 text-sm text-(--muted)">
                  Result: <span className="font-semibold text-foreground">{String(latestResult.result)}</span>
                </div>
              ) : (
                <TablePreview rows={resultRows} columns={resultColumns} />
              )}
            </div>

            {latestResult?.metrics ? (
              <div className="border-t border-(--border) bg-(--surface-subtle) px-4 py-4">
                <p className="text-xs uppercase tracking-[0.2em] text-(--muted)">Execution metrics</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-4">
                  <Metric label="Time" value={`${latestResult.metrics.time_ms.toFixed(3)} ms`} />
                  <Metric label="Heap (R/W)" value={`${latestResult.metrics.heap_reads} / ${latestResult.metrics.heap_writes}`} />
                  <Metric label="Index (R/W)" value={`${latestResult.metrics.index_reads} / ${latestResult.metrics.index_writes}`} />
                  <Metric label="Total (R/W)" value={`${latestResult.metrics.total_reads} / ${latestResult.metrics.total_writes}`} />
                </div>
              </div>
            ) : null}

            <div className="grid gap-4 border-t border-(--border) bg-(--surface) px-4 py-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-(--muted)">Parser status</p>
                <div className="mt-2 rounded-lg border border-(--border) bg-(--surface-subtle) px-3 py-3 text-sm text-foreground">
                  {parseError ? (
                    <>
                      <p className="font-medium text-rose-500">{parseError.message}</p>
                      <p className="mt-1 text-xs text-(--muted)">
                        Line {parseError.context.line}, column {parseError.context.column}.
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="font-medium text-foreground">{summaryStatement?.type ?? "Program parsed"}</p>
                      <p className="mt-1 text-xs text-(--muted)">{renderAstSummary(summaryStatement)}</p>
                    </>
                  )}
                </div>
              </div>

              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-(--muted)">Grammar notes</p>
                <ul className="mt-2 space-y-2 rounded-lg border border-(--border) bg-(--surface) px-3 py-3 text-xs text-(--muted)">
                  <li>
                    SELECT requires a WHERE clause, and supports <span className="font-mono text-foreground">*</span> or explicit column lists.
                  </li>
                  <li>WHERE supports comparisons, BETWEEN, and IN predicates for SELECT.</li>
                  <li>CREATE TABLE accepts PRIMARY KEY, column indexes, VARCHAR(n) lengths and optional FROM FILE source.</li>
                  <li>INSERT and DELETE update the in-memory catalog (DELETE restricted to comparisons).</li>
                </ul>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function renderAstSummary(statement: Db2Statement | null): string {
  if (!statement) {
    return "No statements parsed.";
  }

  if (statement.type === "Select") {
    const columnsText = statement.columns === "*" ? "*" : statement.columns.join(", ");
    return statement.where
      ? `SELECT ${columnsText} FROM ${statement.table} with ${statement.where.type.toLowerCase()} predicate.`
      : `SELECT ${columnsText} FROM ${statement.table} without a WHERE clause.`;
  }

  if (statement.type === "CreateTable") {
    return `CREATE TABLE ${statement.table} with ${statement.columns.length} column${statement.columns.length === 1 ? "" : "s"}.`;
  }

  if (statement.type === "Insert") {
    return `INSERT INTO ${statement.table} with ${statement.values.length} value${statement.values.length === 1 ? "" : "s"}.`;
  }

  return statement.where
    ? `DELETE FROM ${statement.table} with a WHERE clause.`
    : `DELETE FROM ${statement.table} without a WHERE clause.`;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-(--border) bg-(--surface) px-3 py-2">
      <p className="text-[11px] uppercase tracking-[0.18em] text-(--muted)">{label}</p>
      <p className="mt-1 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function ActionButton({
  children,
  onClick,
  disabled,
  variant,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  variant: "primary" | "secondary";
}) {
  const isPrimary = variant === "primary";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex h-9 items-center justify-center rounded-md border px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 ${
        isPrimary
          ? "border-blue-600 bg-blue-600 text-white hover:bg-blue-700"
          : "border-(--border) bg-(--surface) text-(--muted) hover:border-(--border) hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-(--border) bg-(--surface) px-3 py-2">
      <p className="text-[11px] uppercase tracking-[0.18em] text-(--muted)">{label}</p>
      <p className="mt-1 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function TablePreview({
  rows,
  columns,
}: {
  rows: Db2Row[];
  columns: Db2Table["columns"];
}) {
  if (!columns.length) {
    return <div className="px-4 py-6 text-sm text-slate-500">No columns available.</div>;
  }

  return (
    <table className="w-full border-collapse text-left text-sm">
      <thead className="bg-(--surface-subtle) text-xs uppercase tracking-[0.18em] text-(--muted)">
        <tr>
          {columns.map((column) => (
            <th key={column.name} className="border-b border-(--border) px-3 py-2 font-medium">
              {column.name}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="bg-(--surface)">
        {rows.length ? (
          rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="odd:bg-(--surface) even:bg-(--surface-subtle)">
              {columns.map((column) => (
                <td key={column.name} className="border-b border-(--border) px-3 py-2 font-mono text-[12px] text-foreground">
                  {formatCell(row[column.name])}
                </td>
              ))}
            </tr>
          ))
        ) : (
          <tr>
            <td colSpan={columns.length} className="px-3 py-6 text-sm text-(--muted)">
              No rows to display.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function ThemeToggle({ isDark, onToggle }: { isDark: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      id="theme-toggle"
      onClick={onToggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-(--border) bg-(--surface) text-(--muted) transition-all duration-200 hover:border-(--accent) hover:text-(--accent)"
      style={{ position: "relative", overflow: "hidden" }}
    >
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "opacity 0.3s ease, transform 0.4s ease",
          opacity: isDark ? 0 : 1,
          transform: isDark ? "rotate(-90deg) scale(0.5)" : "rotate(0deg) scale(1)",
          position: "absolute",
        }}
        aria-hidden="true"
      >
        {/* Sun icon */}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
        </svg>
      </span>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "opacity 0.3s ease, transform 0.4s ease",
          opacity: isDark ? 1 : 0,
          transform: isDark ? "rotate(0deg) scale(1)" : "rotate(90deg) scale(0.5)",
          position: "absolute",
        }}
        aria-hidden="true"
      >
        {/* Moon icon */}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </span>
    </button>
  );
}

function formatCell(value: Db2Row[string]) {
  if (value === null) {
    return "NULL";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}