import { expect, test } from "@playwright/test";

function watchErrors(page: import("@playwright/test").Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  return errors;
}

test("heat intelligence: layers, drivers, readiness, land indicator", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/app/heat");
  await page.locator(".ranking button").first().click();

  await expect(page.getByRole("heading", { name: /associated with this ward/ })).toBeVisible();
  await expect(page.locator(".drivers li").first()).toBeVisible();
  await expect(page.getByText(/Not observed: anthropogenic heat/)).toBeVisible();
  await expect(page.getByRole("heading", { name: /Readiness prompts/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Land indicator/ })).toBeVisible();

  // ΔLST raster (PMTiles over HTTP range requests) and the other layers must load without errors.
  const tiles = page.waitForResponse((r) => r.url().includes("/tiles/mini_city/dlst.pmtiles") && r.status() === 206);
  await page.getByLabel("ΔLST raster").check();
  await tiles;
  for (const name of [/Facilities/, /Satellite fire detections/, /Protected areas/]) {
    await page.getByLabel(name).check();
  }
  await expect(page.getByText(/last satellite pass, not real time/).first()).toBeVisible();
  await page.getByLabel("Colour wards by").selectOption("degradation");
  await expect(page.locator(".legend-chips")).toBeVisible();
  expect(errors).toEqual([]);
});

test("planner publishes an advisory; the public sees it and can listen", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/app");
  await page.getByRole("link", { name: "Planner console" }).first().click();

  await page.getByLabel("Planner API key").fill("dev-planner-key");
  await page.getByLabel(/Your name/).fill("asha");
  await page.getByRole("button", { name: "Save for this tab" }).click();

  // official warning outranks the forecast and shows as a banner
  await page.getByLabel("Text").fill("Heatwave warning for the district (test entry)");
  await page.getByRole("button", { name: "Save", exact: true }).first().click();
  await expect(page.getByText(/officialWarning|Official warning/).first()).toBeVisible();

  await page.getByRole("button", { name: "Compose advisory" }).click();
  const card = page.locator("article.reco").filter({ hasText: "draft" }).first();
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Approve" }).click();
  await page.locator("article.reco").filter({ hasText: "approved" }).first().getByRole("button", { name: "Publish" }).click();
  await expect(page.locator("article.reco").filter({ hasText: "published" }).first()).toBeVisible();

  // public side
  await page.getByRole("link", { name: /^Alerts & forecast/ }).click();
  await expect(page.getByRole("heading", { name: "Heat-dome forecast signal" })).toBeVisible();
  const advisory = page.locator("article.reco").first();
  await expect(advisory).toContainText("Heat advisory");
  await advisory.getByRole("button", { name: /Listen/ }).click();
  await expect(advisory.locator("audio")).toBeVisible();
  expect(errors.filter((e) => !e.includes("401"))).toEqual([]);
});

test("roof sketch sets the area and the assessment still works", async ({ page }) => {
  await page.goto("/app/solar");
  const grid = page.locator(".sketch-grid");
  await grid.scrollIntoViewIfNeeded();
  const box = (await grid.boundingBox())!;
  // an 8 m × 8 m square (64 m²) drawn on the 30 m canvas
  for (const [x, y] of [[0.3, 0.3], [0.57, 0.3], [0.57, 0.57], [0.3, 0.57]]) {
    await page.mouse.click(box.x + box.width * x, box.y + box.height * y);
  }
  await page.getByRole("button", { name: "Use this outline" }).click();
  await page.getByLabel("Monthly electricity (units)").fill("400");
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByText(/PM Surya Ghar subsidy/).first()).toBeVisible();
  await expect(page.getByText(/₹/).first()).toBeVisible();
});
