import { expect, test } from "@playwright/test";

test("usa map supports hover, pan, zoom, and Iowa drill-down", async ({ page }) => {
  await page.goto("/#/map");

  const svg = page.locator(".usa-map-svg");
  const iowa = page.locator('[data-state-name="Iowa"]');
  const texas = page.locator('[data-state-name="Texas"]');

  await expect(page.getByLabel("Interactive USA map with Iowa active")).toBeVisible();
  await expect(page.getByRole("heading", { name: "USA overview" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Iowa grid" })).toBeVisible();
  await expect(svg).toHaveAttribute("data-active-state", "Iowa");
  await expect(svg).toHaveAttribute("data-zoom", "1.000");
  await expect(svg).toHaveAttribute("data-selected-state", "");
  await expect(svg).toHaveAttribute("data-hovered-state", "");
  await expect(page.locator(".usa-map-state")).toHaveCount(51);

  await iowa.hover();
  await expect(svg).toHaveAttribute("data-hovered-state", "Iowa");

  await texas.click();
  await expect(svg).toHaveAttribute("data-selected-state", "Texas");

  const box = await svg.boundingBox();
  if (!box) {
    throw new Error("USA map SVG is not visible.");
  }

  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 120, startY + 32);
  await page.mouse.up();

  await expect(svg).not.toHaveAttribute("data-pan-x", "0.00");

  const zoomBefore = Number(await svg.getAttribute("data-zoom"));
  await svg.dispatchEvent("wheel", {
    clientX: startX,
    clientY: startY,
    deltaY: -640,
    bubbles: true,
    cancelable: true,
  });
  await expect.poll(async () => Number(await svg.getAttribute("data-zoom"))).toBeGreaterThan(zoomBefore);

  await svg.dblclick();
  await expect(svg).toHaveAttribute("data-zoom", "1.000");
  await expect(svg).toHaveAttribute("data-pan-x", "0.00");
  await expect(svg).toHaveAttribute("data-pan-y", "0.00");

  await iowa.click();
  await expect(page).toHaveURL(/#\/map\/iowa$/);
  await expect(page.getByRole("heading", { name: "Iowa H3 grid" })).toBeVisible();
});
