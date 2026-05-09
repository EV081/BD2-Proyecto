"use client";

// ---------------------------------------------------------------------------
// Types matching the backend spatial response format
// ---------------------------------------------------------------------------

export type SpatialQueryMode = "radius" | "knn" | "unknown";

export interface SpatialQueryContext {
  mode: SpatialQueryMode;
  center?: [number, number]; // [x, y] from the parsed WHERE clause
  radius?: number;
  k?: number;
}

interface SpatialRid {
  page: number;
  slot: number;
}

interface SpatialResultPoint {
  x: number;
  y: number;
  rid?: SpatialRid;
  distance?: number;
  color?: string;
}

interface SpatialQueryPoint {
  x: number;
  y: number;
  color?: string;
}

interface BackendSpatialData {
  query_point?: SpatialQueryPoint;
  results?: SpatialResultPoint[];
  total?: number;
}

export interface SpatialMapProps {
  data: unknown;
  queryContext?: SpatialQueryContext;
}

// ---------------------------------------------------------------------------
// Parse the backend response into a usable shape
// ---------------------------------------------------------------------------

function parseSpatialData(data: unknown): BackendSpatialData {
  if (!data || typeof data !== "object") return {};
  const d = data as Record<string, unknown>;
  return {
    query_point: d.query_point as SpatialQueryPoint | undefined,
    results: Array.isArray(d.results) ? (d.results as SpatialResultPoint[]) : [],
    total: typeof d.total === "number" ? d.total : undefined,
  };
}

// ---------------------------------------------------------------------------
// Grid coordinate system helpers
// ---------------------------------------------------------------------------

const GRID_W = 480;
const GRID_H = 360;
const PADDING = 48;
const INNER_W = GRID_W - PADDING * 2;
const INNER_H = GRID_H - PADDING * 2;
const TICK_COUNT = 6;

function buildScale(
  allX: number[],
  allY: number[],
): { toSvgX: (x: number) => number; toSvgY: (y: number) => number; minX: number; maxX: number; minY: number; maxY: number } {
  const padFrac = 0.15;

  const rawMinX = Math.min(...allX);
  const rawMaxX = Math.max(...allX);
  const rawMinY = Math.min(...allY);
  const rawMaxY = Math.max(...allY);

  const dx = rawMaxX - rawMinX || 1;
  const dy = rawMaxY - rawMinY || 1;

  const minX = rawMinX - dx * padFrac;
  const maxX = rawMaxX + dx * padFrac;
  const minY = rawMinY - dy * padFrac;
  const maxY = rawMaxY + dy * padFrac;

  return {
    minX,
    maxX,
    minY,
    maxY,
    toSvgX: (x) => PADDING + ((x - minX) / (maxX - minX)) * INNER_W,
    toSvgY: (y) => PADDING + INNER_H - ((y - minY) / (maxY - minY)) * INNER_H,
  };
}

function linspace(min: number, max: number, n: number): number[] {
  return Array.from({ length: n }, (_, i) => min + (i / (n - 1)) * (max - min));
}

function fmt(n: number): string {
  return n.toFixed(2);
}

// ---------------------------------------------------------------------------
// SVG Grid component
// ---------------------------------------------------------------------------

