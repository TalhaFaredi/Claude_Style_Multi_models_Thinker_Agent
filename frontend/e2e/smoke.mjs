/**
 * Click-through smoke test of every mode and guardrail (spec Part 3 §11: "each guardrail and
 * each mode flow as a click test"). Runs against a started app on the mock runner.
 *
 *   npm run build && npm start          # in one terminal
 *   npm run test:e2e                    # in another
 *
 * Env: E2E_URL (default http://localhost:3000), E2E_CHANNEL (msedge | chrome, default msedge on
 * Windows else chrome), E2E_SHOTS (folder for screenshots, default ./e2e/shots).
 */
import { chromium } from "playwright-core";
import fs from "node:fs";

const URL = process.env.E2E_URL ?? "http://localhost:3000";
const SHOTS = process.env.E2E_SHOTS ?? "./e2e/shots";
fs.mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch({ channel: process.env.E2E_CHANNEL ?? (process.platform === "win32" ? "msedge" : "chrome"), headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));

let failed = 0;
const check = (name, ok, extra = "") => { if (!ok) failed++; console.log(ok ? "PASS" : "FAIL", name, extra); };
const shot = (n) => page.screenshot({ path: `${SHOTS}/${n}.png` });
const T = { timeout: 30000 };
const visible = async (loc) => { try { await loc.first().waitFor({ state: "visible", timeout: 30000 }); return true; } catch { return false; } };

const send = () => page.getByRole("button", { name: "Send", exact: true });
const mode = (n) => page.getByRole("group", { name: "Mode" }).getByRole("button", { name: n, exact: true });
const ask = async (text) => { await page.locator("textarea").fill(text); await send().click(); };
const closeDialog = async () => { await page.keyboard.press("Escape"); await page.getByRole("dialog").waitFor({ state: "detached" }).catch(() => {}); };

await page.goto(URL, { waitUntil: "networkidle" });
check("empty state greeting", await visible(page.getByText("What should we work on?")));
check("4 mode cards", (await page.locator(".modecard").count()) === 4);
check("F1 send disabled when empty", await send().isDisabled());
await shot("01-empty");

// ---------- Auto -> Simple, streaming, F9 lock
await ask("What is a token?");
check("Auto routing note", await visible(page.getByText("Auto chose Simple")));
check("F9 mode locked while running", await mode("Thinker").isDisabled());
check("Stop button + lock pill while running", (await page.getByRole("button", { name: "Stop" }).isVisible()) && (await page.getByText("Working, mode locked").isVisible()));
await shot("02-simple-running");
check("Simple answer finishes with Think deeper", await visible(page.getByRole("button", { name: "Think deeper" })));
check("tool chip + citations", (await page.getByText("Used 3 web sources").isVisible()) && (await page.locator(".cite").count()) === 3);
check("answer streamed", (await page.locator(".answer").first().innerText()).includes("sample answer"));
check("meta line has cost", await page.locator(".foot").first().innerText().then((t) => /calls/.test(t)));
check("mode unlocked after done", await mode("Thinker").isEnabled());
await shot("03-simple-done");

// ---------- Think deeper -> Thinker
await page.getByRole("button", { name: "Think deeper" }).click();
check("Thinker progress line", await visible(page.getByText("3 x Claude Sonnet 5.5, on their own")));
await page.getByRole("button", { name: "Show agents" }).click();
await page.locator(".agent").nth(2).waitFor(T);
check("3 agent cards", (await page.locator(".agent").count()) === 3);
await shot("04-thinker-running");
check("Thinker finishes", await visible(page.getByText("All 3 agents finished")));
await shot("05-thinker-done");

