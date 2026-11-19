"""Génération du site statique (lecteur mobile) et des flux RSS de sortie."""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import shutil

from . import revues
from .core import RACINE, bonus_serieux, contient, interet, log, themes_correspondants
from .pipeline import ETAT, charger

WEB = RACINE / "web"
SORTIE = RACINE / "site"
MAX_RSS = 200


# ---------------------------------------------------------------- type d'étude
# Précisions de méthode repérées dans le titre / l'abstract (fiable : ce sont les mots des auteurs)
DETAILS = [
    ("triple aveugle", ["triple-blind", "triple blind", "triple-masked"]),
    ("double aveugle", ["double-blind", "double blind", "double-masked", "double masked"]),
    ("simple aveugle", ["single-blind", "single blind", "single-masked"]),
    ("en ouvert", ["open-label", "open label"]),
    ("contre placebo", ["placebo-controlled", "placebo controlled", "sham-controlled", "sham controlled"]),
    ("en cross-over", ["crossover", "cross-over"]),
    ("en grappes", ["cluster randomi*", "cluster-randomi*"]),
    ("non-infériorité", ["non-inferiority", "noninferiority"]),
    ("multicentrique", ["multicent*", "multi-cent*", "multisite", "multi-site"]),
    ("pilote", ["pilot study", "pilot trial", "pilot randomi*", "feasibility study", "feasibility trial"]),
    ("préenregistrée", ["preregistered", "pre-registered"]),
]
# types déclarés par PubMed / OpenAlex, quand il n'y a pas encore de fiche IA
TYPES_SOURCE = [
    ("méta-analyse", ["meta-analysis"]), ("revue systématique", ["systematic review"]),
    ("essai randomisé", ["randomized controlled trial"]), ("essai clinique", ["clinical trial"]),
    ("étude observationnelle", ["observational study"]), ("cas clinique", ["case reports"]),
    ("revue", ["review"]), ("éditorial", ["editorial"]), ("lettre", ["letter"]), ("commentaire", ["comment"]),
]


def type_etude(a: dict) -> dict:
    fiche = a.get("fiche") or {}
    typ = fiche.get("type_etude") if fiche.get("type_etude") not in (None, "autre") else ""
    if not typ:
        declares = " | ".join(a.get("types") or []).lower()
        typ = next((nom for nom, mots in TYPES_SOURCE if any(m in declares for m in mots)), "")
    if not typ and a.get("essai_registre"):
        typ = "essai enregistré"
    texte = f"{a.get('titre', '')} {a.get('resume', '')}".lower()
    details = [nom for nom, mots in DETAILS if any(contient(texte, m) for m in mots)]
    if "double aveugle" in details or "triple aveugle" in details:
        details = [d for d in details if d != "simple aveugle"]
    for d in fiche.get("design") or []:          # précisions de la fiche IA (nouvelles fiches)
        if d and d.lower() not in details and d.lower() != typ:
            details.append(d.lower())
    return {"type": typ, "details": details[:4]}


def _rfc822(jour: str) -> str:
    try:
        d = dt.datetime.fromisoformat(jour).replace(tzinfo=dt.timezone.utc)
    except ValueError:
        d = dt.datetime.now(dt.timezone.utc)
    return email.utils.format_datetime(d)


def _description(a: dict) -> str:
    f = a.get("fiche") or {}
    e = html.escape
    morceaux = []
    if f.get("verdict"):
        morceaux.append(f"<p><b>{e(f['verdict'])}</b></p>")
    infos = " · ".join(x for x in [f.get("type_etude"), f.get("population"),
                                   f"niveau de preuve {f['niveau_preuve']}/5" if f.get("niveau_preuve") else ""] if x)
    if infos:
        morceaux.append(f"<p>{e(infos)}</p>")
    if f.get("resultats_cles"):
        morceaux.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in f["resultats_cles"]) + "</ul>")
    if not f:
        morceaux.append(f"<p>{e(a.get('resume', '')[:600])}…</p>")
    morceaux.append(f"<p><i>{e(a.get('revue', ''))}</i></p>")
    return "".join(morceaux)


