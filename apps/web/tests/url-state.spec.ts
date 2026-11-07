import { expect, test } from "@playwright/test";

test("shared risk filters load actual rows and survive reload", async ({ page, request }) => {
  const expected = await (
    await request.get("/api/retention/workspace?limit=12&search=SYN&band=watch&auto_renew=0")
  ).json();
  expect(expected.risk.total).toBeGreaterThan(0);

  await page.goto("/risk?search=SYN&band=watch&auto_renew=0");
  await expect(page.getByLabel("Subscriber ID", { exact: true })).toHaveValue("SYN");
  await expect(page.getByRole("combobox", { name: "Risk band", exact: true })).toHaveValue("watch");
  await expect(page.getByRole("combobox", { name: "Auto-renew", exact: true })).toHaveValue("0");
  await expect(page.locator("tbody .customer-link")).toHaveText(
    expected.risk.items.map((row: { customer_id: string }) => row.customer_id),
  );
  await expect(page.getByRole("status")).toHaveText(`${expected.risk.total} matches`);

  await page.reload();
  await expect(page.getByLabel("Subscriber ID", { exact: true })).toHaveValue("SYN");
  await expect(page.getByRole("combobox", { name: "Risk band", exact: true })).toHaveValue("watch");
  await expect(page.getByRole("combobox", { name: "Auto-renew", exact: true })).toHaveValue("0");
  await expect(page.locator("tbody .customer-link")).toHaveText(
    expected.risk.items.map((row: { customer_id: string }) => row.customer_id),
  );
});

test("risk pagination and browser history restore the applied state", async ({ page, request }) => {
  const secondPage = await (
    await request.get("/api/retention/workspace?limit=12&offset=12&search=SYN")
  ).json();
  await page.goto("/risk?search=SYN&page=2");
  await expect(page.locator("tbody .customer-link")).toHaveText(
    secondPage.risk.items.map((row: { customer_id: string }) => row.customer_id),
  );
  await expect(page.locator(".pagination p")).toContainText("13–24");
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page).toHaveURL(/\/risk\?search=SYN&page=3$/);
  await expect(page.locator(".pagination p")).toContainText("25–36");

  await page.goBack();
  await expect(page).toHaveURL(/\/risk\?search=SYN&page=2$/);
  await expect(page.locator(".pagination p")).toContainText("13–24");
  await page.getByRole("combobox", { name: "Risk band", exact: true }).selectOption("watch");
  await page.getByRole("combobox", { name: "Auto-renew", exact: true }).selectOption("0");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect(page).toHaveURL(/\/risk\?search=SYN&band=watch&auto_renew=0$/);
  await expect(page.getByRole("button", { name: "Previous page" })).toBeDisabled();

  await page.goBack();
  await expect(page).toHaveURL(/\/risk\?search=SYN&page=2$/);
  await expect(page.locator("tbody .customer-link")).toHaveText(
    secondPage.risk.items.map((row: { customer_id: string }) => row.customer_id),
  );
  await expect(page.getByRole("combobox", { name: "Risk band", exact: true })).toHaveValue("all");
  await expect(page.getByRole("combobox", { name: "Auto-renew", exact: true })).toHaveValue("all");
  await page.goForward();
  await expect(page).toHaveURL(/\/risk\?search=SYN&band=watch&auto_renew=0$/);
  await expect(page.getByRole("combobox", { name: "Risk band", exact: true })).toHaveValue("watch");
  await expect(page.getByRole("combobox", { name: "Auto-renew", exact: true })).toHaveValue("0");
  await expect(page.getByRole("button", { name: "Previous page" })).toBeDisabled();

  await page.getByLabel("Subscriber ID", { exact: true }).fill("SYN-9999999");
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(page).toHaveURL(/\/risk$/);
  await expect(page.getByLabel("Subscriber ID", { exact: true })).toHaveValue("");
  await expect(page.getByRole("combobox", { name: "Risk band", exact: true })).toHaveValue("all");
  await expect(page.getByRole("combobox", { name: "Auto-renew", exact: true })).toHaveValue("all");
  await expect(page.getByRole("button", { name: "Previous page" })).toBeDisabled();
});

test("a saved page beyond the current cohort has a first-page recovery", async ({ page }) => {
  await page.goto("/risk?search=SYN&page=8334");
  await expect(
    page.getByRole("heading", { name: "This page is outside the current results" }),
  ).toBeVisible();
  await expect(page.locator(".pagination p")).toContainText("0 shown of");
  await page.getByRole("button", { name: "Go to first page", exact: true }).click();
  await expect(page).toHaveURL(/\/risk\?search=SYN$/);
  await expect(page.locator("tbody .customer-link")).toHaveCount(12);
  await expect(page.getByLabel("Subscriber ID", { exact: true })).toHaveValue("SYN");
  await expect(page.getByRole("button", { name: "Previous page" })).toBeDisabled();
});

test("a delayed filter response cannot replace results restored by browser back", async ({
  page,
}) => {
  await page.goto("/risk?search=SYN");
  await expect(page.getByRole("heading", { name: "Ranked subscribers" })).toBeVisible();
  const originalRows = await page.locator("tbody .customer-link").allTextContents();
  let release!: () => void;
  let started!: () => void;
  let finished!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const delayed = new Promise<void>((resolve) => {
    started = resolve;
  });
  const completed = new Promise<void>((resolve) => {
    finished = resolve;
  });
  await page.route("**/api/retention/workspace*", async (route) => {
    if (new URL(route.request().url()).searchParams.get("band") !== "watch") {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    started();
    await gate;
    try {
      await route.fulfill({ response });
    } catch {
      // Returning to the earlier URL may already have aborted this older request.
    } finally {
      finished();
    }
  });

  try {
    await page.getByRole("combobox", { name: "Risk band", exact: true }).selectOption("watch");
    await page.getByRole("button", { name: "Apply filters", exact: true }).click();
    await delayed;
    await expect(page).toHaveURL(/\/risk\?search=SYN&band=watch$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/risk\?search=SYN$/);
    await expect(page.locator("tbody .customer-link")).toHaveText(originalRows);
    release();
    await completed;
    await expect(page.locator("tbody .customer-link")).toHaveText(originalRows);
    await expect(page.getByRole("combobox", { name: "Risk band", exact: true })).toHaveValue("all");
  } finally {
    release();
  }
});
