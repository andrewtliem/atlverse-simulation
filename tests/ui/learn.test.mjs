// Browser test of the learning aids: the guided tutorial done as a student would, the
// reading of results, charts and the glossary. Needs a running server, like editor.test.mjs.
const PW = process.env.PLAYWRIGHT_CORE || "playwright-core";   // set PLAYWRIGHT_CORE to a playwright-core index.mjs if it is not installed here
const { chromium } = await import(PW);
const out = process.argv[2] || "/tmp";
const browser = await chromium.launch({ headless: true, channel: process.env.PW_CHANNEL || "chrome" });
const page = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
const errors = [];
page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", e => errors.push("pageerror: " + e.message));
page.on("dialog", d => { errors.push("unexpected dialog: " + d.message()); d.dismiss(); });
let step = 0;
const check = (name, ok, detail = "") => console.log(`${ok ? "PASS" : "FAIL"} ${++step}. ${name}${detail ? " — " + detail : ""}`);
const stage = page.locator("#stage"), side = page.locator("#side");
const nodeBy = name => page.locator(".node", { has: page.locator("text", { hasText: name }) }).first();
const tourState = () => page.textContent("#tourstate");
const next = () => page.click("#tournext");
const waitOk = async () => { await page.waitForFunction(() => document.getElementById("tourstate")?.classList.contains("ok"), null, { timeout: 60000 }); };

await page.goto("http://127.0.0.1:8765/");
await page.evaluate(() => localStorage.clear());
await page.reload(); await page.waitForSelector(".node");

// glossary
await page.keyboard.press("F1");
check("F1 opens Help", await page.locator("#help").isVisible() && await page.locator("#helplist details").count() > 40);
await page.fill("#helpq", "half width");
check("Help search filters", (await page.locator("#helplist details").count()) < 6 && (await page.textContent("#helplist")).includes("selang kepercayaan"));
await page.click("#helpclose");

// tutorial
await page.click("#btour");
check("tutorial menu lists 4 tutorials", await page.locator("#tour [data-tour]").count() === 4);
await page.click('#tour [data-tour="bank"]');
check("tutorial opens", (await page.textContent("#tour")).includes("Model pertama"));
await next();   // Mulai: new model
check("tutorial starts a new model", await page.locator(".node").count() === 0);
check("step 1 waits and highlights Create", (await tourState()).includes("Belum") && await page.locator('.pal[data-kind="create"].tut-hl').count() === 1 && await page.locator("#tournext").isDisabled());
await page.click('.pal[data-kind="create"]'); await stage.click({ position: { x: 120, y: 160 } });
await waitOk(); check("placing Create completes step 1", true); await next();
await nodeBy("Create").locator("rect.body").click();
await side.getByLabel("Name", { exact: true }).fill("Nasabah Datang");
await side.getByLabel("Entity Type").fill("Nasabah");
await side.getByLabel("Value", { exact: true }).fill("5");
await side.getByLabel("Units").selectOption("Minutes");
check("module dialog shows a module explanation", (await side.textContent()).includes("Selengkapnya"));
await waitOk(); await next();
await page.click('.pal[data-kind="process"]'); await stage.click({ position: { x: 330, y: 160 } });
await waitOk(); check("Auto-Connect links Create to Process", true); await next();
await nodeBy("Process").locator("rect.body").click();
await side.getByLabel("Name", { exact: true }).fill("Layanan Teller");
await side.getByLabel("Resources 1 Resource Name").fill("Teller");
await side.getByLabel("Minimum").fill("3");
await side.getByLabel("Value (Most Likely)").fill("4");
await side.getByLabel("Maximum").fill("6");
await side.getByLabel("Units").selectOption("Minutes");
await waitOk(); await next();
await page.click('.pal[data-kind="dispose"]'); await stage.click({ position: { x: 540, y: 160 } });
check("step lists what is missing", (await tourState()).includes('Ada modul Dispose bernama "Nasabah Pulang"'), await tourState());
await side.getByLabel("Name", { exact: true }).fill("Nasabah Pulang");
await waitOk(); await next();
check("theory step explains rho", (await page.textContent("#tour")).includes("87%")); await next();
await page.click("#bsetup");
const dlg = page.locator("#setupdlg");
await dlg.getByLabel("Number of Replications").fill("5");
await dlg.getByLabel("Replication Length", { exact: true }).fill("8");
await dlg.getByLabel("Replication Length Time Units").selectOption("Hours");
await dlg.locator("#setupok").click();
await page.click("#brun");
await page.waitForSelector("#anibar.on", { timeout: 30000 });
await page.click("#bff");
await waitOk(); await next();
const tourText = await page.textContent("#tour");
check("reading step quotes this run's utilization", /Utilization Teller: \d+\.\d%/.test(tourText), tourText.slice(0, 200));

// reading aids in the Summary
const learn = await page.textContent("#sum-learn");
check("Summary explains the results", learn.includes("Cara membaca hasil") && learn.includes("Teller") && learn.includes("Hukum Little"), learn.slice(0, 300));
check("charts drawn", await page.locator("#p-summary .chart svg").count() >= 3, String(await page.locator("#p-summary .chart svg").count()));
check("column headers link to the glossary", await page.locator('#p-summary th .term[data-term="inst_util"]').count() === 1);
await page.locator('#p-summary th .term[data-term="half_width"]').first().click();
check("clicking a term opens its entry", await page.locator("#help").isVisible() && await page.locator("#h-half_width[open]").count() === 1);
await page.click("#helpclose");
await page.screenshot({ path: out + "/learn_summary.png" });
await next();

// experiment: second teller
await page.click("#bend");
await page.click('.pal.data[data-table="resources"]');
await page.getByLabel("Teller Capacity").fill("2");
await page.waitForTimeout(700);
await page.locator("#p-summary tr.click").first().click().catch(() => {});
await page.click("#brun");
await page.waitForSelector("#anibar.on", { timeout: 30000 });
await page.click("#bff");
await waitOk(); await next();
const cmp = await page.textContent("#tour");
check("comparison step shows both scenarios", cmp.includes("1 teller") && cmp.includes("2 teller"), cmp.slice(0, 260));
await page.screenshot({ path: out + "/learn_compare.png" });
await next();
check("tutorial finishes", (await page.textContent("#tour")).includes("Selesai")); await next();
check("tutorial closes", !(await page.locator("#tour").isVisible()));

// a resource row in the Summary leads to its module
await page.click("#bend");
await page.locator("#p-summary table.res tr.click", { hasText: "Teller" }).first().click();
check("report row selects its module", (await side.getByLabel("Name", { exact: true }).inputValue()).includes("Layanan Teller"));
check("no console errors", errors.length === 0, errors.join(" | "));
await browser.close();
