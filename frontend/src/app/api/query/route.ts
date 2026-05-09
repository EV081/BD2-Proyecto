import { NextResponse } from "next/server";

import { runQuery } from "@src/lib/db2/backend";

type ApiError = {
  status: number;
  detail: {
    type: string;
    message: string;
    phase?: "scan" | "parse" | "execution";
  };
};

export async function GET() {
  return NextResponse.json({ message: "Query received" });
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as { query?: string };
    const response = await runQuery(request.url, body.query ?? "");
    return NextResponse.json(response);
  } catch (error) {
    const payload = error as Partial<ApiError> | undefined;

    if (payload?.status && payload.detail?.type && payload.detail?.message) {
      return NextResponse.json({ detail: payload.detail }, { status: payload.status });
    }

    return NextResponse.json(
      {
        detail: {
          type: "InternalServerError",
          message: error instanceof Error ? error.message : "Query execution failed.",
        },
      },
      { status: 500 },
    );
  }
}