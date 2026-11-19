"""Informations sur les revues (OpenAlex) : type, domaine, notoriété estimée.

Données factuelles, pas de jugement d'IA : citations moyennes sur 2 ans (proche du
« facteur d'impact »), h-index, indexation DOAJ, type de source (revue, dépôt, congrès).
Gardées dans data/revues.json et rafraîchies tous les 90 jours.
"""
from __future__ import annotations

import datetime as dt
import json
import os

from . import pipeline
from .core import aujourd_hui, log

API = "https://api.openalex.org"
LOT = 50              # valeurs par filtre OpenAlex
RAFRAICHIR_JOURS = 90

DOMAINES = {   # sous-domaines OpenAlex les plus fréquents ici -> français
    "Gastroenterology": "Gastro-entérologie", "Clinical Psychology": "Psychologie clinique",
    "Psychiatry and Mental health": "Psychiatrie", "Neurology": "Neurologie",
    "Cognitive Neuroscience": "Neurosciences cognitives", "Cellular and Molecular Neuroscience": "Neurosciences",
    "Behavioral Neuroscience": "Neurosciences comportementales", "Social Psychology": "Psychologie sociale",
    "Developmental and Educational Psychology": "Psychologie du développement",
    "Experimental and Cognitive Psychology": "Psychologie cognitive", "Applied Psychology": "Psychologie appliquée",
    "General Psychology": "Psychologie", "Complementary and alternative medicine": "Médecines complémentaires",
    "Nutrition and Dietetics": "Nutrition", "Microbiology": "Microbiologie", "Immunology": "Immunologie",
    "Pharmacology": "Pharmacologie", "General Medicine": "Médecine générale", "Internal Medicine": "Médecine interne",
    "Pediatrics, Perinatology and Child Health": "Pédiatrie", "Public Health, Environmental and Occupational Health": "Santé publique",
    "Rehabilitation": "Rééducation", "Anesthesiology and Pain Medicine": "Douleur", "Surgery": "Chirurgie",
    "Endocrinology, Diabetes and Metabolism": "Endocrinologie", "Molecular Biology": "Biologie moléculaire",
    "Health Informatics": "Santé numérique", "Nursing": "Soins infirmiers", "Obstetrics and Gynecology": "Gynécologie",
}


def _params(cfg: dict, **p) -> dict:
    p["mailto"] = cfg.get("contact_email", "")
    if os.environ.get("OPENALEX_API_KEY"):
        p["api_key"] = os.environ["OPENALEX_API_KEY"]
    return p


def _fichier():
    return pipeline.DATA / "revues.json"   # lu à l'appel (les tests déplacent DATA)


def charger() -> dict:
    f = _fichier()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def niveau(info: dict | None) -> int:
    """0 = inconnu, 1 = peu citée, 2 = établie, 3 = de référence. Repère de notoriété, pas de qualité."""
    # le h-index (installation de la revue dans la durée) pèse plus que le taux de citation récent,
    # que les « méga-revues » à très gros volume gonflent facilement
    if not info or info.get("type") != "journal":
        return 0
    c, h = info.get("citations_2ans") or 0, info.get("h_index") or 0
    if ((h >= 150 and c >= 1.5) or (h >= 80 and c >= 3)) and not gros_volume(info):
        return 3
    if h >= 40 or (c >= 1.5 and h >= 20):
        return 2
    return 1


def gros_volume(info: dict) -> bool:
    """Méga-revue (plus de 8 000 articles par an, sélection souvent moins exigeante) :
    plafonnée à « établie », sauf si elle est très citée."""
    return (info.get("articles_par_an") or 0) > 8000 and (info.get("citations_2ans") or 0) < 10


