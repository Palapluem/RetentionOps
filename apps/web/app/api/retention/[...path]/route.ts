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
const insightHosts = new Set([
  "127.0.0.1:3000",
  "localhost:3000",
  "127.0.0.1:3100",
  "localhost:3100",
]);

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

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (path.length !== 1 || path[0] !== "insights") {
    return NextResponse.json({ detail: "Resource not found" }, { status: 404 });
  }
  if (!insightHosts.has(request.headers.get("host") ?? "")) {
    return NextResponse.json({ detail: "Local dashboard host required" }, { status: 403 });
  }
  if (request.headers.get("origin") !== new URL(request.url).origin) {
    return NextResponse.json({ detail: "Same-origin request required" }, { status: 403 });
  }
  const target = new URL(
    "/api/v1/insights",
    process.env.RETENTIONOPS_API_URL || "http://127.0.0.1:8000",
  );
  try {
    // Discard caller input: the API builds its prompt from its own allowlisted aggregates.
    const response = await fetch(target, {
      method: "POST",
      body: "{}",
      headers: { "X-RetentionOps-Local-Insight": "generate" },
      cache: "no-store",
      signal: AbortSignal.timeout(50_000),
    });
    const body = await response.json();
    return NextResponse.json(body, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: "Local insight is unavailable. The dashboard remains available." },
      { status: 503 },
    );
  }
}
