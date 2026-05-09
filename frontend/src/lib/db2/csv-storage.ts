import "server-only";

import { mkdir, readdir, unlink, writeFile } from "node:fs/promises";
import path from "node:path";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const CSV_UPLOAD_DIR = path.join(PROJECT_ROOT, "uploaded_files");

export function isCsvFilename(filename: string): boolean {
  return filename.toLowerCase().endsWith(".csv");
}

export function sanitizeCsvFilename(filename: string): string {
  return path.basename(filename).replace(/[\\/]/g, "_");
}

export async function listLocalCsvFiles(): Promise<string[]> {
  try {
    const entries = await readdir(CSV_UPLOAD_DIR, { withFileTypes: true });
    return entries
      .filter((entry) => entry.isFile() && isCsvFilename(entry.name))
      .map((entry) => entry.name)
      .sort((left, right) => left.localeCompare(right));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }

    throw error;
  }
}

export async function saveLocalCsvFile(filename: string, file: File): Promise<string> {
  const safeFilename = sanitizeCsvFilename(filename);

  if (!isCsvFilename(safeFilename)) {
    throw new Error("Filename must end with .csv");
  }

  await mkdir(CSV_UPLOAD_DIR, { recursive: true });
  const buffer = Buffer.from(await file.arrayBuffer());
  await writeFile(path.join(CSV_UPLOAD_DIR, safeFilename), buffer);
  return safeFilename;
}

export async function deleteLocalCsvFile(filename: string): Promise<void> {
  const safeFilename = sanitizeCsvFilename(filename);

  if (!isCsvFilename(safeFilename)) {
    throw new Error("Filename must end with .csv");
  }

  await unlink(path.join(CSV_UPLOAD_DIR, safeFilename));
}