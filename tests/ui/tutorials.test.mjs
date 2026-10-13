// Browser test: the Decide, Assign and Schedule tutorials done step by step as a student would.
// Needs a running server, like editor.test.mjs.
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
const body = name => nodeBy(name).locator("rect.body");
const next = () => page.click("#tournext");
const waitOk = async (what) => {
  try { await page.waitForFunction(() => document.getElementById("tourstate")?.classList.contains("ok"), null, { timeout: 60000 }); }
  catch (e) { check(what + " (step not completed)", false, await page.textContent("#tourstate")); throw e; }
};
const place = async (kind, x, y, after) => {
  if (after) await body(after).click();
  await page.evaluate(k => { const b = document.querySelector(`.pal[data-kind="${k}"]`).closest(".pbbody"); if (b.hidden) b.previousElementSibling.click(); }, kind);
  await page.click(`.pal[data-kind="${kind}"]`); await stage.click({ position: { x, y } });
};
const name = v => side.getByLabel("Name", { exact: true }).fill(v);
const tria = async (a, b, c) => {
  await side.getByLabel("Delay Type").selectOption("Triangular");
  await side.getByLabel("Minimum").fill(String(a)); await side.getByLabel("Value (Most Likely)").fill(String(b)); await side.getByLabel("Maximum").fill(String(c));
  await side.getByLabel("Units").selectOption("Minutes");
};
const create = async (nm, et, mean) => {
  await place("create", 90, 110); await name(nm);
  await side.getByLabel("Entity Type").fill(et); await side.getByLabel("Value", { exact: true }).fill(String(mean)); await side.getByLabel("Units").selectOption("Minutes");
};
const run = async (reps, hours) => {
  if (await page.locator("#anibar").isVisible()) await page.click("#bend");
  await page.click("#bsetup");
  const dlg = page.locator("#setupdlg");
  await dlg.locator(".dlgtabs button", { hasText: "Replication Parameters" }).click();
  await dlg.getByLabel("Number of Replications").fill(String(reps));
  await dlg.getByLabel("Replication Length", { exact: true }).fill(String(hours));
  await dlg.getByLabel("Replication Length Time Units").selectOption("Hours");
  await dlg.locator("#setupok").click();
  await page.click("#brun");
  await page.waitForSelector("#anibar.on", { timeout: 60000 });
  await page.click("#bff");
};
const startTutorial = async key => {
  await page.click("#btour"); await page.click(`#tour [data-tour="${key}"]`); await next();   // Mulai = new model
};
const tourText = () => page.textContent("#tour");

await page.goto("http://127.0.0.1:8765/");
await page.evaluate(() => localStorage.clear());
await page.reload(); await page.waitForSelector(".node");

