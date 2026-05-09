import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { deleteLocalCsvFile } from "@src/lib/db2/csv-storage";

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

export async function DELETE(request: NextRequest, context: { params: Promise<{ filename: string }> }) {
  const { filename } = await context.params;
  const remoteUrl = getRemoteApiUrl(request.url, `/csv/data/${encodeURIComponent(filename)}`);

  if (remoteUrl) {
    const response = await fetch(remoteUrl, {
      method: "DELETE",
      cache: "no-store",
    });

    if (!response.ok) {
      return proxyError(response, "FileDeletionError", "Error deleting file.");
    }

    return NextResponse.json(await response.json());
  }

  try {
    await deleteLocalCsvFile(filename);
    return NextResponse.json({ message: `File '${filename}' deleted successfully.` });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Error deleting file.";
    return apiError(500, "FileDeletionError", message);
  }
}