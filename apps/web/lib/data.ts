import type { components } from "./schema";

export type WorkspaceData = components["schemas"]["Workspace"];
export type Risk = components["schemas"]["RiskItem"];
export type Cohort = components["schemas"]["Cohort"];
export type Customer = components["schemas"]["CustomerDetail"];
export type JobPage = components["schemas"]["JobPage"];
export type SystemData = components["schemas"]["SystemStatus"];

export async function readData<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/retention/${path}`, { signal, cache: "no-store" });
  const body = await response.json();
  if (!response.ok)
    throw new Error(typeof body.detail === "string" ? body.detail : "Check the filters and retry.");
  return body as T;
}

export const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
export const number = (value: number) => new Intl.NumberFormat("en-GB").format(value);
export const shortDate = (value: string) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
export const timestamp = (value: string) =>
  `${new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Bangkok",
  }).format(new Date(value))} ICT`;
