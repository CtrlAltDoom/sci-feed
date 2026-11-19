/* Veille scientifique — lecteur (aucune dépendance, fonctionne hors-ligne une fois chargé) */
(function () {
  "use strict";
  const PAR_PAGE = 40;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------- état local (lus, favoris, masqués, filtres) ----------
  const CLE = "veille-etat-v1";
  let etat = { lus: {}, favoris: {}, masques: {}, themes: [], etiquettes: [], chipsOuverts: false,
    vue: "tous", type: "", niveau: "0", tri: "recent" };
  try { Object.assign(etat, JSON.parse(localStorage.getItem(CLE) || "{}")); } catch (e) { /* stockage indisponible */ }
  const enregistrer = () => { try { localStorage.setItem(CLE, JSON.stringify(etat)); } catch (e) { } };

  let DATA = { meta: { themes: [], etiquettes: [] }, articles: [] };
  let nomsThemes = {}, famThemes = {}, nomsEtiq = {}, famEtiq = {};
  const ORDRE_FAMILLES = ["sujet", "mecanisme", "approche", "animal", ""];
  const NOM_FAMILLE = { sujet: "Sujets psy", mecanisme: "Corps & mécanismes", approche: "Approches", animal: "Signalement", "": "Autres" };
  let affiches = PAR_PAGE;

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

  // ---------- filtrage / tri ----------
  function filtrer() {
    const q = $("recherche").value.trim().toLowerCase();
    const mots = q ? q.split(/\s+/) : [];
    const niv = parseInt(etat.niveau, 10) || 0;
    let liste = DATA.articles.filter((a) => {
      const masque = !!etat.masques[a.id];
      if (etat.vue === "masques") { if (!masque) return false; } else if (masque) return false;
      if (etat.vue === "nonlus" && etat.lus[a.id]) return false;
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
      if (mots.length) {
        const f = a.fiche || {};
        const texte = [a.titre, a.resume, a.revue, (a.auteurs || []).join(" "), f.verdict,
          (f.resultats_cles || []).join(" "), (f.mots_cles_fr || []).join(" ")].join(" ").toLowerCase();
        if (!mots.every((m) => texte.includes(m))) return false;
      }
      return true;
    });
    const recent = (a) => (a.ajoute_le || "") + (a.date || "");
    if (etat.tri === "pertinence") {
      liste.sort((x, y) => ((y.fiche && y.fiche.pertinence) || 0) - ((x.fiche && x.fiche.pertinence) || 0) || recent(y).localeCompare(recent(x)));
    } else if (etat.tri === "preuve") {
      liste.sort((x, y) => ((y.fiche && y.fiche.niveau_preuve) || 0) - ((x.fiche && x.fiche.niveau_preuve) || 0) || recent(y).localeCompare(recent(x)));
    } else {
      liste.sort((x, y) => recent(y).localeCompare(recent(x)));
    }
    return liste;
  }

  // ---------- rendu ----------
  function carte(a) {
    const f = a.fiche;
    const badges = [];
    if (f && f.type_etude && f.type_etude !== "autre") badges.push(`<span class="badge">${esc(f.type_etude)}</span>`);
    else if (estSynthese(a)) badges.push(`<span class="badge">synthèse</span>`);
    if (a.essai_registre) badges.push(`<span class="badge reg">essai enregistré</span>`);
    if (a.preprint) badges.push(`<span class="badge pp">preprint · non relu</span>`);
    if (a.retracte) badges.push(`<span class="badge ret">RÉTRACTÉ</span>`);
    if ((a.etiquettes || []).includes("animal")) badges.push(`<span class="badge animal">Étude animale</span>`);
    const meta = `<div class="meta">${badges.join("")}<span>${esc(fmtJour(a.date))}</span>` +
      (a.revue ? `<span>· ${esc(a.revue)}</span>` : "") + `</div>`;

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
      corps = (a.resume ? `<p class="extrait">${esc(a.resume.slice(0, 260))}${a.resume.length > 260 ? "…" : ""}</p>` : "") +
        `<p class="attente">${a.resume ? "Fiche IA en attente (prochaine mise à jour)" : "Pas d'abstract disponible"}</p>`;
    }

    const det = [];
    if (f) {
      if (f.intervention) det.push(`<p><b>Intervention / comparaison :</b> ${esc(f.intervention)}</p>`);
      if (f.conclusion) det.push(`<p><b>Conclusion des auteurs :</b> ${esc(f.conclusion)}</p>`);
      if ((f.limites || []).length) det.push(`<p><b>Limites :</b> ${f.limites.map(esc).join(" · ")}</p>`);
      if (f.pertinence_raison) det.push(`<p><b>Pourquoi pour moi :</b> ${esc(f.pertinence_raison)}</p>`);
    }
    if (a.resume) det.push(`<p class="abstract"><b>Abstract original :</b>\n${esc(a.resume)}</p>`);
    if ((a.auteurs || []).length) det.push(`<p><b>Auteurs :</b> ${esc(a.auteurs.slice(0, 8).join(", "))}${a.auteurs.length > 8 ? " et al." : ""}</p>`);
    const ids = [a.doi && `DOI ${esc(a.doi)}`, a.pmid && `PMID ${esc(a.pmid)}`, a.nct && esc(a.nct)].filter(Boolean);
    if (ids.length) det.push(`<p>${ids.join(" · ")}</p>`);
    if (f && f.modele) det.push(`<p class="attente">Fiche : ${esc(f.modele)}, ${esc(f.date || "")}</p>`);

    const tags = (a.themes || []).map((t) => `<span class="tag f-${esc(famThemes[t] || "")}">${esc(nomsThemes[t] || t)}</span>`)
      .concat((a.etiquettes || []).filter((t) => t !== "animal" && nomsEtiq[t])
        .map((t) => `<span class="tag f-${esc(famEtiq[t] || "")}">${esc(nomsEtiq[t])}</span>`)).join("");
    const fav = !!etat.favoris[a.id], lu = !!etat.lus[a.id], masque = !!etat.masques[a.id];
    return `<article class="carte${lu ? " lu" : ""}" data-id="${esc(a.id)}">${meta}
      <h2><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.titre)}</a></h2>
      ${corps}
      <details><summary>Détails & abstract</summary>${det.join("")}</details>
      <div class="tags">${tags}</div>
      <div class="actions">
        <button data-act="fav" class="${fav ? "actif" : ""}">${fav ? "★ Favori" : "☆ Favori"}</button>
        <button data-act="lu">${lu ? "↺ Non lu" : "✓ Lu"}</button>
        <button data-act="masquer">${masque ? "Réafficher" : "Pas intéressé"}</button>
        ${a.url_libre ? `<a href="${esc(a.url_libre)}" target="_blank" rel="noopener">Texte libre ↗</a>` : ""}
        ${a.pmid ? `<a href="https://pubmed.ncbi.nlm.nih.gov/${esc(a.pmid)}/" target="_blank" rel="noopener">PubMed ↗</a>` : ""}
      </div></article>`;
  }

  function afficher() {
    const liste = filtrer();
    const nonLus = liste.filter((a) => !etat.lus[a.id]).length;
    $("compteur").textContent = `${liste.length} article${liste.length > 1 ? "s" : ""} · ${nonLus} non lu${nonLus > 1 ? "s" : ""}`;
    if (!liste.length) {
      $("liste").innerHTML = `<p class="vide">Aucun article pour ces filtres.</p>`;
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
    DATA.articles.forEach((a) => {
      if (etat.masques[a.id] || etat.lus[a.id]) return;
      (a.themes || []).forEach((t) => { cT[t] = (cT[t] || 0) + 1; });
      (a.etiquettes || []).forEach((t) => { cE[t] = (cE[t] || 0) + 1; });
    });
    const puce = (genre, t, n) => {
      const actif = (genre === "t" ? etat.themes : etat.etiquettes).includes(t.id);
      return { actif, html: `<button class="chip f-${esc(t.famille || "")}" data-genre="${genre}" data-id="${esc(t.id)}" ` +
        `title="${esc(t.nom)}" aria-pressed="${actif}">${esc(t.court || t.nom)}${n ? `<span class="n">${n}</span>` : ""}</button>` };
    };
    const themes = DATA.meta.themes.map((t) => puce("t", t, cT[t.id]));
    const etiqs = (DATA.meta.etiquettes || []).map((t) => Object.assign(puce("e", t, cE[t.id]), { famille: t.famille || "" }));
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

  const rafraichir = (garderPage) => { if (!garderPage) affiches = PAR_PAGE; afficherThemes(); afficher(); };

  // ---------- export Zotero (RIS) ----------
  function exporterRIS() {
    const favs = DATA.articles.filter((a) => etat.favoris[a.id]);
    if (!favs.length) { alerteDouce("Aucun favori à exporter."); return; }
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
    // noms courts sur les cartes aussi (le nom complet est dans l'infobulle des puces)
    nomsThemes = Object.fromEntries(DATA.meta.themes.map((t) => [t.id, t.court || t.nom]));
    famThemes = Object.fromEntries(DATA.meta.themes.map((t) => [t.id, t.famille || ""]));
    nomsEtiq = Object.fromEntries(DATA.meta.etiquettes.map((t) => [t.id, t.court || t.nom]));
    famEtiq = Object.fromEntries(DATA.meta.etiquettes.map((t) => [t.id, t.famille || ""]));
    etat.themes = (etat.themes || []).filter((t) => nomsThemes[t]);
    etat.etiquettes = (etat.etiquettes || []).filter((t) => nomsEtiq[t]);
    ["vue", "type", "niveau", "tri"].forEach((k) => {
      const el = $("f-" + k); el.value = etat[k];
      el.addEventListener("change", () => { etat[k] = el.value; enregistrer(); rafraichir(); });
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
    });    $("liste").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-act]"); if (!b) return;
      const id = b.closest(".carte").dataset.id;
      const bascule = (dico) => { if (dico[id]) delete dico[id]; else dico[id] = 1; };
      if (b.dataset.act === "fav") bascule(etat.favoris);
      if (b.dataset.act === "lu") bascule(etat.lus);
      if (b.dataset.act === "masquer") bascule(etat.masques);
      enregistrer(); rafraichir(true);
    });
    $("liste").addEventListener("toggle", (e) => {   // ouvrir les détails = marquer comme lu
      const c = e.target.closest && e.target.closest(".carte");
      if (e.target.open && c && !etat.lus[c.dataset.id]) {
        etat.lus[c.dataset.id] = 1; enregistrer(); c.classList.add("lu");
        const b = c.querySelector('button[data-act="lu"]'); if (b) b.textContent = "↺ Non lu";
      }
    }, true);
    $("plus").addEventListener("click", () => { affiches += PAR_PAGE; afficher(); });
    $("tout-lu").addEventListener("click", () => { filtrer().forEach((a) => { etat.lus[a.id] = 1; }); enregistrer(); rafraichir(); });
    $("export").addEventListener("click", exporterRIS);
    rafraichir();
  }

  if (window.VEILLE_DATA) { DATA = window.VEILLE_DATA; brancher(); }
  else {
    fetch("data.json", { cache: "no-cache" }).then((r) => r.json()).then((d) => { DATA = d; brancher(); })
      .catch(() => { $("liste").innerHTML = `<p class="vide">Impossible de charger les données.</p>`; });
  }
})();
