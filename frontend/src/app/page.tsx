import type { Metadata } from "next";
import { headers } from "next/headers";

import { Db2Playground } from "@src/components/db2-playground";
import type { Db2TablesEndpointResponse } from "@src/types/db2";

export const metadata: Metadata = {
  title: "DB2 Playground",
  description:
    "A focused DB2 query playground for exploring tables, schemas, and query results.",
};

export default async function Home() {
  const headerList = await headers();
  const protocol = headerList.get("x-forwarded-proto") ?? "http";
  const host = headerList.get("host") ?? "localhost:3000";
  const response = await fetch(`${protocol}://${host}/api/tables`, { cache: "no-store" });
  const payload = (await response.json()) as Db2TablesEndpointResponse;
  const initialCatalog = payload.tables;

  return <Db2Playground initialCatalog={initialCatalog} />;
}
