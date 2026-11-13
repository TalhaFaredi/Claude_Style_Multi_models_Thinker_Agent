/** Capture README screenshots from the offline demo; no backend or provider calls. */
import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import { once } from "node:events";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.resolve(frontend, "../docs/screenshots");
const port = 3142;
fs.mkdirSync(output, { recursive: true });
const server = spawn(process.execPath, [path.join(frontend, "node_modules/next/dist/bin/next"), "start", "--hostname", "127.0.0.1", "--port", String(port)], {
  cwd: frontend,
  env: { ...process.env, NEXT_BUILD_DIR: ".next-readme", MMA_DEMO: "1" },
  windowsHide: true,
  stdio: ["ignore", "pipe", "pipe"],
});
let log = "";
server.stdout.on("data", data => { log += data; });
server.stderr.on("data", data => { log += data; });
let browser;
let context;
try {
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(`Screenshot server exited: ${log}`);
    try { ready = (await fetch(`http://127.0.0.1:${port}`)).ok; } catch { /* Starting. */ }
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!ready) throw new Error(`Screenshot server did not start: ${log}`);
  browser = await chromium.launch({ channel: process.env.E2E_CHANNEL ?? (process.platform === "win32" ? "msedge" : "chrome"), headless: true });
  let page;
  const fresh = async () => {
    if (context) await context.close();
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1, reducedMotion: "reduce" });
    page = await context.newPage();
    await page.goto(`http://127.0.0.1:${port}/app`, { waitUntil: "networkidle" });
    await page.getByText("What should we work on?").waitFor();
    await page.evaluate(() => document.fonts.ready);
  };
  const mode = name => page.getByRole("group", { name: "Mode", exact: true }).getByRole("button", { name, exact: true });
  const shot = async name => {
    await page.screenshot({ path: path.join(output, `${name}.png`), animations: "disabled" });
    console.log(`Saved ${name}.png`);
  };
  await fresh();
  await shot("01-home");

  await mode("Thinker").click();
  await page.getByRole("button", { name: "Set up this mode" }).click();
  await page.getByRole("dialog").waitFor();
  await shot("02-thinker-setup");
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "detached" });
  await page.locator("textarea").fill("Compare solar and wind power for a small business.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByRole("button", { name: "Show agents" }).click();
  await page.getByText("All 3 agents finished").waitFor({ timeout: 30000 });
  await shot("03-thinker-answer");

  await fresh();
  await mode("Planner").click();
  await page.locator("textarea").fill("Make a 2-page PDF report on solar power.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByRole("button", { name: "Approve and run" }).waitFor({ timeout: 30000 });
  await shot("04-plan-approval");
  await page.getByRole("button", { name: "Approve and run" }).click();
  await page.getByText("solar_power_report.pdf", { exact: true }).waitFor({ timeout: 30000 });
  await page.getByRole("button", { name: "Send", exact: true }).waitFor({ timeout: 30000 });
  await shot("05-plan-output");
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null) {
    const ended = once(server, "exit");
    server.kill();
    await ended;
  }
}
