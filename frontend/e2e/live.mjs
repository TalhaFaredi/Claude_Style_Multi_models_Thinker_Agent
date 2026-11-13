/**
 * LIVE end-to-end test: the real frontend against the real backend and real (cheap) models.
 * It spends well under 1 cent. Needs both servers running:
 *   backend:  uvicorn app.main:app --port 8000
 *   frontend: built with NEXT_PUBLIC_API_URL=http://localhost:8000 and started (npm start)
 *   npm run test:live
 * Env: E2E_URL (default http://localhost:3000), E2E_CHANNEL (msedge|chrome), E2E_SHOTS.
 */
import { chromium } from "playwright-core";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const URL = process.env.E2E_URL ?? "http://localhost:3000";
const SHOTS = process.env.E2E_SHOTS ?? "./e2e/shots-live";
fs.mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch({ channel: process.env.E2E_CHANNEL ?? (process.platform === "win32" ? "msedge" : "chrome"), headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
const page = await context.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));

let failed = 0;
const check = (name, ok, extra = "") => { if (!ok) failed++; console.log(ok ? "PASS" : "FAIL", name, extra); };
const shot = (n) => page.screenshot({ path: `${SHOTS}/${n}.png` });
const T = { timeout: 120000 };
const visible = async (loc, timeout = 60000) => { try { await loc.first().waitFor({ state: "visible", timeout }); return true; } catch { return false; } };
const send = () => page.getByRole("button", { name: "Send", exact: true });
const mode = (n) => page.getByRole("group", { name: "Mode" }).getByRole("button", { name: n, exact: true });
const idle = () => send().waitFor({ state: "visible", ...T });
const ask = async (text) => { await page.locator("textarea").fill(text); await send().click(); };
const answer = async (text) => { await ask(text); await idle(); };
const closeDialog = async () => { await page.keyboard.press("Escape"); await page.getByRole("dialog").waitFor({ state: "detached", timeout: 5000 }).catch(() => {}); };
const money = (t) => Number((t.match(/\$([0-9.]+)/) ?? [])[1] ?? NaN);

// ------------------------------------------------------------ start: real models, real price
await page.goto(URL.replace(/\/$/, "") + "/app", { waitUntil: "networkidle" });
check("connects to the backend (no error screen)", await visible(page.getByText("What should we work on?"), 30000));
const estText = await page.locator(".costlink").innerText();
check("estimate comes from the server (a tiny real price, not $0.000)", /About \$0\.0+\d/.test(estText), estText);
await mode("Simple").click();
await page.getByRole("button", { name: "Set up this mode" }).click();
const dialog = page.getByRole("dialog");
check("real model registry in Setup (Qwen 3.7 Flash is the default)", await visible(dialog.getByRole("button", { name: /Qwen 3\.7 Flash/ })));
await dialog.getByRole("button", { name: /Qwen 3\.7 Flash/ }).click();
await page.locator(".mrow").first().waitFor({ state: "visible", timeout: 15000 });
const rows = await page.locator(".mrow").allInnerTexts();
check("model rows show real per-million prices", rows.some((r) => /per 1M tokens/.test(r)), rows[0]?.replace(/\n/g, " | ").slice(0, 90));
// The read-only provider probe cannot detect an inference-only 403, so unknown NVIDIA prices are the visible reason.
check("NVIDIA models are greyed with a reason", rows.some((r) => /NIM/.test(r) && /(not authorized|price unknown|pricing unavailable)/i.test(r)));
await shot("01-model-picker");
await page.getByRole("button", { name: "Done" }).click();
await closeDialog();
await mode("Simple").click();

