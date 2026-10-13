// Browser test of the editor. Needs a running server (python -m simcore.web --no-browser)
// and playwright-core: node tests/ui/editor.test.mjs [screenshot-dir]
const PW = process.env.PLAYWRIGHT_CORE || "playwright-core";   // set PLAYWRIGHT_CORE to a playwright-core index.mjs if it is not installed here
const { chromium } = await import(PW);
const out = process.argv[2] || "/tmp";
const browser = await chromium.launch({ headless: true, channel: process.env.PW_CHANNEL || "chrome" });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 860 }, acceptDownloads: true });
const page = await ctx.newPage();
const errors = [];
page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", e => errors.push("pageerror: " + e.message));
page.on("dialog", d => { errors.push("unexpected dialog: " + d.message()); d.dismiss(); });
let step = 0;
const check = (name, ok, detail = "") => console.log(`${ok ? "PASS" : "FAIL"} ${++step}. ${name}${detail ? " — " + detail : ""}`);
const count = s => page.locator(s).count();
const nodeBy = name => page.locator(".node", { has: page.locator("text", { hasText: name }) }).first();

const menu = async (m, item) => { await page.click("#m" + m); await page.click(item); };   // open a menu-bar menu, click an item
await page.goto("http://127.0.0.1:8765/");
await page.evaluate(() => localStorage.clear());
await page.reload();
await page.waitForSelector(".node");
check("sample model loads", await count(".node") === 4);

await menu("file", "#bnew");
check("New gives an empty canvas", await count(".node") === 0);

// drag Create from palette (HTML5 drag and drop)
const stage = page.locator("#stage");
await page.locator('.pal[data-kind="create"]').dragTo(stage, { targetPosition: { x: 120, y: 150 } });
check("drag Create from palette", await count(".node") === 1);
// click-to-place the rest
const place = async (kind, x, y) => {
  await page.evaluate(k => { const b = document.querySelector(`.pal[data-kind="${k}"]`).closest(".pbbody"); if (b.hidden) b.previousElementSibling.click(); }, kind);
  await page.click(`.pal[data-kind="${kind}"]`); await stage.click({ position: { x, y } });
};
await place("process", 330, 150);
await place("decide", 540, 150);
await place("dispose", 760, 90);
await place("dispose", 760, 230);
check("click-to-place 4 more modules", await count(".node") === 5);

// connect ports by dragging
const port = (name, i = 0) => nodeBy(name).locator("circle.port").nth(i);
const body = name => nodeBy(name).locator("rect.body");
await port("Create 1", 0).dragTo(body("Process 1"));
await port("Process 1", 1).dragTo(body("Decide 1"));     // [0]=input, [1]=out
await port("Decide 1", 1).dragTo(body("Dispose 1"));     // true
await port("Decide 1", 2).dragTo(body("Dispose 2"));     // false
check("4 links drawn", await count("path.link[marker-end]") === 4, String(await count("path.link[marker-end]")));

// edit module properties
await body("Process 1").click();
await page.locator("#side").getByLabel("Name", { exact: true }).fill("Machining");
await page.locator("#side").getByLabel("Resources 1 Resource Name").fill("Lathe");
await page.locator("#side").getByLabel("Delay Type").selectOption("Expression");
await page.locator("#side").getByLabel("Expression", { exact: true }).fill("TRIA(1, 2, 3)");
await page.waitForTimeout(700);
check("module name shown on canvas", (await nodeBy("Machining").count()) === 1);

// N-way decide gains exits
await body("Decide 1").click();
await page.locator("#side").getByLabel("Type", { exact: true }).selectOption("N-way by Chance");
await page.locator("#side").getByLabel("Percentages 1 Percent (0-100)").fill("30");
await page.locator("#side button", { hasText: "+ Add percentage" }).click();
await page.locator("#side").getByLabel("Percentages 2 Percent (0-100)").fill("30");
await page.waitForTimeout(700);
const decPorts = await nodeBy("Decide 1").locator("circle.port").count();
check("n-way decide shows 3 exits + input", decPorts === 4, String(decPorts));
await page.locator("#side").getByLabel("Type", { exact: true }).selectOption("2-way by Chance");
await page.waitForTimeout(300);