// ---------------------------------------------------------------- Decide
await startTutorial("decide");
await create("Part Datang", "Part", 10); await waitOk("decide create"); await next();
await place("process", 270, 110, "Part Datang"); await name("Inspeksi");
await side.getByLabel("Resources 1 Resource Name").fill("Inspektor"); await tria(4, 5, 7);
await waitOk("decide inspeksi"); await next();
await place("decide", 450, 110, "Inspeksi"); await name("Lulus?");
await side.getByLabel("Percent True (0-100)").fill("80");
await waitOk("decide lulus"); await next();
await place("dispose", 640, 60, "Lulus?"); await name("Part Bagus"); await waitOk("decide bagus"); await next();
await place("process", 640, 230, "Lulus?"); await name("Perbaikan");
await side.getByLabel("Resources 1 Resource Name").fill("Teknisi"); await tria(10, 15, 20);
await waitOk("decide perbaikan"); await next();
await nodeBy("Perbaikan").locator("circle.port").nth(1).dragTo(body("Inspeksi"));
await waitOk("decide loop"); await next();
check("theory step: 1.25 inspections per part", (await tourText()).includes("1.25 kali")); await next();
await run(5, 8); await waitOk("decide run"); await next();
const dRead = await tourText();
check("Decide reading shows inspections per part", /= \d\.\d+<?\/?b?>? ?kali per part|kali per part/.test(dRead) && dRead.includes("Inspektor"), dRead.slice(0, 260));
await next();
// by Condition
await page.click("#bend"); await page.click("#tclose");
await page.evaluate(() => {   // select the link Perbaikan -> Inspeksi (as clicking it does), then Delete removes it
  const id = n => model.nodes.find(x => x.props.name === n).id;
  const i = model.links.findIndex(l => l.from === id("Perbaikan") && l.to === id("Inspeksi"));
  document.querySelectorAll("#links path")[2 * i + 1].dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
});
await page.keyboard.press("Delete");
await place("assign", 640, 360, "Perbaikan"); await name("Tandai");
await side.getByLabel("Assignments 1 Type").selectOption("Attribute");
await side.getByLabel("Assignments 1 Attribute Name").fill("Sudah Diperbaiki"); await side.getByLabel("Assignments 1 New Value").fill("1");
await nodeBy("Tandai").locator("circle.port").nth(1).dragTo(body("Inspeksi"));
// second Decide on the False branch: re-route Lulus? (False) through it
await page.evaluate(() => {
  const id = n => model.nodes.find(x => x.props.name === n).id;
  const i = model.links.findIndex(l => l.from === id("Lulus?") && l.port === "false");
  document.querySelectorAll("#links path")[2 * i + 1].dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
});
await page.keyboard.press("Delete");
await place("decide", 450, 260, "Lulus?"); await name("Boleh Diperbaiki?");
await side.getByLabel("Type", { exact: true }).selectOption("2-way by Condition");
await side.getByLabel("Value", { exact: true }).fill("Sudah Diperbaiki == 0");
await place("dispose", 450, 380, null);
await name("Part Ditolak");
await nodeBy("Boleh Diperbaiki?").locator("circle.port").nth(1).dragTo(body("Perbaikan"));
await nodeBy("Boleh Diperbaiki?").locator("circle.port").nth(2).dragTo(body("Part Ditolak"));
await page.waitForTimeout(500);
await run(5, 8); await waitOk("decide by condition"); await next();
const dCmp = await tourText();
check("Decide comparison table", dCmp.includes("maks. 1 kali") && dCmp.includes("Perbaikan per part"), dCmp.slice(0, 300));
await page.screenshot({ path: out + "/tut_decide.png" });
await next(); check("Decide tutorial finishes", (await tourText()).includes("Selesai")); await next();

// ---------------------------------------------------------------- Assign
if (await page.locator("#anibar").isVisible()) await page.click("#bend");
await startTutorial("assign");
await create("Pasien Datang", "Pasien", 8); await waitOk("assign create"); await next();
await place("assign", 270, 110, "Pasien Datang"); await name("Data Pasien"); await waitOk("assign place"); await next();
await side.getByLabel("Assignments 1 Type").selectOption("Attribute");
await side.getByLabel("Assignments 1 Attribute Name").fill("Waktu Datang"); await side.getByLabel("Assignments 1 New Value").fill("TNOW");
await waitOk("assign waktu"); await next();
await side.locator("button", { hasText: "+ Add assignment" }).click();
await side.getByLabel("Assignments 2 Type").selectOption("Attribute");
await side.getByLabel("Assignments 2 Attribute Name").fill("Jenis"); await side.getByLabel("Assignments 2 New Value").fill("DISC(0.7, 1, 1.0, 2)");
await waitOk("assign jenis"); await next();
await side.locator("button", { hasText: "+ Add assignment" }).click();
await side.getByLabel("Assignments 3 Type").selectOption("Variable");
await side.getByLabel("Assignments 3 Variable Name").fill("Jumlah Pasien"); await side.getByLabel("Assignments 3 New Value").fill("Jumlah Pasien + 1");
await waitOk("assign variable"); await next();
await place("process", 450, 110, "Data Pasien"); await name("Pemeriksaan");
await side.getByLabel("Resources 1 Resource Name").fill("Dokter");
await side.getByLabel("Delay Type").selectOption("Expression");
await side.getByLabel("Expression", { exact: true }).fill("TRIA(3, 4, 6) * Jenis"); await side.getByLabel("Units").selectOption("Minutes");
await waitOk("assign pemeriksaan"); await next();
await place("record", 630, 110, "Pemeriksaan"); await name("Lama di Klinik");
await side.getByLabel("Type", { exact: true }).selectOption("Time Interval"); await side.getByLabel("Attribute Name").fill("Waktu Datang");
await waitOk("assign record"); await next();
await place("dispose", 630, 260, "Lama di Klinik"); await name("Pasien Pulang"); await waitOk("assign dispose"); await next();
await page.click('.pal.data[data-table="variables"]');
await page.getByLabel("Jumlah Pasien Report Statistics").check();
await waitOk("assign report"); await next();
await run(5, 8); await waitOk("assign run"); await next();
const aRead = await tourText();
check("Assign reading: tally equals Total Time, counter equals Number In", /Lama di Klinik = (\S+) menit, sama dengan Total Time entity Pasien \((\S+)\)/.test(aRead.replace(/\s+/g, " ")) && aRead.includes("Jumlah Pasien"), aRead.slice(0, 400));
const [, tl, tt] = aRead.replace(/\s+/g, " ").match(/Lama di Klinik = (\S+) menit, sama dengan Total Time entity Pasien \(([^)]+)\)/) || [];
check("tally and Total Time agree", tl && tl === tt, `${tl} vs ${tt}`);
await page.screenshot({ path: out + "/tut_assign.png" });
await next(); await next();

