/* NAFA : fonctionne sans connexion apres la premiere visite.
   Pour publier une mise a jour, changez le numero de VERSION ci-dessous. */
const VERSION = "v2";
const CACHE = "mon-plan-brvm-" + VERSION;
const FICHIERS = ["./", "index.html", "manifest.webmanifest", "icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(FICHIERS)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith("mon-plan-brvm-") && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  const page = e.request.mode === "navigate" || /\/(index\.html)?$/.test(new URL(e.request.url).pathname);
  if (page) {
    // La page (avec les cours du jour) : le reseau, mais pas plus de 2,5 s d'attente.
    // Au-dela, on affiche la derniere copie et on previent la page des que la nouvelle arrive.
    const reseau = fetch(e.request, { cache: "no-store" }).then(r => {
      if (r && r.ok) { const copie = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copie)); }
      return r;
    });
    e.respondWith(caches.match(e.request).then(enCache => {
      if (!enCache) return reseau.catch(() => caches.match("index.html"));
      let expire = false;
      const delai = new Promise(ok => setTimeout(() => { expire = true; ok(enCache); }, 2500));
      reseau.then(() => { if (expire) self.clients.matchAll().then(cs => cs.forEach(c => c.postMessage({ type: "maj" }))); }).catch(() => {});
      return Promise.race([reseau.catch(() => enCache), delai]);
    }));
    return;
  }
  // Icones et fichiers fixes : le cache d'abord, mis a jour en arriere-plan
  e.respondWith(caches.open(CACHE).then(c => c.match(e.request).then(rep => {
    const reseau = fetch(e.request).then(r => { if (r && r.ok) c.put(e.request, r.clone()); return r; }).catch(() => rep);
    return rep || reseau;
  })));
});