// Assign: repeat group with Arena's assignment types
await place("assign", 330, 330);
await body("Assign 1").click();
const side = page.locator("#side");
await side.getByLabel("Assignments 1 Type").selectOption("Variable Array (2D)");
check("2D array assignment shows Row and Column", await side.getByLabel("Assignments 1 Row").count() === 1 && await side.getByLabel("Assignments 1 Column").count() === 1);
await side.getByLabel("Assignments 1 Variable Name").fill("Grid");
await side.getByLabel("Assignments 1 Row").fill("2");
await side.getByLabel("Assignments 1 New Value").fill("TNOW");
await side.locator("button", { hasText: "+ Add assignment" }).click();
await side.getByLabel("Assignments 2 Type").selectOption("Entity Picture");
check("Entity Picture hides New Value", await side.getByLabel("Assignments 2 New Value").count() === 0 && await side.getByLabel("Assignments 2 Entity Picture").count() === 1);
await side.locator("button", { hasText: "+ Add assignment" }).click();
await side.getByLabel("Assignments 3 Type").selectOption("Other");
await side.getByLabel("Assignments 3 Other").fill("MR(Lathe)");
const titles = await side.locator(".rtitle").allTextContents();
check("assignment rows summarised", titles.join("|") === "1. Grid(2, 1) = TNOW|2. Entity.Picture = Picture.Report|3. MR(Lathe) = 1", titles.join("|"));
await side.getByLabel("Move Assignments row 3 up").click();
check("rows reorder", (await side.locator(".rtitle").first().textContent()).startsWith("1. Grid") && (await side.locator(".rtitle").nth(1).textContent()).includes("MR(Lathe)"));
await page.waitForTimeout(1300);
check("array assignment to an undefined variable is flagged", (await page.textContent("#p-problems")).includes("Variables table"));
await page.keyboard.press("Escape");
await body("Assign 1").click();
await page.keyboard.press("Delete");

// data tab: resource capacity
await page.click("#sidetabs button:nth-child(2)");
const lathe = page.getByLabel("Lathe Capacity");
check("seized resource appears in Data tab", await lathe.count() === 1);
await lathe.fill("2");
await page.evaluate(() => document.querySelector('details[data-table="entities"]').open = true);
await page.locator('details[data-table="entities"] button', { hasText: "+ Add Entity" }).click();
check("add entity type card", await page.locator('details[data-table="entities"] .card').count() === 2);
await page.waitForTimeout(800);

// validation: duplicate name
await body("Dispose 2").click();
await page.locator("#side").getByLabel("Name", { exact: true }).fill("Dispose 1");
await page.waitForTimeout(1400);
check("duplicate name flagged", (await count(".node.problem")) >= 1, (await page.textContent("#pcount")));
await page.locator("#side").getByLabel("Name", { exact: true }).fill("Scrap");
await page.waitForTimeout(1400);
check("problem cleared after rename", (await count(".node.problem")) === 0);

// undo / redo
const before = await count(".node");
await body("Scrap").click();
await page.keyboard.press("Delete");
check("delete module", (await count(".node")) === before - 1);
await page.keyboard.press("Control+z");
check("undo restores it", (await count(".node")) === before);
await page.keyboard.press("Control+y");
check("redo deletes again", (await count(".node")) === before - 1);
await page.keyboard.press("Control+z");
// copy / paste
await body("Machining").click();
await page.keyboard.press("Control+c"); await page.keyboard.press("Control+v");
check("copy/paste adds a module with a new name", (await count(".node")) === before + 1 && (await nodeBy("Machining 1").count()) === 1);
await page.keyboard.press("Delete");
check("pasted module deleted", (await count(".node")) === before);

// Process of Type Submodel: logic drawn inside, with Entry and Exit points
await place("process", 540, 330);
await body("Process 1").click();
await side.getByLabel("Type", { exact: true }).selectOption("Submodel");
check("Submodel hides the Standard prompts", await side.getByLabel("Action").count() === 0 && await side.locator("button", { hasText: "Open submodel" }).count() === 1);
const topCount = await count(".node");
await body("Process 1").dblclick();
await page.waitForTimeout(300);
check("double-click opens the submodel", await count(".node") === 2 && await page.locator("#crumbs").isVisible() && await page.locator('.pal[data-kind="sub_in"]').isVisible());
await place("delay", 640, 200);
await port("Entry", 0).dragTo(body("Delay 1"));
await port("Delay 1", 1).dragTo(body("Exit"));
check("inner modules connect", await count("path.link[marker-end]") === 2, String(await count("path.link[marker-end]")));
await page.locator("#crumbs button", { hasText: "Top Level" }).click();
await page.waitForTimeout(300);
check("back to top level", await count(".node") === topCount && !(await page.locator('.pal[data-kind="sub_in"]').isVisible()));
check("submodel subtitle counts inner modules", (await nodeBy("Process 1").textContent()).includes("submodel · 1 modules"));
await port("Machining", 1).dragTo(body("Process 1"));
await port("Process 1", 1).dragTo(body("Decide 1"));
await page.waitForTimeout(1300);
const probs = await page.textContent("#p-problems");
check("submodel validates", !/error/.test(probs), probs);

