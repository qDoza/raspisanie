// Офлайн-кэш приложения. При изменении файлов увеличь номер версии.
const VERSION = "v17";
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

// Запрос с ограничением по времени: при «висящей» сети (VPN, Wi-Fi без интернета) не ждём минуту
const timed = (p, ms) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms))]);

self.addEventListener("install", e => {
  // Каждый файл сохраняем отдельно: если один не скачался (GitHub из РФ иногда отваливается),
  // остальные всё равно попадут в кэш. Без самой страницы установка не считается удачной.
  e.waitUntil((async () => {
    const c = await caches.open(CACHE);
    const res = await Promise.allSettled(SHELL.map(async u => {
      for (let i = 0; i < 3; i++) {
        try { const r = await timed(fetch(u, { cache: "no-cache" }), 15000); if (r.ok) return c.put(u, r); } catch (err) {}
      }
      throw new Error("не скачался " + u);
    }));
    if (res[1].status === "rejected" && !(await c.match("./index.html"))) throw new Error("нет index.html");
    await self.skipWaiting();
  })());
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
    const saved = () => caches.open(DATA).then(c => c.match(key)).then(r => r || caches.match(req, { ignoreSearch: true }));
    e.respondWith((async () => {
      const net = fetch(req).then(res => {
        if (res.ok) { const copy = res.clone(); e.waitUntil(caches.open(DATA).then(c => c.put(key, copy))); }
        return res;
      });
      e.waitUntil(net.catch(() => {})); // даже если ответили из кэша, свежая копия всё равно сохранится
      try {
        // есть сохранённая копия — ждём сеть не больше 4 секунд, нет копии — до 20 секунд
        return await timed(net, (await saved()) ? 4000 : 20000);
      } catch (err) {
        return (await saved()) || Response.error();
      }
    })());
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