// ---------- Planner: nothing runs before Approve (F10)
await mode("Planner").click();
await ask("Make a 2-page PDF report on solar power");
check("plan waits for approval", await visible(page.getByRole("button", { name: "Approve and run" })));
const runningBefore = await page.locator(".step .pill", { hasText: "Running" }).count();
check("F10 no step running before approval", runningBefore === 0);
check("Stop is the only way out, mode locked", await mode("Auto").isDisabled());
await shot("06-plan-approval");
await page.getByRole("button", { name: "Approve and run" }).click();
check("plan runs a retry note", await visible(page.getByText("Retry 1 of 2")));
check("output card appears", await visible(page.getByText("solar_power_report.pdf")));
check("planner done message", await visible(page.getByText("All 4 steps passed their checks")));
await shot("07-plan-done");

// ---------- Stop keeps progress
await mode("Simple").click();
await ask("Explain context windows");
await page.getByRole("button", { name: "Stop" }).click();
check("Stopped message", await visible(page.getByText("Stopped. What was done is kept.")));
check("send available after Stop", await send().isVisible());

// ---------- Setup dialog: F3 limits, over-budget (F7)
await mode("Thinker").click();
await page.getByRole("button", { name: "Set up this mode" }).click();
check("Setup dialog opens (lazy chunk)", await visible(page.getByRole("dialog", { name: "Set up Thinker" })));
for (let i = 0; i < 4; i++) await page.getByRole("button", { name: "More agents" }).click();
check("F3 stepper stops at 5 with toast", await visible(page.getByText("At most 5 agents")));
check("agent count 5", (await page.locator(".stepper-val").first().innerText()) === "5");
await page.getByRole("button", { name: /^Model: / }).click();
await page.getByRole("button", { name: /Claude Opus 5.5/ }).click();
await shot("08-model-picker");
await page.getByRole("button", { name: "Done" }).click();
check("back in Setup after picker", await visible(page.getByRole("dialog", { name: "Set up Thinker" })));
await page.getByRole("button", { name: /Different models/ }).click();
await page.getByRole("button", { name: /Pick models/ }).click();
// deselect down to 2, then try to go below
await page.getByRole("button", { name: /GPT \(latest\)/ }).click();
await page.getByRole("button", { name: /Gemini Pro/ }).click();
check("F3 cannot go below 2 models", await visible(page.getByText("Needs at least 2 models")));
await page.getByRole("button", { name: "Done" }).click();
// F13 mixed strength
await page.getByRole("button", { name: /Pick models/ }).click();
await page.getByRole("button", { name: /Llama 3.3/ }).click();
await page.getByRole("button", { name: /Claude Opus 5.5/ }).click().catch(() => {});
await page.getByRole("button", { name: "Done" }).click();
await shot("09-setup-thinker");
await page.getByRole("button", { name: /Same model/ }).click();
await page.getByRole("button", { name: "Done" }).last().click();
await page.locator("textarea").fill("Compare two options");
await send().click();
check("F7 cost dialog before spending", await visible(page.getByRole("dialog", { name: "Over your budget" })));
await shot("10-cost-dialog");
await page.getByText("Make it cheaper").click();
check("cheaper toast", await visible(page.getByText("Cheaper setup chosen")));

// ---------- Files
await page.getByRole("button", { name: "Attach a file" }).click();
await page.getByRole("dialog").getByRole("button", { name: /Q3_Report.pdf/ }).click();
check("file plan total $0.07", await visible(page.getByText("Total about $0.07")));
await shot("11-file-plan");
await page.getByRole("button", { name: /Read file \(\$0.07\)/ }).click();
check("file chip Reading then Ready", await visible(page.locator(".fchip", { hasText: "Ready" })));
await page.getByRole("button", { name: "Attach a file" }).click();
check("Read before marker", await visible(page.getByText("Read before · $0")));
await page.getByRole("dialog").getByRole("button", { name: /Q3_Report.pdf/ }).click();
check("reused reading costs $0", await visible(page.getByText("The saved reading is reused")));
await closeDialog();