def _rss(articles, titre, lien, chemin):
    items = []
    for a in articles[:MAX_RSS]:
        items.append(
            "<item>"
            f"<title>{html.escape(a['titre'])}</title>"
            f"<link>{html.escape(a.get('url', ''))}</link>"
            f"<guid isPermaLink=\"false\">{html.escape(a['id'])}</guid>"
            f"<pubDate>{_rfc822(a.get('ajoute_le', ''))}</pubDate>"
            f"<description>{html.escape(_description(a))}</description>"
            "</item>")
    chemin.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{html.escape(titre)}</title><link>{html.escape(lien)}</link>"
        f"<description>{html.escape(titre)}</description>{''.join(items)}</channel></rss>",
        encoding="utf-8")


def construire(cfg: dict, inline: bool = False, articles: list[dict] | None = None) -> None:
    if articles is None:
        articles = charger().articles
    articles = sorted(articles, key=lambda a: (a.get("ajoute_le", ""), a.get("date", "")), reverse=True)
    etat = json.loads(ETAT.read_text(encoding="utf-8")) if ETAT.exists() else {}
    # étiquettes : calculées à chaque génération sur toute la base (rien de plus à collecter)
    etiquettes = cfg.get("etiquettes", [])
    infos_revues = revues.charger()
    enrichis = []
    for a in articles:
        e = themes_correspondants(a, etiquettes)
        info = revues.resume(infos_revues.get(a.get("revue_oa") or ""))
        enrichis.append(dict(a, etiquettes=e, revue_info=info, etude=type_etude(a),
                             interet=round(interet(a, cfg, e) + bonus_serieux(a, info, cfg), 2)))
    articles = enrichis
    meta = {
        "titre": cfg.get("titre", "Veille scientifique"),
        "mise_a_jour": etat.get("derniere_collecte", ""),
        "themes": [{"id": t["id"], "nom": t["nom"], "court": t.get("court", ""), "famille": t.get("famille", "")}
                   for t in cfg.get("themes", [])],
        "etiquettes": [{"id": t["id"], "nom": t["nom"], "court": t.get("court", ""), "famille": t.get("famille", "")}
                       for t in etiquettes],
        "familles": cfg.get("familles", {}),
        "jours_par_point": (cfg.get("interet") or {}).get("jours_par_point", 2),
    }
    if any(a.get("libre") for a in articles):
        ids = {t["id"] for t in meta["themes"]}
        for a in articles:
            for t in a.get("themes", []):
                if t not in ids:
                    meta["themes"].append({"id": t, "nom": t})
                    ids.add(t)
    if SORTIE.exists():
        shutil.rmtree(SORTIE)
    shutil.copytree(WEB, SORTIE)
    donnees = {"meta": meta, "articles": articles}
    if inline:
        page = (SORTIE / "index.html").read_text(encoding="utf-8")
        script = "<script>window.VEILLE_DATA=" + json.dumps(donnees, ensure_ascii=False).replace(
            "</", "<\\/") + ";</script>"
        page = page.replace("<!--DONNEES-->", script)
        page = page.replace('<link rel="stylesheet" href="style.css">',
                            "<style>" + (SORTIE / "style.css").read_text(encoding="utf-8") + "</style>")
        page = page.replace('<script src="app.js"></script>',
                            "<script>" + (SORTIE / "app.js").read_text(encoding="utf-8") + "</script>")
        (SORTIE / "index.html").write_text(page, encoding="utf-8")
    else:
        (SORTIE / "data.json").write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    _rss(articles, meta["titre"], "./", SORTIE / "feed.xml")
    for t in meta["themes"]:
        _rss([a for a in articles if t["id"] in a.get("themes", [])],
             f"{meta['titre']} — {t['nom']}", "./", SORTIE / f"feed-{t['id']}.xml")
    for t in meta["etiquettes"]:
        _rss([a for a in articles if t["id"] in a.get("etiquettes", [])],
             f"{meta['titre']} — {t['nom']}", "./", SORTIE / f"feed-etiquette-{t['id']}.xml")
    (SORTIE / ".nojekyll").write_text("", encoding="utf-8")
    log.info("Site généré : %d articles -> %s", len(articles), SORTIE)
