import { test, expect } from "@playwright/test";
test("local telemetry, scenario, incident replay, evidence and report", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill(process.env.ADMIN_PASSWORD!);
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Security overview" }),
  ).toBeVisible();
  await expect(page.locator('.react-flow__node')).toHaveCount(5);
  await page.locator('.graph').scrollIntoViewIfNeeded();
  await expect(page.locator('.react-flow__node').first()).toBeVisible();
  await expect(page.locator('.react-flow__edge')).toHaveCount(4);
  await page.getByRole('status').click();
  await page.screenshot({
    path: "test-results/screenshots/overview.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Event explorer", exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "local", exact: true }).first(),
  ).toBeVisible({ timeout: 60000 });
  await page.getByRole("button", { name: "Scenario lab", exact: true }).click();
  await page.getByRole("button", { name: "Run scenario A" }).click();
  await page.getByRole("button", { name: /^Incidents/ }).click();
  await expect(
    page.getByRole("button", { name: /Open investigation/ }).first(),
  ).toBeVisible({ timeout: 60000 });
  await page
    .getByRole("button", { name: /Open investigation/ })
    .first()
    .click();
  await expect(
    page.getByText("SECURITY TIME MACHINE", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Next event").click();
  await expect(page.locator('.react-flow__node')).toHaveCount(1);
  await page.screenshot({
    path: "test-results/screenshots/time-machine.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Verify evidence" }).click();
  await expect(page.getByRole("status")).toContainText("verification complete");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "JSON evidence" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.json$/);
});