// ------------------------------------------------------------ Simple, real answer and cost
await ask("What is a token in a language model? One short paragraph.");
check("no Auto routing note", !(await page.getByText(/Auto chose/).count()));
check("mode locked while the answer runs (F9)", await mode("Thinker").isDisabled());
await idle();
const meta = await page.locator(".foot").first().innerText();
check("answer has a real cost, not 'sample'", /calls? · cost \$0\.0+\d/.test(meta) && !/sample/.test(meta), meta.split("\n")[0]);
check("answer text streamed", (await page.locator(".answer").first().innerText()).length > 40);
const pct = Number((await page.locator(".meter .hint").innerText()).match(/\d+/)[0]);
check("memory meter shows the server's real window fill", pct > 0 && pct < 60, "pct=" + pct);
await page.locator(".meter").click();
check("context details show real token counts", await visible(page.getByText(/usable tokens/)));
await shot("02-context");
await closeDialog();
const month = await page.locator(".side-foot .hint").innerText();
check("month spend updated from the server", /\$0\.\d+ of/.test(month) && money(month) > 0, month);

// ------------------------------------------------------------ chat is saved, reload brings it back
await page.reload({ waitUntil: "networkidle" });
const row = page.locator(".chatrow").first();
check("chat appears in Recent after reload", await visible(row, 15000), await row.innerText().catch(() => ""));
await row.click();
check("opening it restores the saved answer", await visible(page.locator(".answer").first(), 15000));
check("restored message keeps its cost", /\$0\.0+\d/.test(await page.locator(".foot").first().innerText()));

// ------------------------------------------------------------ Thinker + Stop
await mode("Thinker").click();
await ask("Should a small team build its own search engine or use an existing service?");
check("Thinker shows team progress", await visible(page.getByText(/x .*(on their own|together)/)));
await page.getByRole("button", { name: "Show agents" }).click();
await page.locator(".agent").nth(2).waitFor(T);
check("agents have roles (Solver, Critic, Fact-checker)", /Solver/.test(await page.locator(".agents").innerText()));
await idle();
check("Thinker finishes with a composed answer", (await page.locator(".answer").last().innerText()).length > 60);
await shot("03-thinker");
await ask("Compare five databases for a startup in great detail.");
await page.getByRole("button", { name: "Stop" }).click();
check("Stop keeps what was done", await visible(page.getByText("Stopped. What was done is kept.")));

