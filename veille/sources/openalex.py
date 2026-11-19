"""OpenAlex : index ouvert de la littérature scientifique, toutes disciplines."""
from __future__ import annotations

import os

from ..core import nouvel_article, log

API = "https://api.openalex.org/works"
CHAMPS = ("id,doi,display_name,publication_date,abstract_inverted_index,authorships,"
          "primary_location,open_access,type,ids,is_retracted")


def requete(groupes):
    # les virgules sont interdites dans un filtre OpenAlex
    return " AND ".join("(" + " OR ".join(f'"{t.replace(",", " ")}"' for t in g) + ")"
                        for g in groupes)


def collecter(cfg, http, theme, depuis, jusqu_a):
    maxi = cfg["collecte"].get("max_par_requete", 150)
    params = {
        "filter": (f"title_and_abstract.search:{requete(theme['_groupes'])},"
                   f"from_publication_date:{depuis.isoformat()},"
                   f"to_publication_date:{jusqu_a.isoformat()},is_paratext:false"),
        # pagination par numéro de page : la pagination par curseur exige désormais une clé API
        "per-page": min(200, maxi), "page": 1, "select": CHAMPS,
        "mailto": cfg.get("contact_email", ""),
    }
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    resultats = []
    while len(resultats) < maxi:
        data = http.get(API, params=params).json()
        page = data.get("results", [])
        resultats += page
        total = (data.get("meta") or {}).get("count") or 0
        if not page or len(resultats) >= total:
            break
        params["page"] += 1
    articles = analyser(resultats[:maxi])
    log.info("  OpenAlex [%s] : %d", theme["id"], len(articles))
    return articles


def abstract_depuis_index(inv: dict | None) -> str:
    if not inv:
        return ""
    positions = {}
    for mot, pos in inv.items():
        for p in pos:
            positions[p] = mot
    return " ".join(positions[i] for i in sorted(positions))


def analyser(resultats: list[dict]) -> list[dict]:
    sortie = []
    for w in resultats:
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        pmid = (w.get("ids") or {}).get("pmid", "") or ""
        pmid = pmid.rstrip("/").rsplit("/", 1)[-1] if pmid else ""
        typ = w.get("type") or ""
        sortie.append(nouvel_article(
            titre=w.get("display_name", ""),
            resume=abstract_depuis_index(w.get("abstract_inverted_index")),
            auteurs=[(a.get("author") or {}).get("display_name", "")
                     for a in (w.get("authorships") or [])],
            revue=src.get("display_name", ""), date=w.get("publication_date", ""),
            doi=w.get("doi", ""), pmid=pmid,
            url_libre=(w.get("open_access") or {}).get("oa_url") or "",
            types=[typ] if typ in ("review", "preprint", "letter", "editorial") else [],
            preprint=typ == "preprint", retracte=bool(w.get("is_retracted")),
            sources=["openalex"],
            revue_oa=(src.get("id") or "").rsplit("/", 1)[-1] or None,
        ))
    return sortie
