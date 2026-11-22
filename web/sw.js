/* Service worker : l'appli s'ouvre même hors connexion.
   Tout passe par le réseau d'abord (toujours la dernière version : page, style et données
   cohérents entre eux) ; le cache ne sert que si le réseau ne répond pas. */
const CACHE = "veille-v16";
const COQUILLE = ["./", "index.html", "style.css", "app.js", "manifest.webmanifest", "logo.png", "icone-192.png", "favicon-64.png"];

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
  // MP3 des fiches : lus par morceaux (requêtes Range) et volumineux, laissés au navigateur
  if (url.pathname.includes("/audio/") || e.request.headers.has("range")) return;
  e.respondWith(
    fetch(e.request, { cache: "no-cache" })
      .then((rep) => {
        if (rep.ok) { const copie = rep.clone(); caches.open(CACHE).then((c) => c.put(e.request, copie)); }
        return rep;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }))
  );
});
