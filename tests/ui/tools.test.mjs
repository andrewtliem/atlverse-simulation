// Browser test of the classroom tools: student identity and the watermarked report with
// its verification code, Scenarios, the Input Analyzer and the live animation plots.
// Needs a running server, like editor.test.mjs.
const PW = process.env.PLAYWRIGHT_CORE || "playwright-core";   // set PLAYWRIGHT_CORE to a playwright-core index.mjs if it is not installed here
const { chromium } = await import(PW);
const fs = await import("fs");
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

const menu = async (m, item) => { await page.click("#m" + m); await page.click(item); };   // open a menu-bar menu, click an item
await page.goto("http://127.0.0.1:8765/");
await page.evaluate(() => localStorage.clear());
await page.reload(); await page.waitForSelector(".node");
check("header fits on one line at 1366px", await page.evaluate(() => document.querySelector("header").offsetHeight) < 60);

// report needs a run, then asks for the identity first
await page.evaluate(() => { model.run.batch_run = true; model.run.replications = "3"; });
await page.click("#brun"); await page.waitForFunction(() => !!lastResults, null, { timeout: 60000 });
await menu("file", "#mi-report");
check("report asks for the student identity", await page.isVisible("#iddlg"));
await page.click("#idok");
check("name and NIM are required", (await page.textContent("#idmsg")).includes("wajib"));
await page.fill("#idname", "Budi Santoso"); await page.fill("#idnim", "2301001"); await page.fill("#idkelas", "TI-3A");
const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#idok")]);
const file = `${out}/${dl.suggestedFilename()}`; await dl.saveAs(file);
const html = fs.readFileSync(file, "utf8");
check("report file named after model and NIM", dl.suggestedFilename() === "Laporan_Bank_2301001.html", dl.suggestedFilename());
const code = (html.match(/<meta name="atl-code" content="([^"]+)"/) || [])[1] || "";
check("report carries code, watermark, diagram and results", /^ATL-\w{4}-\w{4}-\w{4}$/.test(code) && html.includes(`Budi Santoso · 2301001 · ${code}`) && html.includes("<svg") && html.includes("Teller Service.Queue"));
const meta = await page.evaluate(() => model.meta);
check("model stamped with ID and author", /^M-/.test(meta.id) && meta.authors.length === 1 && meta.authors[0].nim === "2301001");
check("analyst name filled from identity", await page.evaluate(() => model.run.analyst) === "Budi Santoso (2301001)");
const ver = t => page.evaluate(t => verifyReport(t).ok, t);
check("verification accepts the untouched report", await ver(html));
check("verification rejects an edited name", !(await ver(html.replace("<b>Budi Santoso</b>", "<b>Andi Wijaya</b>"))));
check("verification rejects edited numbers", !(await ver(html.replace("Teller Service.Queue", "Teller Service.Queuex"))));
// another student saves the same model: the report warns
await page.evaluate(() => localStorage.setItem("atl.identity", JSON.stringify({name: "Andi", nim: "2301002", kelas: ""})));
const [dl2] = await Promise.all([page.waitForEvent("download"), menu("file", "#mi-report")]);
const html2 = fs.readFileSync(await dl2.path(), "utf8");
check("report of a model saved by another NIM shows the history", html2.includes("NIM lain: 2301001") && html2.includes("Budi Santoso (2301001)") && html2.includes("Andi (2301002)"));
await page.evaluate(t => showVerify("x.html", t), html2);
check("Periksa laporan shows both authors", (await page.textContent("#vbody")).includes("2301001") && (await page.textContent("#vbody")).includes("Kode cocok"));
await page.click("#vclose");