// ---------------------------------------------------------------- Schedule
if (await page.locator("#anibar").isVisible()) await page.click("#bend");
await startTutorial("schedule");
await place("create", 90, 110); await name("Nasabah Datang");
await side.getByLabel("Entity Type").fill("Nasabah"); await side.getByLabel("Type", { exact: true }).selectOption("Schedule");
await side.getByLabel("Schedule Name").fill("Pola Kedatangan");
await waitOk("schedule create"); await next();
const fillSched = async (nm, base, peak) => {
  await page.click('.pal.data[data-table="schedules"]');
  await page.getByLabel(`Edit ${nm} graphically`).first().click();
  const d = page.locator("#scheddlg");
  await d.getByLabel("other hours = 0").uncheck();
  const fill = async (a, b, v) => { await d.getByLabel("Every day from").fill(a); await d.getByLabel("to", { exact: true }).fill(b); await d.getByLabel("value", { exact: true }).fill(String(v)); await d.locator("button", { hasText: "Fill" }).click(); };
  await fill("00:00", "08:00", base); await fill("02:00", "06:00", peak);
  await page.click("#gsok");
};
await fillSched("Pola Kedatangan", 12, 30);
await waitOk("schedule arrivals"); await next();
await place("process", 270, 110, "Nasabah Datang"); await name("Layanan Teller");
await side.getByLabel("Resources 1 Resource Name").fill("Teller"); await tria(2, 3, 4);
await waitOk("schedule process"); await next();
await place("dispose", 450, 110, "Layanan Teller"); await name("Nasabah Pulang"); await waitOk("schedule dispose"); await next();
await page.click('.pal.data[data-table="resources"]');
await page.getByLabel("Teller Type").selectOption("Based on Schedule");
await page.getByLabel("Teller Schedule Name").fill("Shift Teller");
await waitOk("schedule resource"); await next();
await fillSched("Shift Teller", 1, 3);
await waitOk("schedule shift"); await next();
check("theory: 2 tellers on average", (await tourText()).includes("<b>2</b>") || (await tourText()).includes("= 2")); await next();
await run(5, 8); await waitOk("schedule run"); await next();
const sRead = (await tourText()).replace(/\s+/g, " ");
const ns = parseFloat((sRead.match(/Number Scheduled = (\S+)/) || [])[1]);
check("Number Scheduled ≈ 2", Math.abs(ns - 2) < 0.05, sRead.slice(0, 300));
await next();
await page.click("#bend");
await fillSched("Shift Teller", 1, 2);
await run(5, 8); await waitOk("schedule experiment"); await next();
const sCmp = await tourText();
check("Schedule comparison table", sCmp.includes("3 teller sibuk") && sCmp.includes("2 teller sibuk"), sCmp.slice(0, 300));
await page.screenshot({ path: out + "/tut_schedule.png" });
await next(); await next();
await page.click("#btour");
check("menu marks finished tutorials", (await page.locator("#tour [data-tour] b", { hasText: "✅" }).count()) === 3);
check("no console errors", errors.length === 0, errors.join(" | "));
await browser.close();
