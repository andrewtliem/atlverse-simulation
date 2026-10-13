// Service worker of the in-browser build. It
//  - adds the COOP/COEP headers that make the page cross-origin isolated, so the End button
//    can stop a run in progress, on hosts that cannot set headers (GitHub Pages);
//  - keeps the app and Pyodide in a cache, so after the first visit it also works offline.
// Pyodide files are always fetched and cached as CORS responses: an opaque (no-cors)
// response in the cache cannot be served to a cross-origin isolated page, and the worker
// would wait forever for its importScripts.
const CACHE = "atl-sim-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k);
  await self.clients.claim();
})()));

function isolate(res) {
  if (!res || res.status === 0 || res.type === "opaque") return res;
  const h = new Headers(res.headers);
  h.set("Cross-Origin-Embedder-Policy", "require-corp");
  h.set("Cross-Origin-Opener-Policy", "same-origin");
  h.set("Cross-Origin-Resource-Policy", "cross-origin");
  return new Response(res.body, {status: res.status, statusText: res.statusText, headers: h});
}
async function cached(cache, key) {
  try { return await cache.match(key); } catch (e) { try { await cache.delete(key); } catch (e2) {} return undefined; }
}

self.addEventListener("fetch", e => {
  const r = e.request;
  if (r.method !== "GET" || (r.cache === "only-if-cached" && r.mode !== "same-origin")) return;
  const url = new URL(r.url);
  const pyodide = url.hostname === "cdn.jsdelivr.net" && url.pathname.startsWith("/pyodide/");
  if (url.origin !== location.origin && !pyodide) return;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    if (pyodide) {   // versioned URLs: cache first, stored by URL as CORS responses
      const hit = await cached(cache, url.href);
      if (hit && hit.type !== "opaque") return hit;
      const res = await fetch(url.href, {mode: "cors", credentials: "omit"});
      if (res.ok) cache.put(url.href, res.clone()).catch(() => {});
      return res;
    }
    try {            // the app itself: network first, so updates arrive; the cache when offline
      const res = await fetch(r);
      if (res.ok) cache.put(r, res.clone()).catch(() => {});
      return isolate(res);
    } catch (err) {
      const hit = await cached(cache, r);
      if (hit) return isolate(hit);
      throw err;
    }
  })());
});