// ---------- Context: auto-compact at 95% (C37), then alarm at 85% (C36)
// context is ~93% here; one more answer crosses 95% and (auto-summary is on by default) compacts by itself
await mode("Simple").click();
await ask("Push the window over 95 percent");
check("C37 auto-compact at 95%", await visible(page.getByText("Older messages summarized")));
await page.getByRole("dialog").waitFor({ state: "detached", timeout: 30000 }).catch(() => {});
await page.getByRole("button", { name: /Settings, memory, data/ }).click();
await page.getByRole("tab", { name: "Memory" }).click();
await page.getByRole("switch", { name: /Summarize automatically/ }).click();
check("auto-summary switched off", (await page.getByRole("switch", { name: /Summarize automatically/ }).getAttribute("aria-checked")) === "false");
await closeDialog();
await mode("Simple").click();
const alarm = page.getByRole("alert").filter({ hasText: "full" });
for (let i = 0; i < 9 && !(await alarm.isVisible()); i++) {
  await ask("Another short question " + i);
  await page.getByRole("button", { name: "Send", exact: true }).waitFor({ state: "visible", timeout: 30000 });
}
const pct = Number((await page.locator(".meter .hint").innerText()).match(/\d+/)[0]);
check("context reached the 85% alarm", pct >= 85 && pct < 95, "pct=" + pct);
await shot("12-alarm");
check("alarm banner with 4 buttons", (await alarm.isVisible()) && (await alarm.getByRole("button").count()) === 4);
await alarm.getByRole("button", { name: "Later" }).click();
check("Later hides alarm until 90%", !(await alarm.isVisible()));
await ask("One more question");
await page.getByRole("button", { name: "Send", exact: true }).waitFor({ state: "visible", timeout: 30000 });
check("alarm returns at 90%+", await visible(alarm));
await alarm.getByRole("button", { name: "Summarize now" }).click();
check("Summarizing dialog (no close button)", (await visible(page.getByRole("dialog", { name: "Summarizing safely" }))) && (await page.getByRole("dialog").getByRole("button", { name: "Close" }).count()) === 0);
await page.getByRole("dialog").waitFor({ state: "detached", timeout: 30000 });
check("context dropped to 34%", (await page.locator(".meter .hint").innerText()).includes("34"));

// ---------- Settings, memory delete, export, import
await page.getByRole("button", { name: /Settings, memory, data/ }).click();
check("Settings dialog", await visible(page.getByRole("dialog", { name: "Settings" })));
await page.getByRole("tab", { name: "Memory" }).click();
await page.getByRole("button", { name: "Delete" }).first().click();
check("F11 delete asks Keep or Delete", (await page.getByRole("button", { name: "Keep" }).isVisible()));
await page.getByRole("button", { name: "Keep" }).click();
await page.getByRole("tab", { name: "Data and safety" }).click();
await page.getByText("Import a chat").click();
await page.getByRole("button", { name: "Choose chat_export.zip" }).click();
check("import report", await visible(page.getByText("142 messages, 3 files, 21 facts restored")));
await shot("13-import");
await page.getByRole("button", { name: "Open the chat" }).click();
check("imported chat opened", await visible(page.getByText('Imported "System design review"')));

// ---------- keyboard: Escape closes, focus returns
await page.getByRole("button", { name: /Memory window/ }).focus();
await page.keyboard.press("Enter");
check("context dialog", await visible(page.getByRole("dialog", { name: /Memory window/ })));
await page.keyboard.press("Escape");
await page.getByRole("dialog").waitFor({ state: "detached" });
check("Escape closes, focus returns to trigger", await page.evaluate(() => document.activeElement?.className.includes("meter")));

// ---------- phone viewport
await page.setViewportSize({ width: 390, height: 844 });
await page.reload({ waitUntil: "networkidle" });
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
check("no horizontal scroll on phone", !overflow);
await shot("14-phone");

// ---------- persisted prefs survive reload (settings saved per user)
const stored = await page.evaluate(() => Object.keys(localStorage));
check("preferences persisted", stored.includes("mma-settings") && stored.includes("mma-chat-config"), stored.join(","));

console.log("\nconsole/page errors:", errors.length ? errors : "none");
console.log(failed === 0 && errors.length === 0 ? "\nALL GOOD" : `\n${failed} FAILED`);
await browser.close();
process.exit(failed === 0 && errors.length === 0 ? 0 : 1);
