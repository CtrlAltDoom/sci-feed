/* Service worker : l'appli s'ouvre même hors connexion (dernière version consultée).
   Données : réseau d'abord (toujours la veille du jour si possible), cache sinon.
   Interface : cache d'abord, rafraîchi en arrière-plan. */
const CACHE = "veille-v3";
const COQUILLE = ["./", "index.html", "style.css", "app.js", "manifest.webmanifest", "icone.svg", "icone-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((cles) => Promise.all(cles.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;   // GitHub, PubMed… : pas touchés
  const enCache = (rep) => { const copie = rep.clone(); caches.open(CACHE).then((c) => c.put(e.request, copie)); return rep; };
  if (url.pathname.endsWith("data.json")) {
    e.respondWith(fetch(e.request).then(enCache).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then((cache) => {
    const reseau = fetch(e.request).then(enCache).catch(() => cache);
    return cache || reseau;
  }));
});
