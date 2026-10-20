import { expect, test } from "@playwright/test";

// M1.1 acceptance: Lab on :5173, Demo on :5174, GET /api/health returns 200 (also through each site's proxy).
for (const site of [
  { name: "Lab", url: "http://localhost:5173", title: "PulseLens Lab" },
  { name: "Demo", url: "http://localhost:5174", title: "PulseLens Demo" },
]) {
  test(`${site.name} loads and proxies /api`, async ({ page, request }) => {
    await page.goto(site.url);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(site.title);
    const health = await request.get(`${site.url}/api/health`);
    expect(health.status()).toBe(200);
    expect((await health.json()).status).toBe("ok");
  });
}

test("server health returns 200", async ({ request }) => {
  const r = await request.get("http://127.0.0.1:8000/api/health");
  expect(r.status()).toBe(200);
});
