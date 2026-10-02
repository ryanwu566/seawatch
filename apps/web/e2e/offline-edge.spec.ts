import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";

const pageOrigin = "http://127.0.0.1:8000";
let server: ChildProcess;

test.beforeAll(async () => {
  const repository = path.resolve(process.cwd(), "../..");
  const python = path.join(repository, ".venv", "Scripts", "python.exe");
  server = spawn(
    python,
    ["-m", "uvicorn", "apps.api.seawatch.main:app", "--host", "127.0.0.1", "--port", "8000"],
    {
      cwd: repository,
      env: {
        ...process.env,
        SEAWATCH_SERVE_WEB: "true",
        SEAWATCH_WEB_DIST: path.join(repository, "apps", "web", "dist"),
        SEAWATCH_LIVE_INGEST: "false",
      },
      stdio: "inherit",
    },
  );
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch(`${pageOrigin}/health`);
      if (response.ok) return;
    } catch {
      // Server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("local FastAPI server did not become ready");
});

test.afterAll(async () => {
  if (!server || server.exitCode !== null) return;
  await new Promise<void>((resolve) => {
    server.once("exit", () => resolve());
    server.kill();
    setTimeout(resolve, 2_000);
  });
});

test("offline Edge stays same-origin and renders the emergency map", async ({ page }) => {
  const forbidden: string[] = [];
  const observed: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (url.startsWith("data:") || url.startsWith("blob:")) return;
    observed.push(url);
    if (new URL(url).origin !== pageOrigin) forbidden.push(url);
  });

  await page.goto(`${pageOrigin}/`, { waitUntil: "networkidle" });
  await expect(page.locator(".app-header")).toBeVisible();
  await expect(page.locator('[data-basemap-stage="emergency"] canvas')).toBeVisible();
  await expect(page.getByLabel("Taiwan maritime map")).toBeVisible();
  await expect(
    page.locator(".live-pill").filter({ hasText: /即時資料無法使用|LIVE DATA UNAVAILABLE/ }),
  ).toBeVisible();
  await expect(page.locator(".map-canvas")).toBeVisible();

  expect(observed.some((url) => url.includes("/live/vessels"))).toBe(true);
  expect(observed.some((url) => url.includes("/resilience/status"))).toBe(true);
  expect(forbidden).toEqual([]);
  expect(observed.join("\n")).not.toMatch(
    /localhost:8000|vercel|onrender|nlsc|cdn|fonts\.google|demotiles/i,
  );
});
