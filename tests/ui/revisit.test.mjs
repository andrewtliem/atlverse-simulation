// The in-browser build across visits, as a student uses it: the first visit installs the
// service worker and caches Pyodide; later visits must still run (a cache the isolated page
// cannot use once made every later run hang). Serve a build first:
//   python -m simcore.web.build dist && python -m http.server -d dist 8790
//   BASE=http://127.0.0.1:8790/ node tests/ui/revisit.test.mjs   (or BASE=https://<site>/)
const PW = process.env.PLAYWRIGHT_CORE || "playwright-core";
const { chromium } = await import(PW);
const fs = await import("fs"), os = await import("os"), path = await import("path");
const base = process.env.BASE || "http://127.0.0.1:8790/";
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "atl-profile-"));
const ctx = await chromium.launchPersistentContext(dir, { headless: true, channel: process.env.PW_CHANNEL || "chrome", viewport: { width: 1366, height: 800 } });
let step = 0;
const check = (name, ok, detail = "") => console.log(`${ok ? "PASS" : "FAIL"} ${++step}. ${name}${detail ? " — " + detail : ""}`);
for (const visit of [1, 2, 3]) {
  const page = await ctx.newPage();
  const errs = []; page.on("pageerror", e => errs.push(e.message));
  await page.goto(base); await page.waitForSelector(".node"); await page.waitForTimeout(1500); await page.waitForSelector(".node");
  await page.evaluate(() => { model.run.replications = "2"; model.run.batch_run = true; });
  await page.click("#brun");
  const ok = await page.waitForFunction(() => !!lastResults, null, { timeout: 90000 }).then(() => true, () => false);
  check(`visit ${visit}: run finishes`, ok && errs.length === 0, errs.join(" | "));
  if (visit === 1) check("cross-origin isolated (End keeps partial results)", await page.evaluate(() => self.crossOriginIsolated));
  await page.close();
}
await ctx.close();
fs.rmSync(dir, { recursive: true, force: true });