// run
await page.click("#brun");
await page.waitForSelector("#anibar.on", { timeout: 30000 });
check("results wait for the end of the run", (await page.textContent("#p-summary")).includes("appear when the run ends"));
await page.click("#bff");
const summary = await page.textContent("#p-summary");
check("summary shows queues and resources", summary.includes("Machining.Queue") && summary.includes("Lathe") && summary.includes("Scheduled Utilization") && summary.includes("% Busy"));
check("summary is Arena's Category Overview", ["Entity", "Time per Entity", "Accumulated Time", "Queue", "Resource", "Usage"].every(t => summary.includes(t)), summary.slice(0, 200));
check("Reports panel links enabled after the run", !(await page.locator("#pbreports button", { hasText: "Resources" }).isDisabled()));
check("Create and Dispose show their counts", /^\d+$/.test((await page.textContent("#badge-1")) || ""), await page.textContent("#badge-1"));
await page.waitForTimeout(2500);
await page.click("#arestart");
await page.waitForTimeout(1500);
check("animation clock advances", parseFloat((await page.textContent("#clock")).replace("t = ", "")) > 0.5, await page.textContent("#clock"));
check("entity dots drawn", (await count(".ent")) > 0, String(await count(".ent")));
await page.screenshot({ path: out + "/ui2_run.png" });
await page.click("#aexit");

// Graphical Schedule Editor: working hours per day, capacity per hour
await page.click("#sidetabs button:nth-child(2)");
await page.evaluate(() => document.querySelector('details[data-table="schedules"]').open = true);
await page.locator('details[data-table="schedules"] button', { hasText: "+ Add Schedule" }).click();
await page.getByLabel("Edit Schedule 1 graphically").click();
const gsd = page.locator("#scheddlg");
check("schedule editor opens with 24 one-hour slots", await gsd.isVisible() && (await page.textContent("#gsrange")).includes("Day 1 00:00 – Day 2 00:00"), await page.textContent("#gsrange"));
await gsd.getByLabel("Every day from").fill("08:00");
await gsd.getByLabel("to", { exact: true }).fill("17:00");
await gsd.getByLabel("value", { exact: true }).fill("3");
await gsd.locator("button", { hasText: "Fill" }).click();
// paint 12:00 (slot 13) down to 1 by clicking low in that column
const box = await page.locator("#gschart").boundingBox();
const sx = 36 + (box.width - 44) / 24 * 12.5, sy = 8 + (box.height - 42) * (1 - 1 / 5);
await page.mouse.click(box.x + sx, box.y + sy);
check("status bar describes the slot", (await page.textContent("#gsstatus")).includes("Timeslot 13: Day 1 12:00"), await page.textContent("#gsstatus"));
await gsd.locator("#gsok").click();
const rowsText = await page.locator('details[data-table="schedules"] .rtitle').allTextContents();
check("editor writes value/duration rows", rowsText.join("|") === "1. 0 for 8|2. 3 for 4|3. 1 for 1|4. 3 for 4|5. 0 for 7", rowsText.join("|"));
check("schedule preview drawn", await page.locator('details[data-table="schedules"] .schedprev rect').count() === 9);
await page.click("#sidetabs button:nth-child(1)");

