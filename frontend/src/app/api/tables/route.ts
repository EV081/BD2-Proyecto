import { NextResponse } from "next/server";

import { fetchTables } from "@src/lib/db2/backend";

export async function GET(request: Request) {
  const response = await fetchTables(request.url);
  return NextResponse.json(response);
}