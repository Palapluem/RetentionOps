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
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "System dashboard", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "The active release is serving" })).toBeVisible();
  await expect(
    page.getByRole("list", { name: "Local pipeline stages" }).getByRole("listitem"),
  ).toHaveCount(5);
  await expect(page.getByText(actual.active_release.model_version, { exact: true })).toBeVisible();
  await expect(
    page.getByText(`${actual.scored_customers} rows reconciled`, { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Simulated labels", { exact: true })).toBeVisible();
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