def resume(info: dict | None) -> dict | None:
    """Ce qui est envoyé au site pour une revue. Rien pour les archives (PubMed Central, Zenodo…),
    qui hébergent aussi des articles publiés : on ne peut rien en dire de fiable."""
    if not info or info.get("type") != "journal":
        return None
    domaine = info.get("domaine")
    return {"type": "journal", "doaj": info.get("doaj", False),
            # domaine affiché seulement s'il est connu (les revues généralistes ont un 1er sujet arbitraire)
            "domaine": domaine if domaine in DOMAINES.values() else None,
            "citations_2ans": info.get("citations_2ans"), "h_index": info.get("h_index"),
            "articles_par_an": info.get("articles_par_an"), "gros_volume": gros_volume(info),
            "editeur": info.get("editeur"), "niveau": niveau(info)}


def completer(cfg: dict, http, base, maxi_articles: int = 1000) -> None:
    """Rattache les articles à leur revue OpenAlex (via le DOI), puis met à jour les fiches revues."""
    # 1. articles -> identifiant de revue (une requête pour 50 DOI)
    a_faire = [a for a in base.articles if a.get("doi") and "," not in a["doi"] and "|" not in a["doi"]
               and "revue_oa" not in a][:maxi_articles]   # virgule et | interdites dans un filtre
    for i in range(0, len(a_faire), LOT):
        lot = {a["doi"]: a for a in a_faire[i:i + LOT]}
        try:
            data = http.get(f"{API}/works", params=_params(
                cfg, filter="doi:" + "|".join(lot), select="doi,primary_location", **{"per-page": LOT})).json()
        except Exception as ex:
            log.debug("revues (articles) : %s", ex)
            continue
        for w in data.get("results", []):
            doi = (w.get("doi") or "").lower().replace("https://doi.org/", "")
            src = ((w.get("primary_location") or {}).get("source") or {})
            if doi in lot:
                lot[doi]["revue_oa"] = (src.get("id") or "").rsplit("/", 1)[-1]
        for a in lot.values():
            a.setdefault("revue_oa", "")       # introuvable : ne pas redemander à chaque fois

    # 2. revues -> informations (une requête pour 50 revues)
    revues = charger()
    limite = (aujourd_hui() - dt.timedelta(days=RAFRAICHIR_JOURS)).isoformat()
    ids = sorted({a["revue_oa"] for a in base.articles if a.get("revue_oa")})
    a_maj = [s for s in ids if s not in revues or revues[s].get("maj", "") < limite]
    for i in range(0, len(a_maj), LOT):
        lot = a_maj[i:i + LOT]
        try:
            data = http.get(f"{API}/sources", params=_params(
                cfg, filter="openalex:" + "|".join(lot), **{"per-page": LOT},
                select="id,display_name,type,is_in_doaj,summary_stats,host_organization_name,topics,counts_by_year")).json()
        except Exception as ex:
            log.debug("revues (sources) : %s", ex)
            continue
        for s in data.get("results", []):
            sid = s["id"].rsplit("/", 1)[-1]
            stats = s.get("summary_stats") or {}
            sous = ((s.get("topics") or [{}])[0].get("subfield") or {}).get("display_name", "")
            revues[sid] = {
                "nom": s.get("display_name", ""), "type": s.get("type"), "doaj": bool(s.get("is_in_doaj")),
                "citations_2ans": round(stats.get("2yr_mean_citedness") or 0, 2), "h_index": stats.get("h_index") or 0,
                "editeur": s.get("host_organization_name") or "", "domaine": DOMAINES.get(sous, sous),
                # volume annuel récent (le total pénaliserait les revues anciennes)
                "articles_par_an": max([y.get("works_count") or 0 for y in (s.get("counts_by_year") or [])
                                        if y.get("year", 0) >= aujourd_hui().year - 3] or [0]),
                "maj": aujourd_hui().isoformat(),
            }
    pipeline.DATA.mkdir(exist_ok=True)
    _fichier().write_text(json.dumps(revues, ensure_ascii=False, indent=0), encoding="utf-8")
    log.info("Revues : %d connues, %d articles rattachés", len(revues),
             sum(1 for a in base.articles if a.get("revue_oa")))