// ------------------------------------------------------------ Planner: approval gate, edit, PDF
await mode("Planner").click();
await ask("Make a 1-page PDF report on why drinking water should be conserved");
check("plan waits for approval", await visible(page.getByRole("button", { name: "Approve and run" })));
check("nothing runs before approval (F10)", (await page.locator(".step .pill", { hasText: /Running|Checking|Done/ }).count()) === 0);
check("plan shows the server's cost estimate", /About \$0\.\d+/.test(await page.locator(".card", { hasText: "Approve and run" }).first().innerText()));
await page.getByRole("button", { name: "Edit", exact: true }).click();
await page.getByPlaceholder(/What should change/).fill("Keep it to three short sections");
await page.getByRole("button", { name: "Re-plan" }).click();
check("Edit re-plans and shows the plan again (C15)", await visible(page.getByRole("button", { name: "Approve and run" }), 90000));
await shot("04-plan");
await page.getByRole("button", { name: "Approve and run" }).click();
check("plan finishes", await visible(page.getByText(/is ready:/), 240000));
const dl = page.getByRole("link", { name: "Download" });
const href = await dl.getAttribute("href");
check("output card links to the real PDF", /\/api\/artifacts\//.test(href ?? ""), href);
const pdf = await context.request.get(href);
check("the PDF downloads and is a real PDF", pdf.ok() && (await pdf.body()).subarray(0, 4).toString() === "%PDF");
await idle();
await shot("05-plan-done");

// ------------------------------------------------------------ a file: upload, price, read, cited answer
await mode("Simple").click();
await page.getByRole("button", { name: "Attach a file" }).click();
const txt = path.join(os.tmpdir(), "orion_pump_notes.txt");
fs.writeFileSync(txt, `Orion pump service notes (run ${Date.now()}).\n\n` + "General housekeeping paragraph about the plant room. ".repeat(40) + "\n\nSpecification: the Orion pump has a rated flow of 840 liters per minute and a maximum pressure of 6.5 bar.\n\n" + "More routine text about logbooks. ".repeat(40));
await page.locator('input[type="file"]').setInputFiles(txt);
check("upload shows the free page check", await visible(page.getByText(/Pages checked for free/)));
check("price shown before reading (text pages free; only the meaning index costs)", await visible(page.getByText("Free text reading")) && await visible(page.getByText(/Approved maximum \$0\.0/)));
await shot("06-file");
await page.getByRole("button", { name: /Read file/ }).click();
check("file chip becomes Ready", await visible(page.locator(".fchip", { hasText: "Ready" }), 90000));
await page.locator(".fchip-open").first().click();
// Scope to the dialog: "Summary" also appears in earlier answers, and Escape must not race the lazily loaded dialog.
check("Document Card shows a real summary", await visible(page.getByRole("dialog").getByText("Summary")));
await closeDialog();
await answer("What is the rated flow of the Orion pump and its maximum pressure?");
const ans = await page.locator(".answer").last().innerText();
check("answer uses the file (840 liters / 6.5 bar)", /840/.test(ans) && /6\.5/.test(ans) && !/could not find support/i.test(ans), ans.slice(0, 90).replace(/\n/g, " "));
check("answer cites the file and page", (await page.locator(".cite").count()) > 0 || /orion_pump_notes/.test(ans));
// same file again: read before -> $0
const stray = await page.getByRole("dialog").allInnerTexts();
if (stray.length) { console.log("   open dialog after the file answer:", stray.map((d) => d.slice(0, 200).replace(/\n/g, " | "))); await shot("06b-stray-dialog"); }
check("no dialog left open after the file answer", stray.length === 0);
if (stray.length) await closeDialog();
await page.getByRole("button", { name: "Attach a file" }).click();
await page.locator('input[type="file"]').setInputFiles(txt);
check("same file again says: read before, $0", await visible(page.getByText(/saved reading is reused/)));
await closeDialog();

// ------------------------------------------------------------ memory: the model remembers a fact across chats
await page.getByRole("button", { name: "New chat" }).click();
check("New chat clears the screen", await visible(page.getByText("What should we work on?")));
await answer("Please remember: my favorite color is teal and my project is called Nimbus.");
await page.waitForTimeout(8000); // the Memory Writer runs after the reply
await page.getByRole("button", { name: "New chat" }).click();
await answer("What is my project called, and what is my favorite color?");
const mem = await page.locator(".answer").last().innerText();
check("long-term memory works across chats", /nimbus/i.test(mem) && /teal/i.test(mem), mem.slice(0, 80).replace(/\n/g, " "));
await page.getByRole("button", { name: /Settings, memory, data/ }).click();
await page.getByRole("tab", { name: "Memory" }).click();
check("Memory tab lists the remembered facts with sources", await visible(page.getByText(/Nimbus/i)));
await shot("07-memory");
await closeDialog();

// ------------------------------------------------------------ auto-compaction (small window so it is quick and cheap)
await page.getByRole("button", { name: /Settings, memory, data/ }).click();
await page.getByRole("tab", { name: "Memory" }).click();
await page.getByRole("group", { name: "Working window" }).getByRole("button", { name: "8k", exact: true }).click();
await closeDialog();
await page.getByRole("button", { name: "New chat" }).click();
await mode("Simple").click();
await answer("My ticket number is TCK-48213, the budget is $48,250 and the deadline is 2026-03-14. Reply with just OK.");
const filler = "Background text for the long chat: " + "the quick brown fox jumps over the lazy dog. ".repeat(55);
let compactSeen = false, levels = [];
for (let i = 0; i < 14 && !compactSeen; i++) {
  await ask(filler + ` Part ${i}. Reply with just OK.`);
  const dlg = page.getByRole("dialog", { name: "Summarizing safely" });
  compactSeen = await dlg.waitFor({ state: "visible", timeout: 25000 }).then(() => true).catch(() => false);
  if (!compactSeen) await idle();
  levels.push(Number((await page.locator(".meter .hint").innerText()).match(/\d+/)[0]));
}
console.log("   window fill per message:", levels.join("% "), "%");
check("auto-compaction dialog appears at 95% with no click", compactSeen);
if (compactSeen) {
  check("dialog shows the four checked steps", (await page.getByRole("dialog").getByText("Check, then swap").count()) === 1);
  await shot("08-compacting");
  await page.getByRole("dialog", { name: "Summarizing safely" }).waitFor({ state: "detached", timeout: 90000 });
  check("a note says older messages were summarized, nothing deleted", await visible(page.getByText(/Older messages summarized/)));
  await idle().catch(() => {});
  const after = Number((await page.locator(".meter .hint").innerText()).match(/\d+/)[0]);
  check("the window dropped after summarizing", after < levels[levels.length - 1], `${levels[levels.length - 1]}% -> ${after}%`);
  await answer("What are the ticket number, the budget and the deadline I told you at the start?");
  const rec = await page.locator(".answer").last().innerText();
  check("after compaction the assistant still knows the planted facts", /TCK-48213/.test(rec) && /48,250/.test(rec) && /2026-03-14/.test(rec), rec.slice(0, 110).replace(/\n/g, " "));
  await shot("09-after-compaction");
}

// ------------------------------------------------------------ export, import, delete
await page.getByRole("button", { name: /Settings, memory, data/ }).click();
await page.getByRole("tab", { name: "Data and safety" }).click();
await page.getByText("Download this chat").click();
const lockAvailable = await visible(page.getByText("Lock with a password"), 5000);
check("password lock is offered (or honestly unavailable)", lockAvailable || await visible(page.getByText(/Password lock is not available/), 2000));
const PASS = "e2e-secret-42";
if (lockAvailable) {
  await page.getByText("Lock with a password").click();
  await page.getByLabel("Password").fill(PASS);
}
const [download] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }), page.getByRole("button", { name: "Download .zip" }).click()]);
const zipPath = path.join(os.tmpdir(), "mma_export.zip");
await download.saveAs(zipPath);
check("the chat downloads as a .zip", fs.statSync(zipPath).size > 500 && download.suggestedFilename().endsWith(".zip"), download.suggestedFilename());
await page.getByRole("button", { name: /Settings, memory, data/ }).click();
await page.getByRole("tab", { name: "Data and safety" }).click();
await page.getByText("Import a chat").click();
if (lockAvailable) await page.getByRole("dialog").locator('input[type="password"]').fill(PASS);
await page.locator('input[type="file"]').setInputFiles(zipPath);
check("import reports restored messages and $0 reading", await visible(page.getByText(/messages, .* files, .* facts restored\. Reading cost \$0/), 60000));
await shot("10-import");
await page.getByRole("button", { name: "Open the chat" }).click();
check("the imported chat opens", await visible(page.locator(".user").first(), 15000));
// delete a chat: asks about memories (C42)
await page.locator(".chatline").first().hover();
await page.getByRole("button", { name: /Delete chat/ }).first().click();
check("delete asks what to do with the memories", await visible(page.getByText(/Delete the chat, keep its memories/)));
await shot("11-delete");
const before = await page.locator(".chatrow").count();
await page.getByText("Delete the chat, keep its memories").click();
await page.waitForTimeout(1500);
check("the chat is removed from Recent", (await page.locator(".chatrow").count()) === before - 1, `${before} -> ${await page.locator(".chatrow").count()}`);

// ------------------------------------------------------------ keyboard + errors
console.log("\nconsole/page errors:", errors.length ? errors : "none");
console.log(failed === 0 && errors.length === 0 ? "\nALL GOOD" : `\n${failed} FAILED`);
await browser.close();
process.exit(failed === 0 && errors.length === 0 ? 0 : 1);