// Run > Setup dialog (Arena's tabs) and the run toolbar
await page.click("#bsetup");
const dlg = page.locator("#setupdlg");
check("Run Setup dialog opens", await dlg.isVisible() && (await dlg.locator(".dlgtabs button").allTextContents()).join("|") === "Replication Parameters|Project Parameters|Run Speed|Run Control");
await dlg.getByLabel("Number of Replications").fill("3");
await dlg.getByLabel("Replication Length", { exact: true }).fill("2");
await dlg.getByLabel("Replication Length Time Units").selectOption("Hours");
await dlg.getByLabel("Warm-up Period", { exact: true }).fill("10");
await dlg.locator(".dlgtabs button", { hasText: "Project Parameters" }).click();
await dlg.getByLabel("Analyst Name").fill("Tester");
await dlg.locator("#setupcancel").click();
check("Cancel discards changes", !(await dlg.isVisible()) && !(await page.textContent("#side")).includes("3 replications"));
await page.click("#bsetup");
await dlg.locator(".dlgtabs button", { hasText: "Replication Parameters" }).click();
await dlg.getByLabel("Number of Replications").fill("3");
await dlg.getByLabel("Replication Length", { exact: true }).fill("2");
await dlg.getByLabel("Replication Length Time Units").selectOption("Hours");
await dlg.locator("#setupok").click();
await page.keyboard.press("Escape");
check("OK applies: side panel summary", (await page.textContent("#runsum")).includes("3 replications · length 2 hours"), await page.textContent("#runsum"));
await page.click("#brun");
await page.waitForSelector("#anibar.on", { timeout: 30000 });
check("3 replications run", (await page.textContent("#runstate")).includes("1 of 3"));
await page.click("#bpause");
const tp = await page.textContent("#clock");
await page.waitForTimeout(400);
check("Pause stops the clock", tp === await page.textContent("#clock"));
await page.click("#bstep");
check("Step advances", tp !== await page.textContent("#clock"), `${tp} -> ${await page.textContent("#clock")}`);
await page.click("#bff");
check("Fast-Forward reaches the end", (await page.textContent("#clock")).startsWith("t = 120.00") && await page.locator("#bff").isDisabled());
check("results shown at the end", (await page.textContent("#p-summary")).includes("Replications: 3"));
await page.click("#bend");
check("End returns to editing", !(await page.locator("#anibar").isVisible()) && !(await page.locator("#bsetup").isDisabled()));
// an endless run is stopped with End while the server is still running it
await page.click("#bsetup");
await dlg.getByLabel("Replication Length", { exact: true }).fill("");
await dlg.locator("#setupok").click();
const doneRun = page.waitForResponse(r => r.url().includes("/api/run"), { timeout: 30000 });
await page.click("#brun");
await page.waitForFunction(() => document.getElementById("status").textContent.includes("t = "), null, { timeout: 15000 });
check("progress shown while running", (await page.textContent("#status")).includes("Running replication"));
await page.click("#bend");
await doneRun;
await page.waitForTimeout(300);
check("End stops a running simulation", (await page.textContent("#rinfo")).includes("Ended by you") && !(await page.locator("#anibar").isVisible()), await page.textContent("#rinfo"));
await page.click("#bsetup");
await dlg.getByLabel("Replication Length", { exact: true }).fill("480");
await dlg.getByLabel("Replication Length Time Units").selectOption("Minutes");
await dlg.getByLabel("Number of Replications").fill("1");
await dlg.locator("#setupok").click();

