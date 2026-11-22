/* Veille scientifique — lecteur (aucune dépendance, fonctionne hors-ligne une fois chargé) */
(function () {
  "use strict";
  const PAR_PAGE = 40;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------- état local (lus, favoris, masqués, filtres) ----------
  const CLE = "veille-etat-v1";
  // alias : raccourcis personnels des puces ("t:sii" / "e:anx_dep" -> "Anx") ; cachees : puces masquées
  let etat = { lus: {}, favoris: {}, masques: {}, themes: [], etiquettes: [], chipsOuverts: false,
    alias: {}, cachees: {}, reglages: {}, horo: {}, vue: "tous", type: "", niveau: "0", revue: "0", tri: "pourmoi", triV: 2 };
  try {
    const garde = JSON.parse(localStorage.getItem(CLE) || "{}");
    if (!garde.triV) delete garde.tri;      // nouveau tri par défaut « Pour moi » (une seule fois)
    Object.assign(etat, garde, { triV: 2 });
  } catch (e) { /* stockage indisponible */ }
  const enregistrer = (sansSync) => {
    try { localStorage.setItem(CLE, JSON.stringify(etat)); } catch (e) { }
    if (!sansSync) sync.planifier();
  };
  // modifie un élément partagé entre appareils et date le changement
  const poser = (cat, cle, valeur) => {
    if (valeur) etat[cat][cle] = valeur; else delete etat[cat][cle];
    etat.horo[cat + "|" + cle] = Date.now();
  };

  // ---------- synchronisation entre appareils (gist GitHub secret) ----------
  // Le jeton (droit « gist » uniquement) reste dans CE navigateur, jamais exporté ni publié.
  const sync = (() => {
    const CLE_SYNC = "veille-sync-v1", FICHIER = "veille-synchro.json", API = "https://api.github.com";
    let cfg = {}; try { cfg = JSON.parse(localStorage.getItem(CLE_SYNC) || "{}"); } catch (e) { }
    const garder = () => { try { localStorage.setItem(CLE_SYNC, JSON.stringify(cfg)); } catch (e) { } };
    let minuterie = null, enCours = null, dernierMessage = "", dernierOk = false;
    const statut = (m, ok = false) => {
      dernierMessage = m; dernierOk = ok;
      const el = document.getElementById("sync-statut");
      if (el) { el.textContent = (ok ? "✓ " : "") + m; el.className = ok ? "ok" : ""; }
    };
    const appel = (chemin, options = {}) => fetch(API + chemin, Object.assign({}, options, {
      headers: { Authorization: "Bearer " + cfg.jeton, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
    })).then((r) => {
      if (r.status === 401) throw new Error("jeton refusé (expiré ou mal copié)");
      if (r.status === 403 || r.status === 404) throw new Error("le jeton n'a pas le droit « gist »");
      if (!r.ok) throw new Error("GitHub a répondu " + r.status);
      return r.status === 204 ? null : r.json();
    });

    // retrouve le gist de synchronisation sur le compte, ou le crée (secret)
    async function trouverGist() {
      if (cfg.gist) return cfg.gist;
      for (let page = 1; page <= 10; page++) {
        const liste = await appel(`/gists?per_page=100&page=${page}`);
        const g = liste.find((x) => x.files && x.files[FICHIER]);
        if (g) { cfg.gist = g.id; garder(); return g.id; }
        if (liste.length < 100) break;
      }
      const cree = await appel("/gists", { method: "POST", body: JSON.stringify({
        description: "Veille scientifique : synchronisation des lus, favoris et réglages (créé par l'appli)",
        public: false, files: { [FICHIER]: { content: JSON.stringify(etatPartage()) } } }) });
      cfg.gist = cree.id; garder(); return cree.id;
    }

    async function lire(id) {
      const g = await appel(`/gists/${id}`);
      const f = g.files[FICHIER];
      if (!f) return null;
      const texte = f.truncated ? await fetch(f.raw_url).then((r) => r.text()) : f.content;
      return JSON.parse(texte || "{}");
    }

    async function synchroniser() {
      if (!cfg.jeton) return;
      if (enCours) return enCours;
      enCours = (async () => {
        try {
          statut("Synchronisation…");
          let id = await trouverGist(), distant;
          try { distant = await lire(id); }
          catch (e) { if (/404|gist/.test(e.message)) { cfg.gist = ""; id = await trouverGist(); distant = null; } else throw e; }
          if (distant && fusionner(distant)) { enregistrer(true); calculerNoms(); rafraichir(true); }
          await appel(`/gists/${id}`, { method: "PATCH", body: JSON.stringify({ files: { [FICHIER]: { content: JSON.stringify(etatPartage()) } } }) });
          cfg.derniere = new Date().toISOString(); garder();
          statut("Clé enregistrée · synchronisé à " + new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }), true);
        } catch (e) {
          statut(navigator.onLine === false ? "Hors connexion : synchronisation au retour du réseau" : "Échec : " + e.message);
        } finally { enCours = null; }
      })();
      return enCours;
    }

    return {
      actif: () => !!cfg.jeton,
      message: () => dernierMessage || (cfg.jeton ? "Connecté" : "Non configurée"),
      ok: () => dernierOk,
      planifier() { if (!cfg.jeton) return; clearTimeout(minuterie); minuterie = setTimeout(synchroniser, 4000); },
      maintenant: synchroniser,
      connecter(jeton) { cfg = { jeton: jeton.trim() }; garder(); return synchroniser(); },
      deconnecter() { cfg = {}; garder(); statut("Non configurée (le gist reste sur GitHub)"); },
      demarrer() {
        synchroniser();
        // retour sur l'appli : on récupère ; départ (appli fermée, écran éteint) : on envoie tout de suite
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible" || minuterie) { clearTimeout(minuterie); minuterie = null; synchroniser(); }
        });
        window.addEventListener("online", synchroniser);
      },
    };
  })();

  let DATA = { meta: { themes: [], etiquettes: [] }, articles: [] };

  // ---------- chargement en plusieurs temps ----------
  // data.json : articles récents, sans abstracts (ouverture rapide) ; archive.json : les plus anciens,
  // juste après l'affichage ; details/<paquet>.json : abstracts et auteurs, à l'ouverture de « Détails »
  // ou pour une recherche. Le service worker garde ce qui a été chargé pour le hors connexion.
  const PAR_ID = new Map();
  const paquets = {};
  function preparer(liste) {
    const revues = DATA.meta.revues || {};
    liste.forEach((a) => { if (a.rv && !a.revue_info) a.revue_info = revues[a.rv]; PAR_ID.set(a.id, a); });
    return liste;
  }
  const sansDetails = (a) => !!a.d && !a.detailsOk;
  function chargerPaquet(nom) {
    if (!paquets[nom]) {
      paquets[nom] = fetch(`details/${encodeURIComponent(nom)}.json`, { cache: "no-cache" })
        .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then((p) => Object.keys(p).forEach((id) => { const a = PAR_ID.get(id); if (a) Object.assign(a, p[id], { detailsOk: true }); }))
        .catch((e) => { delete paquets[nom]; throw e; });     // nouvel essai possible plus tard (retour du réseau)
    }
    return paquets[nom];
  }
  const chargerDetails = (liste) => Promise.all([...new Set(liste.filter(sansDetails).map((a) => a.d))].map(chargerPaquet));
  function chargerArchive() {
    const arch = DATA.meta.archive;
    if (!arch || DATA.archiveOk) return;
    fetch(arch.fichier, { cache: "no-cache" }).then((r) => r.json()).then((d) => {
      DATA.archiveOk = true;
      DATA.articles = DATA.articles.concat(preparer(d.articles || []));
      rafraichir(true);
    }).catch(() => { /* hors connexion : les articles récents restent consultables */ });
  }
  // recherche : on cherche tout de suite dans ce qui est chargé, puis dans les abstracts une fois arrivés
  let rechercheAbstracts = null;
  function chercherDansAbstracts() {
    if (rechercheAbstracts || !DATA.articles.some(sansDetails)) return;
    rechercheAbstracts = chargerDetails(DATA.articles).then(
      () => { rechercheAbstracts = null; if ($("recherche").value.trim()) rafraichir(true); },
      () => { rechercheAbstracts = null; });
  }
  let nomsThemes = {}, famThemes = {}, nomsEtiq = {}, famEtiq = {};
  // nom affiché : raccourci personnel > nom court du site > nom complet
  const libelle = (genre, t) => (etat.alias[genre + ":" + t.id] || "").trim() || t.court || t.nom;
  const calculerNoms = () => {
    nomsThemes = Object.fromEntries(DATA.meta.themes.map((t) => [t.id, libelle("t", t)]));
    nomsEtiq = Object.fromEntries(DATA.meta.etiquettes.map((t) => [t.id, libelle("e", t)]));
  };
  const ORDRE_FAMILLES = ["sujet", "mecanisme", "approche", "animal", ""];
  const NOM_FAMILLE = { sujet: "Sujets psy", mecanisme: "Corps & mécanismes", approche: "Approches", animal: "Signalement", "": "Autres" };
  let affiches = PAR_PAGE;

  // ---------- nouveaux depuis ma dernière visite (propre à cet appareil) ----------
  // On retient le jour d'ajout le plus récent vu à chaque visite. Est « nouveau » ce qui a été ajouté
  // après celui de la visite précédente. Une visite qui suit de moins de 3 h le début de la précédente
  // en est la suite : les « nouveaux » restent marqués le temps de les lire.
  let depuis = "";
  function noterVisite() {
    const max = DATA.articles.reduce((m, a) => ((a.ajoute_le || "") > m ? a.ajoute_le : m), "");
    const v = etat.visite || {}, maintenant = Date.now();
    const suite = v.debut && maintenant - v.debut < 3 * 36e5;
    depuis = suite ? v.avant || "" : v.jour || "";
    etat.visite = { jour: max > (v.jour || "") ? max : v.jour || max, avant: depuis, debut: suite ? v.debut : maintenant };
    enregistrer(true);
  }
  const estNouveau = (a) => !!depuis && (a.ajoute_le || "") > depuis;

  // ---------- utilitaires ----------
  const fmtJour = (iso) => {
    if (!iso) return "";
    const d = new Date(iso + "T12:00:00");
    if (isNaN(d)) return iso;
    return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: d.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined });
  };
  const titreJour = (iso) => {
    const auj = new Date(); auj.setHours(12, 0, 0, 0);
    const d = new Date(iso + "T12:00:00");
    const ecart = Math.round((auj - d) / 864e5);
    if (ecart === 0) return "Aujourd'hui";
    if (ecart === 1) return "Hier";
    return d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  };
  const points = (n, label) => n ? `<span class="points" title="${label} ${n}/5">` +
    [1, 2, 3, 4, 5].map((i) => `<span class="${i <= n ? "on" : "off"}">●</span>`).join("") + "</span>" : "";
  const typeEtude = (a) => (a.fiche && a.fiche.type_etude) || "";
  const estSynthese = (a) => /méta-analyse|revue systématique/.test(typeEtude(a)) ||
    (a.types || []).some((t) => /meta-analysis|systematic review/i.test(t));
  const estECR = (a) => /essai randomisé/.test(typeEtude(a)) ||
    (a.types || []).some((t) => /randomized controlled trial/i.test(t));

  // ---------- tri « Pour moi » : récence ET intérêt dans un même score ----------
  // intérêt (mots-clés : thèmes + étiquettes, calculé par le site) + pertinence de la fiche IA (centrée sur 3)
  // moins 1 point tous les `jours_par_point` jours. Date de référence : date de publication, ramenée
  // dans les 30 jours précédant l'ajout (les dates futures ou très anciennes ne faussent pas le tri).
  const JOUR = 864e5;
  function scorePourMoi(a) {
    const ajout = Date.parse((a.ajoute_le || "") + "T12:00:00") || Date.now();
    let ref = Date.parse((a.date || "") + "T12:00:00");
    if (isNaN(ref) || ref > ajout) ref = ajout;
    ref = Math.max(ref, ajout - 30 * JOUR);
    const age = Math.max(0, (Date.now() - ref) / JOUR);
    const pert = a.fiche && a.fiche.pertinence ? a.fiche.pertinence - 3 : 0;
    return (a.interet || 0) + pert - age / (DATA.meta.jours_par_point || 2);
  }

  // ---------- revue : type, domaine, notoriété (données OpenAlex, pas d'IA) ----------
  const NIV_REVUE = { 1: "revue peu citée", 2: "revue établie", 3: "revue de référence" };
  function ligneRevue(a) {
    const r = a.revue_info;
    if (!r) return "";
    const libelleR = r.type === "repository" ? "dépôt d'archives (non relu)" :
      r.type === "conference" ? "actes de congrès" : NIV_REVUE[r.niveau] || "";
    const morceaux = [];
    if (r.domaine) morceaux.push(esc(r.domaine));
    if (r.gros_volume) morceaux.push("méga-revue (gros volume)");
    if (r.doaj) morceaux.push("accès libre (DOAJ)");
    if (!libelleR && !morceaux.length) return "";
    const pts = r.niveau ? `<span class="points">${[1, 2, 3].map((i) => `<span class="${i <= r.niveau ? "on" : "off"}">●</span>`).join("")}</span>` : "";
    const detail = `Notoriété estimée d'après les citations (OpenAlex) : ${r.citations_2ans == null ? "?" : r.citations_2ans} citations par article sur 2 ans, ` +
      `h-index ${r.h_index == null ? "?" : r.h_index}${r.articles_par_an ? ", environ " + r.articles_par_an + " articles par an" : ""}` +
      `${r.editeur ? ", éditeur " + r.editeur : ""}. Repère sur la revue, pas sur la qualité de l'article.`;
    return `<div class="revue-info" title="${esc(detail)}">` +
      (libelleR ? `<span>${pts} ${esc(libelleR)}</span>` : "") + morceaux.map((m) => `<span>${m}</span>`).join("") + `</div>`;
  }

  // ---------- filtrage / tri ----------
  function filtrer() {
    const q = $("recherche").value.trim().toLowerCase();
    const mots = q ? q.split(/\s+/) : [];
    const niv = parseInt(etat.niveau, 10) || 0;
    const nivRevue = parseInt(etat.revue, 10) || 0;
    if (mots.length) chercherDansAbstracts();
    let liste = DATA.articles.filter((a) => {
      const masque = !!etat.masques[a.id];
      if (etat.vue === "masques") { if (!masque) return false; } else if (masque) return false;
      if (etat.vue === "nonlus" && etat.lus[a.id]) return false;
      if (etat.vue === "nouveaux" && !estNouveau(a)) return false;
      if (etat.vue === "favoris" && !etat.favoris[a.id]) return false;
      // OU à l'intérieur des thèmes, OU à l'intérieur des étiquettes, ET entre les deux
      if (etat.themes.length && !(a.themes || []).some((t) => etat.themes.includes(t))) return false;
      if (etat.etiquettes.length && !(a.etiquettes || []).some((t) => etat.etiquettes.includes(t))) return false;
      switch (etat.type) {
        case "synthese": if (!estSynthese(a)) return false; break;
        case "ecr": if (!estECR(a)) return false; break;
        case "publies": if (a.preprint || a.essai_registre) return false; break;
        case "preprint": if (!a.preprint) return false; break;
        case "registre": if (!a.essai_registre) return false; break;
      }
      if (niv && !((a.fiche && a.fiche.niveau_preuve) >= niv)) return false;
      if (nivRevue && !((a.revue_info && a.revue_info.niveau) >= nivRevue)) return false;
      if (mots.length) {
        const f = a.fiche || {};
        const texte = [a.titre, a.resume || a.extrait, (a.mots_cles || []).join(" "), a.revue, (a.auteurs || []).join(" "), f.verdict,
          (f.resultats_cles || []).join(" "), (f.mots_cles_fr || []).join(" ")].join(" ").toLowerCase();
        if (!mots.every((m) => texte.includes(m))) return false;
      }
      return true;
    });
    const recent = (a) => (a.ajoute_le || "") + (a.date || "");
    if (etat.tri === "pourmoi") {
      const s = new Map(liste.map((a) => [a.id, scorePourMoi(a)]));
      liste.sort((x, y) => s.get(y.id) - s.get(x.id) || recent(y).localeCompare(recent(x)));
    } else if (etat.tri === "pertinence") {
      liste.sort((x, y) => ((y.fiche && y.fiche.pertinence) || 0) - ((x.fiche && x.fiche.pertinence) || 0) || recent(y).localeCompare(recent(x)));
    } else if (etat.tri === "preuve") {
      liste.sort((x, y) => ((y.fiche && y.fiche.niveau_preuve) || 0) - ((x.fiche && x.fiche.niveau_preuve) || 0) || recent(y).localeCompare(recent(x)));
    } else {
      liste.sort((x, y) => recent(y).localeCompare(recent(x)));
    }
    return liste;
  }

  // ---------- accès institutionnel (OpenAthens, EZproxy…) ----------
  // Préfixe propre à chaque lecteur : l'article s'ouvre via son établissement, où il s'identifie lui-même.
  function adresseInstitution(prefixe, url) {
    if (!prefixe || !url) return "";
    return prefixe.includes("{url}") ? prefixe.replace("{url}", encodeURIComponent(url)) : prefixe + encodeURIComponent(url);
  }
  function lienInstitution(a) {
    const r = etat.reglages || {};
    const cible = a.doi ? `https://doi.org/${a.doi}` : (a.essai_registre || a.preprint ? "" : a.url);
    const href = adresseInstitution(r.prefixe_acces, cible);
    return href ? `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(r.nom_acces || "Via mon établissement")} ↗</a>` : "";
  }

  // ---------- écoute ----------
  // Fiche avec MP3 (a.audio, voix neuronale préparée chaque nuit) : lecteur audio du navigateur, qui
  // continue écran éteint et se pilote depuis l'écran de verrouillage (Media Session).
  // Sinon, la voix du téléphone lit la fiche (rien n'est téléchargé ni stocké) ; les navigateurs la
  // coupent quand l'écran s'éteint : la lecture se met alors en pause et « Reprendre » repart de la
  // phrase interrompue.
  const ecoute = (() => {
    const dispo = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
    const st = { id: null, morceaux: [], i: 0, etat: "arret", mode: "voix" };   // etat : arret | lecture | pause ; mode : voix | mp3
    let lecteur = null;                                               // un seul élément <audio>, partagé
    const session = "mediaSession" in navigator ? navigator.mediaSession : null;
    function audioDe() {
      if (lecteur) return lecteur;
      lecteur = new Audio(); lecteur.preload = "none";
      lecteur.addEventListener("play", () => { if (st.mode === "mp3" && st.id) { st.etat = "lecture"; majBoutons(); majSession(); } });
      // (lecteur.paused : ignore la pause, arrivée en retard, du MP3 précédent quand on passe à une autre fiche)
      lecteur.addEventListener("pause", () => { if (st.mode === "mp3" && st.etat === "lecture" && lecteur.paused) { st.etat = "pause"; majBoutons(); majSession(); } });
      lecteur.addEventListener("ended", () => { if (st.mode === "mp3") arreter(); });
      lecteur.addEventListener("error", () => {                        // MP3 introuvable : la voix du téléphone prend le relais
        if (st.mode !== "mp3" || !st.id || !lecteur.getAttribute("src")) return;
        const a = PAR_ID.get(st.id); st.mode = "voix"; lecteur.removeAttribute("src");
        if (a && dispo) lancer(a, true); else arreter();
      });
      if (session) {
        const act = (nom, f) => { try { session.setActionHandler(nom, f); } catch (e) { /* action inconnue */ } };
        act("play", () => { if (st.mode === "mp3" && st.id) lecteur.play(); });
        act("pause", () => { if (st.mode === "mp3") lecteur.pause(); });
        act("stop", () => arreter());
      }
      return lecteur;
    }
    function majSession() {
      if (!session) return;
      session.playbackState = st.etat === "lecture" ? "playing" : st.etat === "pause" ? "paused" : "none";
    }
    let jeton = 0;                                                    // invalide les fins d'énoncés annulés
    function voixPour(lang) {
      const toutes = speechSynthesis.getVoices();
      const norm = (v) => (v.lang || "").replace("_", "-").toLowerCase();
      const de = toutes.filter((v) => norm(v).startsWith(lang));
      const exacte = (v) => norm(v) === (lang === "fr" ? "fr-fr" : "en-us") || (lang === "en" && norm(v) === "en-gb");
      const bonne = (v) => /natural|neural|online|google|premium|enhanced/i.test(v.name);
      return de.find((v) => bonne(v) && exacte(v)) || de.find(bonne) || de.find(exacte) || de[0] || null;
    }
    // découpe en phrases courtes : les longs énoncés sont coupés net par certains navigateurs
    function decouper(texte, lang) {
      const out = [];
      (String(texte).replace(/\s+/g, " ").trim().match(/[^.!?;]+[.!?;]*\s*/g) || []).forEach((ph) => {
        while (ph.length > 220) {
          let k = ph.lastIndexOf(", ", 220); if (k < 80) k = ph.lastIndexOf(" ", 220); if (k < 1) k = 220;
          out.push({ t: ph.slice(0, k + 1), lang }); ph = ph.slice(k + 1);
        }
        if (ph.trim()) out.push({ t: ph, lang });
      });
      return out;
    }
    function texte(a) {
      const f = a.fiche, m = [];
      const fr = (t) => { if (t) m.push(...decouper(/[.!?]$/.test(String(t).trim()) ? t : t + ".", "fr")); };
      const en = (t) => { if (t) m.push(...decouper(t, "en")); };
      if (f && f.titre_court) fr(f.titre_court); else en(a.titre);
      if (f) {
        fr(f.verdict);
        if (f.population) fr("Population : " + f.population);
        if (f.intervention) fr("Intervention : " + f.intervention);
        (f.resultats_cles || []).forEach(fr);
        if (f.conclusion) fr("Conclusion des auteurs : " + f.conclusion);
        if ((f.limites || []).length) fr("Limites : " + f.limites.join(". "));
        if (f.pertinence_raison) fr("Pour toi : " + f.pertinence_raison);
      } else if (a.resume) {
        fr("Pas encore de fiche. Voici l'abstract original, en anglais.");
        en(a.resume);
      } else fr("Pas encore de fiche ni d'abstract pour cet article.");
      return m;
    }
    function majBoutons() {
      document.querySelectorAll(".carte").forEach((c) => {
        const b = c.querySelector('button[data-act="ecouter"]'), s = c.querySelector('button[data-act="stop"]');
        if (!b) return;
        const moi = c.dataset.id === st.id && st.etat !== "arret";
        b.textContent = libelle(c.dataset.id); b.classList.toggle("actif", moi);
        if (s) s.hidden = !moi;
      });
    }
    function libelle(id) {
      if (id !== st.id || st.etat === "arret") { const a = PAR_ID.get(id); return a && a.audio ? "🎧 Écouter" : "🔊 Écouter"; }
      return st.etat === "lecture" ? "⏸ Pause" : "▶ Reprendre";
    }
    function dire() {
      const j = ++jeton;
      if (st.i >= st.morceaux.length) { arreter(); return; }
      const m = st.morceaux[st.i], u = new SpeechSynthesisUtterance(m.t);
      u.lang = m.lang === "fr" ? "fr-FR" : "en-US";
      const v = voixPour(m.lang); if (v) u.voice = v;
      u.onend = () => { if (j !== jeton || st.etat !== "lecture") return; st.i++; dire(); };
      u.onerror = () => { if (j !== jeton || st.etat !== "lecture") return; st.etat = "pause"; majBoutons(); };
      speechSynthesis.speak(u);
    }
    function couperVoix() { jeton++; if (dispo) speechSynthesis.cancel(); }
    function couperMp3() { if (lecteur) { st.mode = "voix"; lecteur.pause(); lecteur.removeAttribute("src"); lecteur.load(); } }
    function lancer(a, sansMp3) {
      couperVoix(); couperMp3();
      if (a.audio && !sansMp3) {
        const l = audioDe();
        Object.assign(st, { id: a.id, morceaux: [], i: 0, etat: "lecture", mode: "mp3" });
        l.src = a.audio;
        if (session && "MediaMetadata" in window) {
          session.metadata = new MediaMetadata({ title: (a.fiche && a.fiche.titre_court) || a.titre, artist: "SciFeed",
            album: a.revue || "", artwork: [{ src: "icone-192.png", sizes: "192x192", type: "image/png" }] });
        }
        majBoutons(); majSession();
        const p = l.play(); if (p && p.catch) p.catch(() => { if (st.mode === "mp3" && st.id === a.id) { st.etat = "pause"; majBoutons(); majSession(); } });
        return;
      }
      if (!dispo) { arreter(); return; }
      Object.assign(st, { id: a.id, morceaux: texte(a), i: 0, etat: "lecture", mode: "voix" });
      majBoutons(); dire();
    }
    function pause() {
      st.etat = "pause";
      if (st.mode === "mp3") lecteur.pause(); else couperVoix();
      majBoutons(); majSession();
    }
    function reprendre() {
      st.etat = "lecture"; majBoutons(); majSession();
      if (st.mode === "mp3") { const p = lecteur.play(); if (p && p.catch) p.catch(() => pause()); } else dire();
    }
    function arreter() { st.etat = "arret"; st.id = null; couperVoix(); couperMp3(); majBoutons(); majSession(); }
    function basculer(a) {
      if (st.id === a.id && st.etat === "lecture") return pause();
      if (st.id === a.id && st.etat === "pause") return reprendre();
      if (a.audio) return lancer(a);
      if (!a.fiche && sansDetails(a)) {               // l'abstract n'est pas encore chargé
        st.id = a.id; st.etat = "pause"; majBoutons();
        const go = () => { if (st.id === a.id) lancer(a); };
        chargerDetails([a]).then(go, go);
        return;
      }
      lancer(a);
    }
    if (dispo) {
      speechSynthesis.getVoices();                    // Chrome charge les voix à la première demande
      // écran éteint ou appli quittée : le navigateur coupe la voix, on passe en pause propre
      // (le MP3, lui, continue)
      document.addEventListener("visibilitychange", () => { if (document.hidden && st.etat === "lecture" && st.mode === "voix") pause(); });
      window.addEventListener("pagehide", () => speechSynthesis.cancel());
    }
    return { dispo, basculer, arreter, libelle, possible: (a) => dispo || !!a.audio,
             enCours: (id) => st.id === id && st.etat !== "arret" };
  })();

  // ---------- rendu ----------
  function carte(a) {
    const f = a.fiche;
    // signalements d'abord, puis date · revue · type d'étude (+ précisions de méthode)
    const badges = [];
    if (estNouveau(a)) badges.push(`<span class="badge nouveau">Nouveau</span>`);
    if (a.retracte) badges.push(`<span class="badge ret">RÉTRACTÉ</span>`);
    if (a.preprint) badges.push(`<span class="badge pp">preprint · non relu</span>`);
    if (a.essai_registre) badges.push(`<span class="badge reg">essai enregistré</span>`);
    if ((a.etiquettes || []).includes("animal")) badges.push(`<span class="badge animal">Étude animale</span>`);
    const et = a.etude || { type: f && f.type_etude !== "autre" ? f.type_etude : (estSynthese(a) ? "synthèse" : ""), details: [] };
    const typeTxt = [et.type === "essai enregistré" ? "" : et.type].concat(et.details || []).filter(Boolean).join(" · ");
    const meta = `<div class="meta">${badges.join("")}<span>${esc(fmtJour(a.date))}</span>` +
      (a.revue ? `<span>· ${esc(a.revue)}</span>` : "") +
      (typeTxt ? `<span class="badge type">${esc(typeTxt)}</span>` : "") + `</div>`;

    let corps = "";
    if (f) {
      const indic = [];
      if (f.population) indic.push(`<span>👥 <b>${esc(f.population)}</b></span>`);
      if (f.niveau_preuve) indic.push(`<span>Preuve ${points(f.niveau_preuve, "Niveau de preuve")}</span>`);
      if (f.qualite_methodo && f.qualite_methodo !== "non évaluable")
        indic.push(`<span>Méthodo <b class="q-${esc(f.qualite_methodo)}">${esc(f.qualite_methodo)}</b></span>`);
      if (f.pertinence) indic.push(`<span>Pour moi ${points(f.pertinence, "Pertinence")}</span>`);
      corps = (f.verdict ? `<p class="verdict">${esc(f.verdict)}</p>` : "") +
        (indic.length ? `<div class="indic">${indic.join("")}</div>` : "") +
        ((f.resultats_cles || []).length ? `<ul class="cles">${f.resultats_cles.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
    } else {
      const apercu = a.resume ? a.resume.slice(0, 260) + (a.resume.length > 260 ? "…" : "") : a.extrait || "";
      corps = (apercu ? `<p class="extrait">${esc(apercu)}</p>` : "") +
        `<p class="attente">${apercu ? "Fiche IA en attente (prochaine mise à jour)" : "Pas d'abstract disponible"}</p>`;
    }

    const tags = (a.themes || []).map((t) => `<span class="tag f-${esc(famThemes[t] || "")}">${esc(nomsThemes[t] || t)}</span>`)
      .concat((a.etiquettes || []).filter((t) => t !== "animal" && nomsEtiq[t])
        .map((t) => `<span class="tag f-${esc(famEtiq[t] || "")}">${esc(nomsEtiq[t])}</span>`)).join("");
    const fav = !!etat.favoris[a.id], lu = !!etat.lus[a.id], masque = !!etat.masques[a.id];
    return `<article class="carte${lu ? " lu" : ""}" data-id="${esc(a.id)}">${meta}
      <h2><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.titre)}</a></h2>
      ${ligneRevue(a)}
      ${corps}
      <details><summary>Détails & abstract</summary>${contenuDetails(a)}</details>
      <div class="tags">${tags}</div>
      <div class="actions">
        <button data-act="fav" class="${fav ? "actif" : ""}">${fav ? "★ Favori" : "☆ Favori"}</button>
        <button data-act="lu">${lu ? "↺ Non lu" : "✓ Lu"}</button>
        ${ecoute.possible(a) ? `<button data-act="ecouter" class="${ecoute.enCours(a.id) ? "actif" : ""}" title="${a.audio ? "Écouter la fiche (continue écran éteint)" : "Lire la fiche à voix haute"}">${ecoute.libelle(a.id)}</button><button data-act="stop" title="Arrêter la lecture"${ecoute.enCours(a.id) ? "" : " hidden"}>■ Stop</button>` : ""}
        <button data-act="masquer">${masque ? "Réafficher" : "Pas intéressé"}</button>
        ${a.url_libre ? `<a href="${esc(a.url_libre)}" target="_blank" rel="noopener">Texte libre ↗</a>` : ""}
        ${!a.url_libre && !a.essai_registre ? `<a href="https://scholar.google.com/scholar?q=${encodeURIComponent(a.titre)}" target="_blank" rel="noopener" title="Google Scholar trouve souvent une version déposée par les auteurs">Chercher une version ↗</a>` : ""}
        ${lienInstitution(a)}
        ${a.pmid ? `<a href="https://pubmed.ncbi.nlm.nih.gov/${esc(a.pmid)}/" target="_blank" rel="noopener">PubMed ↗</a>` : ""}
      </div></article>`;
  }

  // contenu de « Détails & abstract » (l'abstract et les auteurs arrivent à l'ouverture, s'ils manquent)
  function contenuDetails(a, erreur) {
    const f = a.fiche;
    const det = [];
    if (f) {
      if (f.intervention) det.push(`<p><b>Intervention / comparaison :</b> ${esc(f.intervention)}</p>`);
      if (f.conclusion) det.push(`<p><b>Conclusion des auteurs :</b> ${esc(f.conclusion)}</p>`);
      if ((f.limites || []).length) det.push(`<p><b>Limites :</b> ${f.limites.map(esc).join(" · ")}</p>`);
      if (f.pertinence_raison) det.push(`<p><b>Pourquoi pour moi :</b> ${esc(f.pertinence_raison)}</p>`);
    }
    if (sansDetails(a)) det.push(`<p class="attente charge-details">${erreur
      ? "Abstract indisponible pour l'instant (pas de connexion ?). Refermez puis rouvrez pour réessayer."
      : "Chargement de l'abstract…"}</p>`);
    if (a.resume) det.push(`<p class="abstract"><b>Abstract original :</b>\n${esc(a.resume)}</p>`);
    if ((a.auteurs || []).length) det.push(`<p><b>Auteurs :</b> ${esc(a.auteurs.slice(0, 8).join(", "))}${a.auteurs.length > 8 ? " et al." : ""}</p>`);
    const ids = [a.doi && `DOI ${esc(a.doi)}`, a.pmid && `PMID ${esc(a.pmid)}`, a.nct && esc(a.nct)].filter(Boolean);
    if (ids.length) det.push(`<p>${ids.join(" · ")}</p>`);
    if (f && f.modele) det.push(`<p class="attente">Fiche : ${esc(f.modele)}, ${esc(f.date || "")}</p>`);
    return det.join("");
  }

  function afficher() {
    const liste = filtrer();
    const nonLus = liste.filter((a) => !etat.lus[a.id]).length;
    $("compteur").textContent = `${liste.length} article${liste.length > 1 ? "s" : ""} · ${nonLus} non lu${nonLus > 1 ? "s" : ""}` +
      (rechercheAbstracts ? " · recherche dans les abstracts…" : "");
    const nbNouveaux = DATA.articles.filter((a) => estNouveau(a) && !etat.masques[a.id]).length;
    const bn = $("voir-nouveaux");
    bn.hidden = !nbNouveaux && etat.vue !== "nouveaux";
    bn.textContent = etat.vue === "nouveaux" ? "Tout afficher" :
      `${nbNouveaux} nouveau${nbNouveaux > 1 ? "x" : ""} depuis ta dernière visite`;
    if (!liste.length) {
      $("liste").innerHTML = `<p class="vide">${etat.vue === "nouveaux" ? "Rien de nouveau depuis ta dernière visite." : etat.vue === "favoris"
        ? (DATA.articles.some((a) => etat.favoris[a.id]) ? "Aucun favori pour ces thèmes ou étiquettes." : "Pas encore de favori : touchez « ☆ Favori » sous un article.")
        : "Aucun article pour ces filtres."}</p>`;
      $("plus").hidden = true;
      return;
    }
    let html = "", jour = null;
    liste.slice(0, affiches).forEach((a) => {
      if (etat.tri === "recent" && a.ajoute_le !== jour) {
        jour = a.ajoute_le;
        html += `<h3 class="jour">${esc(titreJour(jour))}</h3>`;
      }
      html += carte(a);
    });
    $("liste").innerHTML = html;
    $("plus").hidden = liste.length <= affiches;
  }

  // ---------- puces de thèmes / étiquettes ----------
  // Repliées : 2 lignes (filtres actifs en premier) + bouton « +N ».
  // Dépliées : toutes, rangées par famille de couleur.
  function afficherThemes() {
    const cT = {}, cE = {};
    const vueFav = etat.vue === "favoris";   // en vue favoris, les compteurs comptent les favoris
    DATA.articles.forEach((a) => {
      if (vueFav ? !etat.favoris[a.id] : (etat.masques[a.id] || etat.lus[a.id])) return;
      (a.themes || []).forEach((t) => { cT[t] = (cT[t] || 0) + 1; });
      (a.etiquettes || []).forEach((t) => { cE[t] = (cE[t] || 0) + 1; });
    });
    const puce = (genre, t, n) => {
      const actif = (genre === "t" ? etat.themes : etat.etiquettes).includes(t.id);
      return { actif, html: `<button class="chip f-${esc(t.famille || "")}" data-genre="${genre}" data-id="${esc(t.id)}" ` +
        `title="${esc(t.nom)}" aria-pressed="${actif}">${esc(libelle(genre, t))}${n ? `<span class="n">${n}</span>` : ""}</button>` };
    };
    const visible = (genre) => (t) => !etat.cachees[genre + ":" + t.id];
    const themes = DATA.meta.themes.filter(visible("t")).map((t) => puce("t", t, cT[t.id]));
    const etiqs = DATA.meta.etiquettes.filter(visible("e")).map((t) => Object.assign(puce("e", t, cE[t.id]), { famille: t.famille || "" }));
    const aucun = !etat.themes.length && !etat.etiquettes.length;
    const tous = `<button class="chip" data-genre="" aria-pressed="${aucun}">Tous</button>`;
    const bascule = `<button class="bascule" id="chips-bascule" aria-expanded="${etat.chipsOuverts}"></button>`;
    let html;
    if (etat.chipsOuverts) {
      const groupe = (titre, liste, fam) => liste.length ? `<div class="groupe"><span class="groupe-titre${fam != null ? " f-" + fam : ""}">${esc(titre)}</span>` +
        liste.map((p) => p.html).join("") + `</div>` : "";
      html = `<div class="groupe">${tous}</div>` + groupe("Thèmes de collecte", themes) +
        ORDRE_FAMILLES.map((f) => groupe(NOM_FAMILLE[f], etiqs.filter((p) => p.famille === f), f)).join("") +
        `<div class="groupe">${bascule}</div>`;
    } else {
      // 2 lignes qui défilent horizontalement ; « Tous » et le bouton restent en 1re colonne,
      // les filtres actifs viennent juste après
      const toutes = themes.concat(etiqs.sort((x, y) => ORDRE_FAMILLES.indexOf(x.famille) - ORDRE_FAMILLES.indexOf(y.famille)));
      html = tous + bascule + toutes.filter((p) => p.actif).concat(toutes.filter((p) => !p.actif)).map((p) => p.html).join("");
    }
    const nav = $("themes");
    nav.classList.toggle("ouvert", etat.chipsOuverts);
    nav.innerHTML = html;
    $("chips-bascule").textContent = etat.chipsOuverts ? "Réduire ▴" : "Tout afficher ▾";
  }

  // bouton ★ : bascule la vue « Favoris » ; les puces de thèmes / étiquettes filtrent ensuite les favoris
  function majFavoris() {
    const b = $("btn-favoris"); if (!b) return;
    const n = DATA.articles.filter((a) => etat.favoris[a.id]).length;
    $("nb-favoris").textContent = n ? " " + n : "";
    b.setAttribute("aria-pressed", String(etat.vue === "favoris"));
    $("f-vue").value = etat.vue;
  }

  const rafraichir = (garderPage) => { if (!garderPage) affiches = PAR_PAGE; afficherThemes(); afficher(); majFavoris(); };

  // ---------- export Zotero (RIS) ----------
  function exporterRIS() {
    const favs = DATA.articles.filter((a) => etat.favoris[a.id]);
    if (!favs.length) { alerteDouce("Aucun favori à exporter."); return; }
    // abstracts et auteurs complets d'abord (hors connexion : export sans ce qui manque)
    chargerDetails(favs).catch(() => { }).then(() => ecrireRIS(favs));
  }
  function ecrireRIS(favs) {
    const lignes = [];
    favs.forEach((a) => {
      lignes.push("TY  - JOUR", `TI  - ${a.titre}`);
      (a.auteurs || []).forEach((au) => lignes.push(`AU  - ${au}`));
      if (a.revue) lignes.push(`JO  - ${a.revue}`);
      if (a.date) lignes.push(`PY  - ${a.date.slice(0, 4)}`, `DA  - ${a.date.replace(/-/g, "/")}`);
      if (a.doi) lignes.push(`DO  - ${a.doi}`);
      if (a.url) lignes.push(`UR  - ${a.url}`);
      if (a.resume) lignes.push(`AB  - ${a.resume}`);
      if (a.fiche && a.fiche.verdict) lignes.push(`N1  - ${a.fiche.verdict}`);
      lignes.push("ER  - ", "");
    });
    const blob = new Blob([lignes.join("\r\n")], { type: "application/x-research-info-systems" });
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(blob);
    lien.download = "favoris-veille.ris";
    document.body.appendChild(lien); lien.click(); lien.remove();
  }
  function alerteDouce(msg) { $("compteur").textContent = msg; setTimeout(afficher, 2500); }

  // ---------- veille arrêtée ? ----------
  function alerteVeille() {
    const d = new Date(DATA.meta.mise_a_jour || "");
    if (isNaN(d)) return;
    const heures = (Date.now() - d) / 36e5;
    if (heures < 48) return;
    $("alerte-veille").hidden = false;
    $("alerte-veille").textContent = `La veille n'a pas été mise à jour depuis ${Math.floor(heures / 24)} jours. ` +
      "La collecte automatique est peut-être en panne (voir l'onglet Actions du dépôt GitHub).";
  }

  // ---------- flux RSS ----------
  function listeFlux() {
    const li = (href, nom) => `<li><a href="${esc(href)}">${esc(nom)}</a></li>`;
    $("liste-flux").innerHTML = DATA.meta.themes.map((t) => li(`feed-${t.id}.xml`, t.nom))
      .concat(DATA.meta.etiquettes.map((t) => li(`feed-etiquette-${t.id}.xml`, "Étiquette : " + t.nom))).join("");
  }

  // ---------- personnalisation (propre à cet appareil) ----------
  function afficherPerso() {
    const ligne = (genre, t) => {
      const cle = genre + ":" + t.id;
      return `<div class="perso-ligne f-${esc(t.famille || "")}">
        <input type="checkbox" data-cle="${esc(cle)}" ${etat.cachees[cle] ? "" : "checked"} aria-label="Afficher ${esc(t.nom)}">
        <span class="perso-nom" title="${esc(t.nom)}">${esc(t.nom)}</span>
        <input type="text" data-alias="${esc(cle)}" value="${esc(etat.alias[cle] || "")}" placeholder="${esc(t.court || t.nom)}" maxlength="30">
      </div>`;
    };
    $("perso-puces").innerHTML = `<p class="perso-groupe">Thèmes de collecte</p>` + DATA.meta.themes.map((t) => ligne("t", t)).join("") +
      `<p class="perso-groupe">Étiquettes</p>` + DATA.meta.etiquettes.map((t) => ligne("e", t)).join("");
  }

  function majApresPerso() {
    calculerNoms();
    etat.themes = etat.themes.filter((t) => !etat.cachees["t:" + t]);
    etat.etiquettes = etat.etiquettes.filter((t) => !etat.cachees["e:" + t]);
    enregistrer(); rafraichir(true);
  }

  // ---------- état partageable entre appareils ----------
  // Chaque changement (lu, favori, masqué, raccourci, puce masquée) est daté dans etat.horo["categorie|cle"].
  // À la fusion, pour chaque élément, la version la plus récente gagne : retirer un favori sur le
  // téléphone le retire aussi sur le PC. Sans date des deux côtés (anciennes données) : union.
  const PARTAGES = ["lus", "favoris", "masques", "alias", "cachees", "reglages"];

  function fusionner(autre) {
    const horoA = autre.horo || {};
    let change = false;
    PARTAGES.forEach((cat) => {
      const ici = etat[cat], la = autre[cat] || {};
      const cles = new Set([...Object.keys(ici), ...Object.keys(la)]);
      Object.keys(horoA).concat(Object.keys(etat.horo)).forEach((h) => { if (h.startsWith(cat + "|")) cles.add(h.slice(cat.length + 1)); });
      cles.forEach((cle) => {
        const h = cat + "|" + cle, ti = etat.horo[h] || 0, ta = horoA[h] || 0;
        let valeur;
        if (ta > ti) { valeur = la[cle]; etat.horo[h] = ta; }
        else if (ti > ta) return;                       // la version locale est plus récente
        else valeur = ici[cle] || la[cle];               // pas de date : union
        if (valeur) { if (ici[cle] !== valeur) { ici[cle] = valeur; change = true; } }
        else if (cle in ici) { delete ici[cle]; change = true; }
      });
    });
    return change;
  }

  function etatPartage() {
    const d = { format: "veille-etat", version: 2, exporte_le: new Date().toISOString(), horo: etat.horo };
    PARTAGES.forEach((cat) => { d[cat] = etat[cat]; });
    return d;
  }

  function exporterEtat() {
    const sauvegarde = etatPartage();
    const blob = new Blob([JSON.stringify(sauvegarde)], { type: "application/json" });
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(blob);
    lien.download = `veille-sauvegarde-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(lien); lien.click(); lien.remove();
  }

  function brancherPerso() {
    const majSync = () => {
      $("sync-off").hidden = sync.actif(); $("sync-on").hidden = !sync.actif();
      $("sync-statut").textContent = (sync.ok() ? "✓ " : "") + sync.message();
      $("sync-statut").className = sync.ok() ? "ok" : "";
    };
    // accès institutionnel
    const OA = "https://go.openathens.net/redirector/";
    const majAcces = () => {
      const r = etat.reglages, p = r.prefixe_acces || "";
      $("acces-nom").value = r.nom_acces || "";
      $("acces-domaine").value = p.startsWith(OA) ? p.slice(OA.length).split("?")[0] : "";
      $("acces-prefixe").value = p.startsWith(OA) ? "" : p;
      const exemple = DATA.articles.find((a) => (a.doi || "").startsWith("10.1016/"));   // un article Elsevier de la base
      const essai = exemple && adresseInstitution(p, `https://doi.org/${exemple.doi}`);
      $("acces-test").innerHTML = essai ? `Lien actif. <a href="${esc(essai)}" target="_blank" rel="noopener">Tester sur un article Elsevier ↗</a>` : "";
    };
    const changerAcces = (prefixe) => { poser("reglages", "prefixe_acces", prefixe); enregistrer(); rafraichir(true); majAcces(); };
    $("acces-nom").addEventListener("change", (e) => { poser("reglages", "nom_acces", e.target.value.trim()); enregistrer(); rafraichir(true); });
    $("acces-domaine").addEventListener("change", (e) => {
      const d = e.target.value.trim().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
      changerAcces(d ? `${OA}${d}?url={url}` : "");
    });
    $("acces-prefixe").addEventListener("change", (e) => {
      const p = e.target.value.trim();
      changerAcces(/^https:\/\//.test(p) ? p : "");
    });
    $("perso-ouvrir").addEventListener("click", () => { afficherPerso(); majSync(); majAcces(); $("perso-message").textContent = ""; $("perso").showModal(); });
    // un clic (ou un toucher) en dehors de la fenêtre la ferme ; Échap aussi (natif)
    $("perso").addEventListener("click", (e) => {
      if (e.target !== $("perso")) return;
      const r = $("perso").getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) $("perso").close();
    });
    $("sync-connecter").addEventListener("click", () => {
      const j = $("sync-jeton").value.trim();
      if (!/^(ghp_|github_pat_)\w{20,}/.test(j)) { $("sync-statut").textContent = "Ce n'est pas une clé GitHub (elle commence par ghp_ ou github_pat_)."; return; }
      $("sync-jeton").value = "";
      sync.connecter(j).then(majSync);
      majSync();
    });
    $("sync-maintenant").addEventListener("click", () => sync.maintenant().then(majSync));
    $("sync-deconnecter").addEventListener("click", () => { sync.deconnecter(); majSync(); });
    $("perso-puces").addEventListener("change", (e) => {
      const cle = e.target.dataset.cle;
      if (cle) { poser("cachees", cle, e.target.checked ? 0 : 1); majApresPerso(); }
    });
    $("perso-puces").addEventListener("input", (e) => {
      const cle = e.target.dataset.alias;
      if (!cle) return;
      poser("alias", cle, e.target.value.trim());
      majApresPerso();
    });
    $("perso-reinit").addEventListener("click", () => {
      Object.keys(etat.alias).forEach((c) => poser("alias", c, ""));
      Object.keys(etat.cachees).forEach((c) => poser("cachees", c, 0));
      majApresPerso(); afficherPerso();
    });
    $("perso-export").addEventListener("click", exporterEtat);
    $("perso-import").addEventListener("change", (e) => {
      const f = e.target.files[0]; if (!f) return;
      f.text().then((txt) => {
        const d = JSON.parse(txt);
        if (d.format !== "veille-etat") throw new Error("format");
        fusionner(d); majApresPerso(); afficherPerso();
        $("perso-message").textContent = `Importé : ${Object.keys(d.lus || {}).length} lus, ${Object.keys(d.favoris || {}).length} favoris.`;
      }).catch(() => { $("perso-message").textContent = "Fichier non reconnu (il doit venir de « Exporter »)."; });
      e.target.value = "";
    });
  }

  // ---------- événements ----------
  function brancher() {
    $("titre").textContent = DATA.meta.titre || "Veille scientifique";
    document.title = DATA.meta.titre || document.title;
    if (DATA.meta.mise_a_jour) {
      const d = new Date(DATA.meta.mise_a_jour);
      $("maj").textContent = "Mis à jour " + (isNaN(d) ? DATA.meta.mise_a_jour :
        d.toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }));
    }
    DATA.meta.etiquettes = DATA.meta.etiquettes || [];
    Object.assign(NOM_FAMILLE, DATA.meta.familles || {});
    // noms courts (ou raccourcis personnels) sur les cartes aussi ; le nom complet est dans l'infobulle des puces
    calculerNoms();
    famThemes = Object.fromEntries(DATA.meta.themes.map((t) => [t.id, t.famille || ""]));
    famEtiq = Object.fromEntries(DATA.meta.etiquettes.map((t) => [t.id, t.famille || ""]));
    alerteVeille();
    noterVisite();
    listeFlux();
    brancherPerso();
    etat.themes = (etat.themes || []).filter((t) => nomsThemes[t]);
    etat.etiquettes = (etat.etiquettes || []).filter((t) => nomsEtiq[t]);
    ["vue", "type", "niveau", "revue", "tri"].forEach((k) => {
      const el = $("f-" + k); el.value = etat[k];
      el.addEventListener("change", () => { etat[k] = el.value; enregistrer(); rafraichir(); });
    });
    $("btn-favoris").addEventListener("click", () => {
      etat.vue = etat.vue === "favoris" ? "tous" : "favoris";
      enregistrer(true); rafraichir(); window.scrollTo(0, 0);
    });
    $("btn-filtres").addEventListener("click", (e) => {
      const ouvert = $("filtres").hidden; $("filtres").hidden = !ouvert;
      e.currentTarget.setAttribute("aria-expanded", String(ouvert));
    });
    let minuterie;
    $("recherche").addEventListener("input", () => { clearTimeout(minuterie); minuterie = setTimeout(() => rafraichir(), 200); });
    $("themes").addEventListener("click", (e) => {
      if (e.target.closest(".bascule")) { etat.chipsOuverts = !etat.chipsOuverts; enregistrer(); afficherThemes(); return; }
      const b = e.target.closest(".chip"); if (!b) return;
      const genre = b.dataset.genre, id = b.dataset.id;
      if (!genre) { etat.themes = []; etat.etiquettes = []; }
      else {
        const cle = genre === "t" ? "themes" : "etiquettes";
        etat[cle] = etat[cle].includes(id) ? etat[cle].filter((x) => x !== id) : [...etat[cle], id];
      }
      enregistrer(); rafraichir();
    });
    $("liste").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-act]"); if (!b) return;
      const id = b.closest(".carte").dataset.id;
      if (b.dataset.act === "ecouter") { const a = PAR_ID.get(id); if (a) ecoute.basculer(a); return; }
      if (b.dataset.act === "stop") { ecoute.arreter(); return; }
      const bascule = (cat) => poser(cat, id, etat[cat][id] ? 0 : 1);
      if (b.dataset.act === "fav") bascule("favoris");
      if (b.dataset.act === "lu") bascule("lus");
      if (b.dataset.act === "masquer") bascule("masques");
      enregistrer(); rafraichir(true);
    });
    $("liste").addEventListener("toggle", (e) => {   // ouvrir les détails = marquer comme lu (+ charger l'abstract)
      const c = e.target.closest && e.target.closest(".carte");
      if (!e.target.open || !c) return;
      if (!etat.lus[c.dataset.id]) {
        poser("lus", c.dataset.id, 1); enregistrer(); c.classList.add("lu");
        const b = c.querySelector('button[data-act="lu"]'); if (b) b.textContent = "↺ Non lu";
      }
      const a = PAR_ID.get(c.dataset.id), det = e.target;
      if (!a || !sansDetails(a)) return;
      const remplir = (erreur) => {
        det.querySelectorAll(":scope > :not(summary)").forEach((n) => n.remove());
        det.insertAdjacentHTML("beforeend", contenuDetails(a, erreur));
      };
      remplir(false);
      chargerDetails([a]).then(() => remplir(false), () => remplir(true));
    }, true);
    $("plus").addEventListener("click", () => { affiches += PAR_PAGE; afficher(); });
    $("tout-lu").addEventListener("click", () => { filtrer().forEach((a) => { if (!etat.lus[a.id]) poser("lus", a.id, 1); }); enregistrer(); rafraichir(); });
    $("export").addEventListener("click", exporterRIS);
    $("voir-nouveaux").addEventListener("click", () => {
      etat.vue = etat.vue === "nouveaux" ? "tous" : "nouveaux";
      enregistrer(true); rafraichir(); window.scrollTo(0, 0);
    });
    rafraichir();
    sync.demarrer();
    setTimeout(chargerArchive, 300);      // après le premier affichage
  }

  // appli installable (Android / iPhone / PC) et consultable hors connexion
  if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
    navigator.serviceWorker.register("sw.js").catch(() => { /* facultatif */ });
  }

  if (window.VEILLE_DATA) { DATA = window.VEILLE_DATA; preparer(DATA.articles); brancher(); }
  else {
    fetch("data.json", { cache: "no-cache" }).then((r) => r.json()).then((d) => { DATA = d; preparer(DATA.articles); brancher(); })
      .catch(() => { $("liste").innerHTML = `<p class="vide">Impossible de charger les données.</p>`; });
  }
})();
