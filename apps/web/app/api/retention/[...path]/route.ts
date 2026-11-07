import { type NextRequest, NextResponse } from "next/server";

const resources = new Set([
  "workspace",
  "overview",
  "risk",
  "cohorts",
  "model-status",
  "jobs",
  "system-status",
]);
const queries = new Set(["limit", "offset", "search", "band", "auto_renew", "model_version"]);

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const allowed =
    (path.length === 1 && resources.has(path[0])) ||
    (path.length === 2 && path[0] === "customers" && /^SYN-[0-9]{5,7}$/.test(path[1]));
  if (!allowed) return NextResponse.json({ detail: "Resource not found" }, { status: 404 });
  if ([...request.nextUrl.searchParams.keys()].some((key) => !queries.has(key))) {
    return NextResponse.json({ detail: "Unsupported query parameter" }, { status: 400 });
  }
  const target = new URL(
    `/api/v1/${path.join("/")}`,
    process.env.RETENTIONOPS_API_URL || "http://127.0.0.1:8000",
  );
  target.search = request.nextUrl.search;
  try {
    const response = await fetch(target, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    const body = await response.json();
    return NextResponse.json(body, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: "Published data is unavailable. Retry after the data service recovers." },
      { status: 503 },
    );
  }
}
