import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("overview uses published API values and supports keyboard customer review", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/retention/workspace?limit=12");
  expect(response.ok()).toBeTruthy();
  const actual = await response.json();
  await page.goto("/overview");
  await expect(page.getByRole("heading", { name: "Highest-risk subscribers" })).toBeVisible();
  await expect(page.locator(".metric-strip .metric-value").first()).toHaveText(
    String(actual.overview.customers),
  );
  const customer = page.getByRole("button", {
    name: actual.risk.items[0].customer_id,
    exact: true,
  });
  await customer.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Observed inputs")).toBeVisible();
  await expect(dialog.locator(".detail-id")).toHaveText(actual.risk.items[0].customer_id);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(customer).toBeFocused();
});

test("risk filtering, pagination and empty recovery use actual rows", async ({ page, request }) => {
  await page.goto("/risk");
  await expect(page.getByRole("heading", { name: "Ranked subscribers" })).toBeVisible();
  const first = await page.locator("tbody .customer-link").allTextContents();
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page.locator(".pagination p")).toContainText("13–24");
  const second = await page.locator("tbody .customer-link").allTextContents();
  expect(second.some((id) => first.includes(id))).toBeFalsy();
  await page.getByRole("combobox", { name: "Risk band", exact: true }).selectOption("watch");
  await page.getByRole("combobox", { name: "Auto-renew", exact: true }).selectOption("0");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
  const expected = await (
    await request.get("/api/retention/workspace?band=watch&auto_renew=0")
  ).json();
  await expect(page.getByRole("status")).toHaveText(`${expected.risk.total} matches`);
  await expect(page.getByRole("button", { name: "Previous page" })).toBeDisabled();
  await page.getByLabel("Subscriber ID", { exact: true }).fill("SYN-9999999");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "No subscribers match these filters" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear filters", exact: true }).click();
  await expect(page.locator("tbody .customer-link")).toHaveCount(12);
});

test("cohort denominators, model lineage and actual job history are visible", async ({ page }) => {
  await page.goto("/cohorts");
  await expect(page.getByRole("heading", { name: "Cohort breakdown" })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(4);
  await expect(page.locator("tbody tr").first()).toContainText("150");
  await page.getByRole("button", { name: /30 Jun 2026:/ }).click();
  await expect(page.locator(".chart-summary")).toContainText("30 Jun 2026");
  await page.getByRole("link", { name: "Data & model", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Recent pipeline runs" })).toBeVisible();
  await expect(page.locator(".lineage").first()).toContainText("Event-derived");
  await expect(page.getByRole("region", { name: "Pipeline run history" })).toContainText(
    "succeeded",
  );
  await page.getByText("Source and artifact identifiers", { exact: true }).click();
  await expect(page.getByText("Dataset SHA-256", { exact: true })).toBeVisible();
});

test("upstream error and retry are explicit", async ({ page }) => {
  await page.route("**/api/retention/workspace*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Data service is unavailable." }),
    }),
  );
  await page.goto("/risk");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Results could not be loaded",
  );
  await page.unroute("**/api/retention/workspace*");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ranked subscribers" })).toBeVisible();
});

test("first failed pipeline remains visible when no publication exists", async ({ page }) => {
  await page.route("**/api/retention/workspace*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "No valid publication." }),
    }),
  );
  await page.route("**/api/retention/jobs", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        publication_present: false,
        items: [
          {
            run_id: "run-first-failure",
            mode: "events",
            state: "failed",
            started_at: "2026-11-03T04:00:00+00:00",
            finished_at: "2026-11-03T04:00:01+00:00",
            elapsed_seconds: 1,
            output_rows: null,
            error_type: "ValueError",
          },
        ],
      }),
    }),
  );
  await page.goto("/status");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Results could not be loaded",
  );
  await expect(page.getByText("No successful publication exists yet.")).toBeVisible();
  const history = page.getByRole("region", { name: "Latest pipeline attempts" });
  await expect(history).toContainText("failed");
  await expect(history).toContainText("ValueError");
});

test("loading state is announced while a response is pending", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/retention/workspace*", async (route) => {
    await gate;
    await route.continue();
  });
  await page.goto("/overview");
  await expect(page.getByRole("status")).toContainText("Loading published results");
  release();
  await expect(page.getByRole("heading", { name: "Highest-risk subscribers" })).toBeVisible();
});

test("proxy rejects arbitrary resources, URLs and invalid filters", async ({ request }) => {
  expect((await request.get("/api/retention/anything")).status()).toBe(404);
  expect((await request.get("/api/retention/workspace?url=http://example.com")).status()).toBe(400);
  expect((await request.get("/api/retention/workspace?limit=1000")).status()).toBe(422);
  const good = await request.get("/api/retention/workspace");
  expect(good.headers()["cache-control"]).toBe("no-store");
});

for (const view of ["/overview", "/risk", "/cohorts", "/status"]) {
  test(`accessibility ${view}`, async ({ page }) => {
    await page.goto(view);
    await expect(page.getByText("Loading published results", { exact: true })).not.toBeVisible();
    await expect(page.locator("main .panel").first()).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
}

test("mobile navigation, filters and tables fit the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/risk");
  await expect(page.getByRole("heading", { name: "Ranked subscribers" })).toBeVisible();
  const widths = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(widths.document).toBe(widths.viewport);
  await page.getByRole("link", { name: "Cohort analytics", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Cohort breakdown" })).toBeVisible();
  const region = page.getByRole("region", { name: "Cohort breakdown", exact: true });
  await region.focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => region.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
