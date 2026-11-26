"""Europe PMC : PubMed + PMC + preprints (medRxiv, bioRxiv, PsyArXiv, Research Square…)."""
from __future__ import annotations

from ..core import nouvel_article, log

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def requete(groupes, depuis, jusqu_a, preprints=True):
    # « mot* » (troncature, sujets ajoutés dans l'appli) : joker hors guillemets pour un mot seul
    terme = lambda t: (f"TITLE_ABS:{t}" if t.endswith("*") and " " not in t and "-" not in t
                       else f'TITLE_ABS:"{t.rstrip("*")}"')
    q = " AND ".join("(" + " OR ".join(terme(t) for t in g) + ")" for g in groupes)
    q += f" AND FIRST_PDATE:[{depuis.isoformat()} TO {jusqu_a.isoformat()}]"
    if not preprints:
        q += " AND NOT SRC:PPR"
    return q


def collecter(cfg, http, theme, depuis, jusqu_a):
    opts = cfg["sources"].get("europepmc", {})
    maxi = cfg["collecte"].get("max_par_requete", 150)
    params = {"query": requete(theme["_groupes"], depuis, jusqu_a, opts.get("preprints", True)),
              "format": "json", "resultType": "core", "pageSize": 100, "cursorMark": "*"}
    resultats = []
    while len(resultats) < maxi:
        data = http.get(API, params=params).json()
        page = data.get("resultList", {}).get("result", [])
        resultats += page
        suivant = data.get("nextCursorMark")
        if not page or not suivant or suivant == params["cursorMark"]:
            break
        params["cursorMark"] = suivant
    articles = analyser(resultats[:maxi])
    log.info("  Europe PMC [%s] : %d", theme["id"], len(articles))
    return articles


def analyser(resultats: list[dict]) -> list[dict]:
    sortie = []
    for r in resultats:
        preprint = r.get("source") == "PPR"
        revue = (r.get("journalInfo", {}).get("journal", {}).get("title")
                 or r.get("bookOrReportDetails", {}).get("publisher", "")
                 or ("Preprint" if preprint else ""))
        libre = ""
        for u in r.get("fullTextUrlList", {}).get("fullTextUrl", []):
            if u.get("availability", "").lower() in ("open access", "free"):
                libre = u.get("url", "")
                if u.get("documentStyle") == "pdf":
                    break
        if not libre and r.get("pmcid"):
            libre = f"https://europepmc.org/article/PMC/{r['pmcid']}"
        types = r.get("pubTypeList", {}).get("pubType", [])
        if isinstance(types, str):
            types = [types]
        sortie.append(nouvel_article(
            titre=r.get("title", ""), resume=r.get("abstractText", ""),
            auteurs=[a.strip() for a in (r.get("authorString") or "").rstrip(".").split(",")],
            revue=revue, date=r.get("firstPublicationDate", ""),
            doi=r.get("doi", ""), pmid=r.get("pmid", ""), pmcid=r.get("pmcid", ""),
            url="" if r.get("doi") else f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}",
            url_libre=libre,
            types=[t for t in types if t.lower() not in ("journal article", "research-article")],
            preprint=preprint, sources=["europepmc"],
        ))
    return sortie
