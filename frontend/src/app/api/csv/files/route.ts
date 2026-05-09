import { NextResponse } from "next/server";

import { deleteLocalCsvFile, listLocalCsvFiles, saveLocalCsvFile } from "@src/lib/db2/csv-storage";

function getRemoteApiUrl(requestUrl: string, pathname: string): string | null {
  const apiUrl = process.env.API_URL;

  if (!apiUrl) {
    return null;
  }

  try {
    const requestOrigin = new URL(requestUrl).origin;
    const apiOrigin = new URL(apiUrl).origin;
    if (requestOrigin === apiOrigin) {
      return null;
    }

    return new URL(pathname, apiUrl).toString();
  } catch {
    return new URL(pathname, apiUrl).toString();
  }
}

function apiError(status: number, type: string, message: string) {
  return NextResponse.json({ detail: { type, message } }, { status });
}

async function proxyError(response: Response, fallbackType: string, fallbackMessage: string) {
  try {
    const payload = (await response.json()) as { detail?: { type?: string; message?: string } };
    const type = payload.detail?.type ?? fallbackType;
    const message = payload.detail?.message ?? fallbackMessage;
    return apiError(response.status, type, message);
  } catch {
    return apiError(response.status, fallbackType, fallbackMessage);
  }
}

export async function GET(request: Request) {
  const remoteUrl = getRemoteApiUrl(request.url, "/csv/data");

  if (remoteUrl) {
    const response = await fetch(remoteUrl, { cache: "no-store" });
    if (!response.ok) {
      return proxyError(response, "CsvListError", "Unable to list CSV files.");
    }

    return NextResponse.json(await response.json());
  }

  const csvFiles = await listLocalCsvFiles();
  return NextResponse.json({ csv_files: csvFiles });
}

export async function POST(request: Request) {
  const formData = await request.formData();
  const file = formData.get("file");

  if (!(file instanceof File)) {
    return apiError(400, "InvalidFile", "A CSV file is required.");
  }

  const filename = file.name || "unnamed.csv";
  if (!filename.toLowerCase().endsWith(".csv")) {
    return apiError(400, "InvalidFileName", "Filename must end with .csv");
  }

  const remoteUrl = getRemoteApiUrl(request.url, "/csv/data");

  if (remoteUrl) {
    const proxyForm = new FormData();
    proxyForm.append("file", file, filename);
    const response = await fetch(remoteUrl, {
      method: "POST",
      body: proxyForm,
      cache: "no-store",
    });

    if (!response.ok) {
      return proxyError(response, "FileUploadError", "Error uploading file.");
    }

    return NextResponse.json(await response.json());
  }

  try {
    const safeFilename = await saveLocalCsvFile(filename, file);
    return NextResponse.json({ message: `File '${safeFilename}' uploaded successfully.`, filename: safeFilename });
  } catch (error) {
    return apiError(500, "FileUploadError", error instanceof Error ? error.message : "Error saving file.");
  }
}