// Project Bar data modules open the spreadsheet view, as in Arena
await page.click('.pal.data[data-table="resources"]');
check("Resource data module opens its spreadsheet", (await page.textContent("#p-sheet")).includes("Resource - Basic Process") && await page.getByLabel("Lathe Capacity").count() === 1);
await page.getByLabel("Lathe Busy / Hour").fill("12");
await page.waitForTimeout(700);
await page.click('.pal.data[data-table="sets"]');
await page.locator("#p-sheet .addrowline").dblclick();
check("double-click adds a data row", await page.getByLabel("Set 1 Members").count() === 1);
await page.click('.pal.data[data-table="resources"]');
await page.getByLabel("Lathe Failures").click();
check("repeat group opens as rows dialog", await page.locator("#rowsdlg").isVisible() && (await page.textContent("#rowsdlg")).includes("+ Add failure"));
await page.click("#rowsclose");
await page.click('.pal.data[data-table="sets"]');
await page.getByLabel("Delete Set 1").click();
check("sheet row deleted", await page.getByLabel("Set 1 Members").count() === 0);
// Statistic (Advanced Process): a Frequency and an Output reported under User Specified
await page.evaluate(() => { const b = document.querySelector('.pal.data[data-table="statistics"]').closest(".pbbody"); if (b.hidden) b.previousElementSibling.click(); });
await page.click('.pal.data[data-table="statistics"]');
await page.locator("#p-sheet .addrowline").dblclick();
await page.getByLabel("Statistic 1 Type").selectOption("Frequency");
await page.getByLabel("Statistic 1 Expression").fill("NR(Lathe)");
await page.locator("#p-sheet .addrowline").dblclick();
await page.getByLabel("Statistic 2 Type").selectOption("Output");
await page.getByLabel("Statistic 2 Expression").fill("TFIN");
check("Statistic rows: Limit is N/A for a Frequency", await page.getByLabel("Statistic 1 Limit").count() === 0);
await page.waitForTimeout(700);
await page.click("#brun");
await page.waitForSelector("#anibar.on", { timeout: 30000 });
await page.click("#bff");
const sumText = await page.textContent("#p-summary");
check("Frequency and Output in User Specified", sumText.includes("Frequency: Statistic 1") && sumText.includes("Restricted Percent") && /Statistic 2\s*480/.test(sumText), sumText.slice(sumText.indexOf("User Specified"), sumText.indexOf("User Specified") + 300));
await page.click("#bend");
await page.click('.pal.data[data-table="statistics"]');   // results replaced the sheet in the bottom pane
// selecting a module shows the spreadsheet of its type
await body("Machining").click();
check("module spreadsheet follows the selection", (await page.textContent("#p-sheet")).includes("Process - Basic Process"));
// Auto-Connect: place a module while one is selected
const linksBefore = await count("path.link[marker-end]");
await body("Scrap").click();
await page.click("#bauto");   // off: Dispose has no exit anyway; turn back on and test from Assign
await page.click("#bauto");
await place("assign", 330, 420);
await place("dispose", 540, 420);
check("Auto-Connect links the new module", await count("path.link[marker-end]") === linksBefore + 1, `${linksBefore} -> ${await count("path.link[marker-end]")}`);
await body("Dispose 2").click(); await page.keyboard.press("Delete");
await body("Assign 1").click(); await page.keyboard.press("Delete");

// save, then open
await page.fill("#mname", "UI Test"); await page.locator("#mname").press("Tab");
await menu("file", "#bsave"); await page.waitForTimeout(500);
await menu("file", "#bopen"); await page.waitForTimeout(300);
const opts = await page.locator("#openlist button").allTextContents(); await page.click("#openclose");
check("saved model listed", opts.includes("UI Test"), opts.join(","));
await menu("file", "#bnew");
await menu("file", "#bopen"); await page.click('#openlist [data-name="UI Test"]'); await page.waitForTimeout(700);
check("open restores model", (await nodeBy("Machining").count()) === 1);

// reload restores autosave
await page.reload(); await page.waitForSelector(".node");
check("reload restores session", (await nodeBy("Machining").count()) === 1);

// zoom and fit
const t0 = await page.getAttribute("#world", "transform");
await page.click("#zin"); const t1 = await page.getAttribute("#world", "transform");
await page.click("#zfit");
check("zoom changes view", t0 !== t1);

// module queues are listed in the Queue data module (like Arena) and follow a rename
const qs = await page.evaluate(() => {
  const n = allNodes().find(x => x.type === "process" && String(x.props.action).startsWith("Seize"));
  syncData(); const listed = Object.keys(model.data.queues).includes(`${n.props.name}.Queue`);
  const old = n.props.name; n.props.name = "QRenamed"; syncData();
  const after = Object.keys(model.data.queues); n.props.name = old; syncData();
  return {listed, moved: after.includes("QRenamed.Queue") && !after.includes(`${old}.Queue`)};
});
check("module queue listed in Queue data module", qs.listed);
check("queue row dropped/added with module rename", qs.moved);

// export YAML download
const [dl] = await Promise.all([page.waitForEvent("download"), menu("file", "#mi-yaml")]);
check("YAML export downloads", (await dl.suggestedFilename()).endsWith(".yaml"));

await page.screenshot({ path: out + "/ui2_editor.png" });
await page.click("#sidetabs button:nth-child(2)");
await page.screenshot({ path: out + "/ui2_data.png" });
check("no console errors", errors.length === 0, errors.join(" | "));
await browser.close();