// Scenarios
await menu("tools", "#mi-scen");
await page.getByLabel("Skenario 1 Teller · Capacity").fill("1");
await page.click("#scenadd"); await page.getByLabel("Skenario 2 Teller · Capacity").fill("3");
await page.click("#scenrun");
await page.waitForFunction(() => /Selesai/.test(document.getElementById("scenstatus").textContent), null, { timeout: 120000 });
const rows = await page.locator("#scenout table tr").allTextContents();
check("scenarios run with their own capacities", rows.length === 3 && rows[1].includes("Base") && rows[2].includes("Skenario 2"), rows.join(" | "));
const w = await page.evaluate(() => scenRes.rows.map(r => r.responses["wq:Teller Service.Queue"].stat.mean));
check("more tellers, shorter wait", w[1] < w[0] / 5, w.join(" vs "));
check("scenarios saved with the model", await page.evaluate(() => model.scenarios.rows.length) === 2);
check("chart drawn with half-width whiskers", await page.locator("#scenout .scenchart svg path").count() >= 2);
const html3 = await page.evaluate(() => buildReport(false));
check("report includes the scenario comparison", html3.includes("Perbandingan skenario"));
await page.click("#scenclose");

// Input Analyzer
await menu("tools", "#mi-input");
await page.fill("#anadata", "3,5\n4,1\n2,9 5,2; 4,4\n3,8\n4,7\n3,3\n4,0\n4,9\n3,6\n4,2");
await page.click("#anafit");
check("analyzer reads comma decimals", (await page.textContent("#anastats")).includes("n = 12"));
const r = await page.evaluate(() => {
  const {histogram, fitAll, evaluateFit} = atlInput;
  let s = 99; const u = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const ex = Array.from({length: 400}, () => -5 * Math.log(u()));
  const no = Array.from({length: 400}, () => 10 + 2 * Math.sqrt(-2 * Math.log(u())) * Math.cos(2 * Math.PI * u()));
  const fit = x => { const h = histogram(x, 20); return fitAll(x).map(f => evaluateFit(f, x, h)).sort((a, b) => a.se - b.se); };
  const e = fit(ex), n = fit(no);
  return {expo: e.find(f => f.dist === "EXPO" && !/\+/.test(f.expr)), normTop3: n.slice(0, 3).some(f => f.dist === "NORM"), normP: n.find(f => f.dist === "NORM").chiP};
});
check("exponential data: EXPO mean close to 5", Math.abs(parseFloat(r.expo.expr.slice(5)) - 5) < 0.6, r.expo.expr);
check("normal data: NORM among the best and not rejected", r.normTop3 && r.normP > 0.05, String(r.normP));
await page.click("#anaclose");
await page.locator(".node", { has: page.locator("text", { hasText: "Teller Service" }) }).first().locator("rect.body").click();
await menu("tools", "#mi-input"); await page.click("#anasample"); await page.click("#anause");
check("expression used in the selected Process", await page.evaluate(() => { const n = allNodes().find(n => n.props.name === "Teller Service"); return n.props.delay_type === "Expression" && /GAMM|WEIB|EXPO|ERLA|LOGN|BETA/.test(n.props.expression); }));

// live plots
await page.evaluate(() => { model.run.batch_run = false; model.run.replications = "1"; model.data.resources.Teller.capacity = "1"; });
await page.click("#brun"); await page.waitForSelector("#anibar.on", { timeout: 60000 });
await page.waitForTimeout(1500);
check("plot panel shows queue, resource and WIP", await page.isVisible("#plots") && await page.locator("#plots .plg").count() === 3);
await page.click("#bff"); await page.waitForTimeout(400);
const leg = await page.textContent("#plots");
check("plot reaches the end of the run", leg.includes("t = 480") && /Teller: 1 \/ 1|Teller: 0 \/ 1/.test(leg), leg.slice(0, 120));
await page.click("#bplots");
check("plot can be hidden", await page.isHidden("#plots"));
await page.click("#bplots"); await page.click("#aexit"); await page.waitForTimeout(200);
check("plot closes with the animation", await page.isHidden("#plots"));

check("no console errors", errors.length === 0, errors.join(" | "));
await browser.close();
