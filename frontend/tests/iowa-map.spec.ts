import { expect, test } from "@playwright/test";

import { getStaticIowaH3Map } from "../src/data/iowaH3MapData";

test("map pans, zooms, hovers, and pins cells", async ({ page }) => {
  await page.goto("/#/map");

  const svg = page.locator(".map-svg");
  const initialMap = getStaticIowaH3Map(8);
  const resolution10Map = getStaticIowaH3Map(10);
  const firstCellId = initialMap.cells[0].h3_index;

  await expect(page.getByRole("heading", { name: "Iowa H3 grid" })).toBeVisible();
  await expect(svg).toHaveAttribute("data-resolution", "8");
  await expect(svg).toHaveAttribute("data-zoom", "1.000");
  await expect(page.locator(".map-cell")).toHaveCount(initialMap.cells.length);

  const firstCell = page.locator(".map-cell").first();

  await firstCell.hover();
  await expect(page.locator(".map-inspector h2")).toHaveText(firstCellId);

  await firstCell.click();
  await page.mouse.move(25, 25);
  await expect(page.locator(".map-inspector h2")).toHaveText(firstCellId);

  const box = await svg.boundingBox();
  if (!box) {
    throw new Error("Map SVG is not visible.");
  }

  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 96, startY + 48);
  await page.mouse.up();

  await expect(svg).not.toHaveAttribute("data-pan-x", "0.00");

  const zoomBefore = Number(await svg.getAttribute("data-zoom"));
  await svg.dispatchEvent("wheel", {
    clientX: startX,
    clientY: startY,
    deltaY: -600,
    bubbles: true,
    cancelable: true,
  });
  await expect.poll(async () => Number(await svg.getAttribute("data-zoom"))).toBeGreaterThan(zoomBefore);

  const zoomInButton = page.getByRole("button", { name: "Zoom in" });
  for (let index = 0; index < 4; index += 1) {
    await zoomInButton.click();
  }

  await expect(svg).toHaveAttribute("data-resolution", "10");
  await expect(page.locator(".map-cell")).toHaveCount(resolution10Map.cells.length);
});
