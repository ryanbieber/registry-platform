import { expect, test, type Page } from "@playwright/test";

async function installPointerCaptureShim(page: Page, selector: string) {
  await page.evaluate((targetSelector) => {
    const element = document.querySelector(targetSelector);
    if (!(element instanceof SVGElement)) {
      throw new Error(`SVG element not found for selector: ${targetSelector}`);
    }

    const capturedPointers = new Set<number>();
    Object.assign(element, {
      hasPointerCapture(pointerId: number) {
        return capturedPointers.has(pointerId);
      },
      releasePointerCapture(pointerId: number) {
        capturedPointers.delete(pointerId);
      },
      setPointerCapture(pointerId: number) {
        capturedPointers.add(pointerId);
      },
    });
  }, selector);
}

async function dispatchSyntheticPointer(
  page: Page,
  selector: string,
  type: string,
  eventInit: {
    button?: number;
    clientX: number;
    clientY: number;
    isPrimary?: boolean;
    pointerId: number;
    pointerType: string;
  },
) {
  await page.evaluate(
    ({ targetSelector, nextType, nextEventInit }) => {
      const element = document.querySelector(targetSelector);
      if (!(element instanceof SVGElement)) {
        throw new Error(`SVG element not found for selector: ${targetSelector}`);
      }

      element.dispatchEvent(
        new PointerEvent(nextType, {
          bubbles: true,
          button: 0,
          cancelable: true,
          composed: true,
          ...nextEventInit,
        }),
      );
    },
    { nextEventInit: eventInit, nextType: type, targetSelector: selector },
  );
}

test("iowa h3 map supports selection, pan, zoom, and returning to the USA overview", async ({ page }) => {
  await page.goto("/#/map/iowa");

  const svg = page.locator(".map-svg");
  const resetButton = page.getByRole("button", { name: "Reset view" });
  const zoomInButton = page.getByRole("button", { name: "Zoom in" });
  const cell = page.locator('[data-h3-index="880000000000001"]');

  await expect(page.getByRole("heading", { name: "Iowa H3 grid" })).toBeVisible();
  await expect(svg).toHaveAttribute("data-resolution", "8");
  await expect(page.locator(".map-inspector h2")).toHaveText("880000000000001");

  await cell.click();
  await expect(page.locator(".map-inspector h2")).toHaveText("880000000000001");

  const box = await svg.boundingBox();
  if (!box) {
    throw new Error("Iowa H3 SVG is not visible.");
  }

  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 120, startY + 48);
  await page.mouse.up();

  await expect(svg).not.toHaveAttribute("data-pan-x", "0.00");

  const zoomBeforeWheel = Number(await svg.getAttribute("data-zoom"));
  await svg.dispatchEvent("wheel", {
    clientX: startX,
    clientY: startY,
    deltaY: -640,
    bubbles: true,
    cancelable: true,
  });
  await expect.poll(async () => Number(await svg.getAttribute("data-zoom"))).toBeGreaterThan(zoomBeforeWheel);

  await zoomInButton.click();
  await expect.poll(async () => Number(await svg.getAttribute("data-zoom"))).toBeGreaterThan(1);

  await resetButton.click();
  await expect(svg).toHaveAttribute("data-zoom", "1.000");
  await expect(svg).toHaveAttribute("data-pan-x", "0.00");
  await expect(svg).toHaveAttribute("data-pan-y", "0.00");

  await page.getByRole("link", { name: "Back to USA map" }).click();
  await expect(page).toHaveURL(/#\/map$/);
  await expect(page.getByRole("heading", { name: "USA overview" })).toBeVisible();
});

test("iowa h3 map supports touch pan and pinch zoom", async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 900 });
  await page.goto("/#/map/iowa");

  const svg = page.locator(".map-svg");
  await expect(svg).toBeVisible();
  await installPointerCaptureShim(page, ".map-svg");

  const box = await svg.boundingBox();
  if (!box) {
    throw new Error("Iowa H3 SVG is not visible.");
  }

  const centerX = box.x + box.width / 2;
  const centerY = box.y + box.height / 2;

  await dispatchSyntheticPointer(page, ".map-svg", "pointerdown", {
    clientX: centerX,
    clientY: centerY,
    isPrimary: true,
    pointerId: 1,
    pointerType: "touch",
  });
  await dispatchSyntheticPointer(page, ".map-svg", "pointermove", {
    clientX: centerX + 90,
    clientY: centerY + 40,
    isPrimary: true,
    pointerId: 1,
    pointerType: "touch",
  });
  await dispatchSyntheticPointer(page, ".map-svg", "pointerup", {
    clientX: centerX + 90,
    clientY: centerY + 40,
    isPrimary: true,
    pointerId: 1,
    pointerType: "touch",
  });

  await expect(svg).not.toHaveAttribute("data-pan-x", "0.00");

  await page.getByRole("button", { name: "Reset view" }).click();
  await expect(svg).toHaveAttribute("data-zoom", "1.000");

  const zoomBeforePinch = Number(await svg.getAttribute("data-zoom"));
  await dispatchSyntheticPointer(page, ".map-svg", "pointerdown", {
    clientX: centerX - 40,
    clientY: centerY,
    isPrimary: true,
    pointerId: 1,
    pointerType: "touch",
  });
  await dispatchSyntheticPointer(page, ".map-svg", "pointerdown", {
    clientX: centerX + 40,
    clientY: centerY,
    isPrimary: false,
    pointerId: 2,
    pointerType: "touch",
  });
  await dispatchSyntheticPointer(page, ".map-svg", "pointermove", {
    clientX: centerX - 120,
    clientY: centerY - 10,
    isPrimary: true,
    pointerId: 1,
    pointerType: "touch",
  });
  await dispatchSyntheticPointer(page, ".map-svg", "pointermove", {
    clientX: centerX + 120,
    clientY: centerY + 10,
    isPrimary: false,
    pointerId: 2,
    pointerType: "touch",
  });
  await dispatchSyntheticPointer(page, ".map-svg", "pointerup", {
    clientX: centerX - 120,
    clientY: centerY - 10,
    isPrimary: true,
    pointerId: 1,
    pointerType: "touch",
  });
  await dispatchSyntheticPointer(page, ".map-svg", "pointerup", {
    clientX: centerX + 120,
    clientY: centerY + 10,
    isPrimary: false,
    pointerId: 2,
    pointerType: "touch",
  });

  await expect.poll(async () => Number(await svg.getAttribute("data-zoom"))).toBeGreaterThan(zoomBeforePinch);
});
