import type { Db2Table } from "@src/types/db2";

export const db2Catalog: Db2Table[] = [
  {
    name: "students",
    description: "Student records with grades.",
    columns: [
      { name: "id", type: "INT", index: "BTREE", nullable: false },
      { name: "nombre", type: "VARCHAR", index: "DEFAULT_INDEX", nullable: false },
      { name: "nota", type: "FLOAT", index: "DEFAULT_INDEX", nullable: false },
      { name: "ubicacion", type: "VARCHAR", index: "RTREE", nullable: true },
    ],
    rows: [
      { id: 101, nombre: "Juan Perez", nota: 15.5, ubicacion: "POINT(-12.04,-77.02)" },
      { id: 102, nombre: "Ana Torres", nota: 18.2, ubicacion: "POINT(-12.05,-77.03)" },
      { id: 103, nombre: "Luis Gomez", nota: 11.7, ubicacion: "POINT(-12.01,-77.01)" },
      { id: 104, nombre: "Maria Rios", nota: 19.1, ubicacion: "POINT(-12.08,-77.08)" },
    ],
  },
  {
    name: "usuarios",
    description: "Application users and status.",
    columns: [
      { name: "user_id", type: "INT", index: "BTREE", nullable: false },
      { name: "nombre", type: "VARCHAR", index: "DEFAULT_INDEX", nullable: false },
      { name: "estado", type: "VARCHAR", index: "HASH", nullable: false },
    ],
    rows: [
      { user_id: 500, nombre: "Admin", estado: "active" },
      { user_id: 501, nombre: "Guest", estado: "inactive" },
      { user_id: 502, nombre: "Analyst", estado: "active" },
    ],
  },
  {
    name: "inventory",
    description: "Stock snapshot for workspace assets.",
    columns: [
      { name: "sku", type: "VARCHAR", index: "HASH", nullable: false },
      { name: "item", type: "VARCHAR", index: "DEFAULT_INDEX", nullable: false },
      { name: "quantity", type: "INT", index: "SEQUENTIAL", nullable: false },
      { name: "location", type: "VARCHAR", index: "DEFAULT_INDEX", nullable: true },
    ],
    rows: [
      { sku: "DB-001", item: "Reference Guide", quantity: 18, location: "Rack A" },
      { sku: "DB-002", item: "Console Seat", quantity: 6, location: "Rack B" },
      { sku: "DB-003", item: "Storage Node", quantity: 2, location: "Rack C" },
    ],
  },
];