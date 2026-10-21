// Every Lab page that exists fits a 360 px phone and a 1920 px projector without sideways scrolling (SPEC 13).
import { expect, test } from "@playwright/test";

for (const width of [360, 1920]) {
  for (const route of ["/", "/record"]) {
    test(`Lab ${route} fits ${width} px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 360 ? 740 : 1080 });
      await page.goto(`http://localhost:5173${route}`);
      await expect(page.locator("main")).toBeVisible();
      const overflow = await page.evaluate(() =>
        [...document.querySelectorAll("body *")]
          .filter((el) => el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX === "visible")
          .map((el) => el.tagName.toLowerCase() + (el.className ? `.${el.className}` : "")),
      );
      expect(overflow).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`lab${route.replace("/", "-") || "-home"}-${width}.png`), fullPage: true });
    });
  }
}
