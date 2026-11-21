import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("home shows the actual local system release and source boundary", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/retention/system-status");
  expect(response.ok()).toBeTruthy();
  const actual = await response.json();
  expect(actual.publication_state).toBe("ready");
  expect(actual.model_artifact_state).toBe("verified");
  expect(actual.quality_summary.reconciliation_status).toBe("verified");
  expect(actual.quality_summary.scored_rows).toBe(actual.scored_customers);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "System dashboard", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "The active release is serving" })).toBeVisible();
  await expect(
    page.getByRole("list", { name: "Local pipeline stages" }).getByRole("listitem"),
  ).toHaveCount(5);
  await expect(page.getByText(actual.active_release.model_version, { exact: true })).toBeVisible();
  await page.getByText("Source & artifact evidence", { exact: true }).click();
  await expect(
    page.getByText(actual.active_release.event_release_id, { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(actual.active_release.model_sha256, { exact: true })).toBeVisible();
  await expect(
    page.getByText(`${actual.scored_customers} rows reconciled`, { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Simulated labels", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Data quality & model health" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Mature cohort denominators" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate insight" })).toBeEnabled();
  await expect(page.getByRole("definition").filter({ hasText: /^Not connected/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "System pipeline attempts" })).toContainText(
    "succeeded",
  );
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole("heading", { name: "Holdout evaluation" })).toBeVisible();
  const estimator =
    actual.active_release.model_family === "lightgbm" ? "LightGBM" : "Logistic Regression";
  await expect(page.locator(".evaluation .subtle-label")).toHaveText(estimator);
});

test("local AI insight is opt-in and displays only bounded advisory evidence", async ({
  page,
  request,
}) => {
  const system = await (await request.get("/api/retention/system-status")).json();
  const quality = system.quality_summary;
  await page.route("**/api/retention/insights", async (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().postData()).toBeNull();
    await route.fulfill({
      json: {
        status: "ready",
        generated_at: system.observed_at,
        model: "qwen3:4b-instruct",
        source_release_id: quality.source_release_id,
        model_version: quality.model_version,
        score_cutoff: quality.score_cutoff,
        advisory_only: true,
        observations: [
          {
            id: "test_cohort_mature",
            text: `The evaluated test cohort has ${quality.test_cohort_rows} mature rows.`,
          },
        ],
        next_step: "Review eligible and churned denominators across the cohorts.",
        reason: null,
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Generate insight" }).click();
  await expect(page.getByRole("status")).toContainText("mature rows");
  await expect(page.getByRole("status")).toContainText("Advisory only");
  await expect(page.getByRole("status")).not.toContainText("SYN-");
});

test("local AI being unavailable leaves the System dashboard usable", async ({ page }) => {
  await page.route("**/api/retention/insights", (route) =>
    route.fulfill({
      json: {
        status: "unavailable",
        generated_at: "2026-11-20T00:00:00Z",
        model: null,
        source_release_id: null,
        model_version: null,
        score_cutoff: null,
        advisory_only: true,
        observations: [],
        next_step: null,
        reason: "runtime_unavailable",
      },
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Generate insight" }).click();
  await expect(page.getByRole("status")).toContainText("local Ollama runtime is not responding");
  await expect(page.getByRole("heading", { name: "Data quality & model health" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Overview", exact: true })).toBeVisible();
});

test("the loopback dashboard can request an insight through the API proxy", async ({ page }) => {
  await page.goto("/");
  const result = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/retention/insights") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate insight", exact: true }).click();
  const response = await result;

  expect(response.status()).toBe(200);
  await expect(response.json()).resolves.toMatchObject({
    status: "unavailable",
    reason: "unsafe_runtime_url",
  });
  await expect(page.getByRole("status")).toContainText("outside the approved local boundary");
});

test("insight proxy rejects a cross-origin request before calling the API", async ({ request }) => {
  const response = await request.post("/api/retention/insights", {
    headers: { origin: "https://untrusted.example" },
  });

  expect(response.status()).toBe(403);
  await expect(response.json()).resolves.toEqual({ detail: "Same-origin request required" });
});

test("insight proxy rejects a rebinding-style non-local Host", async ({ request }) => {
  const response = await request.post("/api/retention/insights", {
    headers: { host: "attacker.example", origin: "http://attacker.example" },
  });

  expect(response.status()).toBe(403);
  await expect(response.json()).resolves.toEqual({ detail: "Local dashboard host required" });
});

test("system displays a first failed attempt before any publication", async ({ page, request }) => {
  const actual = await (await request.get("/api/retention/system-status")).json();
  await page.route("**/api/retention/system-status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...actual,
        publication_state: "empty",
        active_release: null,
        scored_customers: null,
        score_cutoff: null,
        model_artifact_state: "not_published",
        message: "Run the synthetic event pipeline to publish the first release.",
        runs: [
          {
            run_id: "first-failure",
            mode: "event-source",
            state: "failed",
            started_at: actual.observed_at,
            finished_at: actual.observed_at,
            model_version: null,
            output_rows: null,
            elapsed_seconds: 1,
            error_type: "ValueError",
          },
        ],
      }),
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Publish the first local release" }),
  ).toBeVisible();
  const history = page.getByRole("region", { name: "System pipeline attempts" });
  await expect(history).toContainText("failed");
  await expect(history).toContainText("ValueError");
  await expect(page.getByText("No active scored source", { exact: true })).toBeVisible();
});

test("a mocked running attempt is presented as a recorded state on both views", async ({
  page,
  request,
}) => {
  const actualSystem = await (await request.get("/api/retention/system-status")).json();
  const actualWorkspace = await (
    await request.get("/api/retention/workspace?limit=12&offset=0")
  ).json();
  const running = {
    run_id: "mocked-unconfirmed-attempt",
    mode: "events",
    state: "running",
    started_at: actualSystem.observed_at,
    finished_at: null,
    model_version: null,
    output_rows: null,
    elapsed_seconds: null,
    error_type: null,
  };
  await page.route("**/api/retention/system-status", (route) =>
    route.fulfill({ json: { ...actualSystem, runs: [running] } }),
  );
  await page.route("**/api/retention/workspace*", (route) =>
    route.fulfill({
      json: { ...actualWorkspace, status: { ...actualWorkspace.status, runs: [running] } },
    }),
  );

  for (const [path, label] of [
    ["/", "System pipeline attempts"],
    ["/status", "Pipeline run history"],
  ]) {
    await page.goto(path);
    const history = page.getByRole("region", { name: label });
    await expect(history).toContainText("running (last recorded)");
    await expect(history).toContainText("Not recorded");
    await expect(history).not.toContainText("In progress");
    await expect(page.getByText(/does not confirm that the process is still active/)).toBeVisible();
  }
});

test("system error can be retried against the actual API", async ({ page }) => {
  await page.route("**/api/retention/system-status", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Data service is unavailable." }),
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "System status could not be loaded",
  );
  await page.unroute("**/api/retention/system-status");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("heading", { name: "The active release is serving" })).toBeVisible();
});

test("system is accessible and fits a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "The active release is serving" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