function SpatialGrid({
  queryPoint,
  results,
  mode,
  radius,
}: {
  queryPoint?: SpatialQueryPoint;
  results: SpatialResultPoint[];
  mode: SpatialQueryMode;
  radius?: number;
}) {
  const allX: number[] = [];
  const allY: number[] = [];

  if (queryPoint) {
    allX.push(queryPoint.x);
    allY.push(queryPoint.y);
  }
  results.forEach((r) => {
    allX.push(r.x);
    allY.push(r.y);
  });

  if (allX.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-sm text-slate-400">
        No spatial points to display.
      </div>
    );
  }

  const scale = buildScale(allX, allY);
  const { toSvgX, toSvgY, minX, maxX, minY, maxY } = scale;

  const xTicks = linspace(minX, maxX, TICK_COUNT);
  const yTicks = linspace(minY, maxY, TICK_COUNT);

  // Radius in SVG units (approximate — assumes uniform scale)
  let svgRadius: number | null = null;
  if (mode === "radius" && radius != null && queryPoint) {
    const scaleX = INNER_W / (maxX - minX);
    svgRadius = radius * scaleX;
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <svg
        viewBox={`0 0 ${GRID_W} ${GRID_H}`}
        className="w-full"
        style={{ fontFamily: "var(--font-geist-mono, monospace)" }}
      >
        {/* Background */}
        <rect x={PADDING} y={PADDING} width={INNER_W} height={INNER_H} fill="#f8fafc" rx={2} />

        {/* Grid lines — vertical */}
        {xTicks.map((tick, i) => {
          const sx = toSvgX(tick);
          return (
            <g key={i}>
              <line x1={sx} y1={PADDING} x2={sx} y2={PADDING + INNER_H} stroke="#e2e8f0" strokeWidth={1} />
              <text x={sx} y={PADDING + INNER_H + 14} textAnchor="middle" fontSize={9} fill="#94a3b8">
                {fmt(tick)}
              </text>
            </g>
          );
        })}

        {/* Grid lines — horizontal */}
        {yTicks.map((tick, i) => {
          const sy = toSvgY(tick);
          return (
            <g key={i}>
              <line x1={PADDING} y1={sy} x2={PADDING + INNER_W} y2={sy} stroke="#e2e8f0" strokeWidth={1} />
              <text x={PADDING - 6} y={sy + 3} textAnchor="end" fontSize={9} fill="#94a3b8">
                {fmt(tick)}
              </text>
            </g>
          );
        })}

        {/* Axes labels */}
        <text
          x={PADDING + INNER_W / 2}
          y={GRID_H - 4}
          textAnchor="middle"
          fontSize={10}
          fill="#64748b"
        >
          X
        </text>
        <text
          x={10}
          y={PADDING + INNER_H / 2}
          textAnchor="middle"
          fontSize={10}
          fill="#64748b"
          transform={`rotate(-90, 10, ${PADDING + INNER_H / 2})`}
        >
          Y
        </text>

        {/* Radius circle */}
        {svgRadius !== null && queryPoint && (
          <circle
            cx={toSvgX(queryPoint.x)}
            cy={toSvgY(queryPoint.y)}
            r={svgRadius}
            fill="#bfdbfe"
            fillOpacity={0.25}
            stroke="#3b82f6"
            strokeWidth={1.5}
            strokeDasharray="6 3"
          />
        )}

        {/* Result points */}
        {results.map((r, idx) => {
          const cx = toSvgX(r.x);
          const cy = toSvgY(r.y);
          const fill = mode === "knn" ? "#8b5cf6" : "#f97316";
          return (
            <g key={idx}>
              <circle cx={cx} cy={cy} r={6} fill={fill} opacity={0.85} />
              <text x={cx} y={cy - 9} textAnchor="middle" fontSize={9} fill={fill} fontWeight="600">
                {mode === "knn" ? `#${idx + 1}` : `R${idx + 1}`}
              </text>
            </g>
          );
        })}

        {/* Query point (on top) */}
        {queryPoint && (
          <g>
            {/* crosshair */}
            <line
              x1={toSvgX(queryPoint.x) - 8}
              y1={toSvgY(queryPoint.y)}
              x2={toSvgX(queryPoint.x) + 8}
              y2={toSvgY(queryPoint.y)}
              stroke="#2563eb"
              strokeWidth={2}
            />
            <line
              x1={toSvgX(queryPoint.x)}
              y1={toSvgY(queryPoint.y) - 8}
              x2={toSvgX(queryPoint.x)}
              y2={toSvgY(queryPoint.y) + 8}
              stroke="#2563eb"
              strokeWidth={2}
            />
            <circle cx={toSvgX(queryPoint.x)} cy={toSvgY(queryPoint.y)} r={5} fill="#2563eb" />
            <text
              x={toSvgX(queryPoint.x)}
              y={toSvgY(queryPoint.y) - 10}
              textAnchor="middle"
              fontSize={9}
              fill="#2563eb"
              fontWeight="700"
            >
              Q
            </text>
          </g>
        )}

        {/* Border */}
        <rect
          x={PADDING}
          y={PADDING}
          width={INNER_W}
          height={INNER_H}
          fill="none"
          stroke="#cbd5e1"
          strokeWidth={1}
          rx={2}
        />
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Results table
// ---------------------------------------------------------------------------

function ResultsTable({
  results,
  mode,
}: {
  results: SpatialResultPoint[];
  mode: SpatialQueryMode;
}) {
  if (!results.length) {
    return <p className="py-3 text-sm text-slate-400">No results.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-left text-xs">
        <thead className="bg-slate-100 text-[11px] uppercase tracking-[0.15em] text-slate-500">
          <tr>
            <th className="border-b border-slate-200 px-3 py-2">#</th>
            <th className="border-b border-slate-200 px-3 py-2">X</th>
            <th className="border-b border-slate-200 px-3 py-2">Y</th>
            {mode === "knn" || results.some((r) => r.distance != null) ? (
              <th className="border-b border-slate-200 px-3 py-2">Distance</th>
            ) : null}
            <th className="border-b border-slate-200 px-3 py-2">Page</th>
            <th className="border-b border-slate-200 px-3 py-2">Slot</th>
          </tr>
        </thead>
        <tbody className="bg-white">
          {results.map((r, idx) => (
            <tr key={idx} className="odd:bg-white even:bg-slate-50">
              <td className="border-b border-slate-100 px-3 py-2 font-medium text-slate-500">
                {mode === "knn" ? `#${idx + 1}` : `R${idx + 1}`}
              </td>
              <td className="border-b border-slate-100 px-3 py-2 font-mono text-slate-800">
                {r.x}
              </td>
              <td className="border-b border-slate-100 px-3 py-2 font-mono text-slate-800">
                {r.y}
              </td>
              {mode === "knn" || results.some((r) => r.distance != null) ? (
                <td className="border-b border-slate-100 px-3 py-2 font-mono text-violet-700">
                  {r.distance != null ? r.distance.toFixed(6) : "—"}
                </td>
              ) : null}
              <td className="border-b border-slate-100 px-3 py-2 font-mono text-slate-500">
                {r.rid?.page ?? "—"}
              </td>
              <td className="border-b border-slate-100 px-3 py-2 font-mono text-slate-500">
                {r.rid?.slot ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function SpatialMap({ data, queryContext }: SpatialMapProps) {
  const parsed = parseSpatialData(data);
  const mode = queryContext?.mode ?? "unknown";
  const results = parsed.results ?? [];
  const queryPoint = parsed.query_point;

  const modeLabel =
    mode === "radius"
      ? `Radius search · r = ${queryContext?.radius ?? "?"}`
      : mode === "knn"
        ? `KNN · k = ${queryContext?.k ?? "?"}`
        : "Spatial search";

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-blue-600" /> Query point
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className={`inline-block h-2.5 w-2.5 rounded-full ${mode === "knn" ? "bg-violet-500" : "bg-orange-400"}`}
            />
            {mode === "knn" ? "K nearest" : "Results"}
          </span>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">
          {modeLabel} · {results.length} result{results.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Grid */}
      <SpatialGrid
        queryPoint={queryPoint}
        results={results}
        mode={mode}
        radius={queryContext?.radius}
      />

      {/* Results table */}
      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
          Result points
        </p>
        <ResultsTable results={results} mode={mode} />
      </div>

      {/* Query point detail */}
      {queryPoint && (
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
          Query origin: <span className="font-mono font-semibold">({queryPoint.x}, {queryPoint.y})</span>
        </div>
      )}
    </div>
  );
}
