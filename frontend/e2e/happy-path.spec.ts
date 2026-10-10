import { expect, test } from "@playwright/test";

test("pick a ward, see roofs, check solar, chat in Hindi", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  // Landing page first, then into the app.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Cool the right roofs");
  await page.getByRole("link", { name: "Open the app" }).first().click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Cool roofs");
  await page.getByRole("link", { name: /^Heat map/ }).click();
  await expect(page.getByText("surface temperature at a late-morning satellite pass")).toBeVisible();

  // Ranking list is keyboard-reachable; choosing a ward shows its panel.
  const first = page.locator(".ranking button").first();
  await expect(first).toBeVisible();
  await first.click();
  await expect(page.getByRole("heading", { name: /Heat type/ })).toBeVisible();
  await expect(page.getByText(/Recommendations/)).toBeVisible();
  await expect(page.getByText(/Cost not available/)).toBeVisible();
  await expect(page.locator(".roofs li").first()).toBeVisible();

  // Rooftop solar: 70 m², 400 units → 3 kW, ₹78,000, with provenance.
  await page.getByRole("link", { name: "Rooftop solar" }).click();
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByText("₹78,000")).toBeVisible();
  await expect(page.getByText(/subsidy:ALL:ALL:2024-02-29/)).toBeVisible();

  // Switch to Hindi and ask the assistant.
  await page.getByRole("button", { name: "हिं" }).click();
  await page.getByRole("link", { name: "सहायक" }).click();
  const box = page.getByLabel("अपना प्रश्न लिखें");
  await box.fill("मेरी छत 70 वर्ग मीटर है और 400 यूनिट बिजली लगती है, सोलर सब्सिडी कितनी?");
  await box.press("Enter");
  await expect(page.locator(".msg-assistant").last()).toContainText("₹78,000");
  await expect(page.getByText(/numbers checked/)).toBeVisible();

  expect(errors).toEqual([]);
});

test("unavailable states are explained, never blank", async ({ page }) => {
  await page.goto("/app/heat");
  await page.locator(".ranking button").first().click();
  await expect(page.getByText(/not verified yet/)).toBeVisible();
});
