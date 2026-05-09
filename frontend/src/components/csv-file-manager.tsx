"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { deleteCsvFile, getCsvFiles, uploadCsvFile } from "@src/services/db2.service";

function isCsvFile(file: File): boolean {
  return file.name.toLowerCase().endsWith(".csv");
}

export function CsvFileManager() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dragDepthRef = useRef(0);
  const [csvFiles, setCsvFiles] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);

  useEffect(() => {
    void refreshFiles();
  }, []);

  async function refreshFiles(): Promise<boolean> {
    setIsLoading(true);
    setError(null);

    try {
      const files = await getCsvFiles();
      setCsvFiles(files);
      return true;
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Unable to load CSV files.");
      return false;
    } finally {
      setIsLoading(false);
    }
  }

  function clearFeedback() {
    setMessage(null);
    setError(null);
  }

  async function handleFiles(files: File[]) {
    const validFiles = files.filter(isCsvFile);
    const rejectedCount = files.length - validFiles.length;

    if (!validFiles.length) {
      setError("Solo se permiten archivos CSV.");
      return;
    }

    setIsUploading(true);
    clearFeedback();

    let uploadedCount = 0;
    const failures: string[] = [];

    for (const file of validFiles) {
      try {
        await uploadCsvFile(file);
        uploadedCount += 1;
      } catch (uploadError) {
        failures.push(`${file.name}: ${uploadError instanceof Error ? uploadError.message : "upload failed"}`);
      }
    }

    const refreshed = await refreshFiles();

    if (failures.length) {
      setError(failures.join(" | "));
    } else if (!refreshed) {
      setError("Files uploaded, but the list could not be refreshed.");
    } else {
      const rejectedText = rejectedCount > 0 ? ` ${rejectedCount} archivo(s) fueron rechazados.` : "";
      setMessage(`${uploadedCount} archivo(s) CSV cargado(s).${rejectedText}`);
    }

    setIsUploading(false);
  }

  async function handleDelete(filename: string) {
    const confirmed = window.confirm(`Delete ${filename}?`);
    if (!confirmed) {
      return;
    }

    setDeletingFile(filename);
    clearFeedback();

    try {
      await deleteCsvFile(filename);
      const refreshed = await refreshFiles();
      if (refreshed) {
        setMessage(`File '${filename}' deleted successfully.`);
      } else {
        setError("File deleted, but the list could not be refreshed.");
      }
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete file.");
    } finally {
      setDeletingFile(null);
    }
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files ?? []);
    event.target.value = "";
    void handleFiles(selectedFiles);
  }

  return (
    <section className="rounded-lg border border-(--border) bg-(--surface) p-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-(--muted)">File manager</p>
          <h2 className="mt-1 text-sm font-semibold text-foreground">CSV files</h2>
        </div>
        <button
          type="button"
          className="rounded-md border border-(--border) bg-(--surface-subtle) px-2.5 py-1 text-xs font-medium text-(--muted) transition hover:border-(--accent) hover:text-(--accent)"
          onClick={() => void refreshFiles()}
          disabled={isLoading}
        >
          Refresh
        </button>
      </div>

      <div
        role="button"
        tabIndex={0}
        className={`mt-3 rounded-xl border border-dashed px-3 py-4 text-center transition ${isDragging ? "border-blue-500 bg-blue-500/8" : "border-(--border) bg-(--surface-subtle)"}`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragEnter={(event) => {
          event.preventDefault();
          if (Array.from(event.dataTransfer.types).includes("Files")) {
            dragDepthRef.current += 1;
            setIsDragging(true);
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
          if (dragDepthRef.current === 0) {
            setIsDragging(false);
          }
        }}
        onDrop={(event) => {
          event.preventDefault();
          dragDepthRef.current = 0;
          setIsDragging(false);
          void handleFiles(Array.from(event.dataTransfer.files));
        }}
      >
        <input
          ref={inputRef}
          type="file"
          className="sr-only"
          accept=".csv,text/csv"
          multiple
          onChange={handleInputChange}
        />
        <p className="text-sm font-medium text-foreground">Drag and drop CSV files here</p>
        <p className="mt-1 text-xs text-(--muted)">Only .csv files are accepted. Click to browse.</p>
        <button
          type="button"
          className="mt-3 inline-flex items-center justify-center rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-700"
          onClick={(event) => {
            event.stopPropagation();
            inputRef.current?.click();
          }}
        >
          Select CSV
        </button>
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-(--muted)">
        <span>{isUploading ? "Uploading..." : `${csvFiles.length} file(s) available`}</span>
        <span>{csvFiles.length ? "Ready" : "No CSV files yet"}</span>
      </div>

      {message || error ? (
        <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${error ? "border-rose-500/20 bg-rose-500/10 text-rose-500" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-500"}`}>
          {error ?? message}
        </div>
      ) : null}

      <div className="mt-3 space-y-2">
        {isLoading ? (
          <div className="rounded-lg border border-(--border) bg-(--surface-subtle) px-3 py-3 text-sm text-(--muted)">Loading files...</div>
        ) : csvFiles.length ? (
          csvFiles.map((filename) => (
            <div key={filename} className="flex items-center justify-between gap-3 rounded-lg border border-(--border) bg-(--surface-subtle) px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{filename}</p>
                <p className="text-[11px] text-(--muted)">CSV document</p>
              </div>
              <button
                type="button"
                className="rounded-md border border-rose-500/20 bg-rose-500/10 px-2.5 py-1 text-xs font-medium text-rose-500 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void handleDelete(filename)}
                disabled={deletingFile === filename || isUploading}
              >
                {deletingFile === filename ? "Deleting..." : "Delete"}
              </button>
            </div>
          ))
        ) : (
          <div className="rounded-lg border border-(--border) bg-(--surface-subtle) px-3 py-3 text-sm text-(--muted)">
            No CSV files uploaded yet.
          </div>
        )}
      </div>
    </section>
  );
}