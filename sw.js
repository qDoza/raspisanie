// Офлайн-кэш приложения. При изменении файлов увеличь номер версии.
const VERSION = "v16";
const CACHE = "raspisanie-" + VERSION;
// Расписание лежит в отдельном кэше, который НЕ стирается при обновлении приложения
const DATA = "raspisanie-data";
const SHELL = [
  "./",
  "./index.html",
  "./access.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png"
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith("raspisanie-") && k !== CACHE && k !== DATA).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Данные расписания (data/*.json): сначала сеть, без сети — последняя сохранённая копия
  if (url.origin === location.origin && url.pathname.includes("/data/")) {
    const key = url.origin + url.pathname; // без ?параметров
    e.respondWith(
      fetch(req).then(res => {
        if (res.ok) { const copy = res.clone(); e.waitUntil(caches.open(DATA).then(c => c.put(key, copy))); }
        return res;
      }).catch(() => caches.open(DATA).then(c => c.match(key)).then(r => r || caches.match(req, { ignoreSearch: true })).then(r => r || Response.error()))
    );
    return;
  }

  // Сама страница: сначала сеть (до 3 секунд), без сети — сохранённая копия
  if (req.mode === "navigate") {
    e.respondWith((async () => {
      const cache = await caches.open(CACHE);
      try {
        const res = await Promise.race([fetch(req.url, { cache: "no-cache", credentials: "same-origin" }),new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 3000))]);
        if (res.ok) e.waitUntil(cache.put("./index.html", res.clone()));
        return res;
      } catch (err) {
        return (await cache.match("./index.html")) || (await cache.match("./")) || Response.error();
      }
    })());
    return;
  }

  // Остальные файлы оболочки и шрифты: сначала кэш, в фоне обновляем
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then(cached => {
      const net = fetch(req).then(res => {
        if (res.ok || res.type === "opaque") {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return res;
      }).catch(() => cached);
      return cached || net;
    })
  );
});
