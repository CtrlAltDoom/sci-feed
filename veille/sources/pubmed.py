"""PubMed via les E-utilities du NCBI (gratuit ; clé facultative NCBI_API_KEY)."""
from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET

from ..core import nouvel_article, log

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
MOIS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def requete(groupes: list[list[str]]) -> str:
    def terme(t):
        return f'"{t}"[tiab]' if " " in t or "-" in t or "/" in t else f"{t}[tiab]"
    return " AND ".join("(" + " OR ".join(terme(t) for t in g) + ")" for g in groupes)


def _params_communs(cfg):
    p = {"tool": "veille-scientifique", "email": cfg.get("contact_email", "")}
    if os.environ.get("NCBI_API_KEY"):
        p["api_key"] = os.environ["NCBI_API_KEY"]
    return p


def collecter(cfg, http, theme, depuis, jusqu_a):
    base = _params_communs(cfg)
    params = dict(base, db="pubmed", term=requete(theme["_groupes"]), datetype="edat",
                  mindate=depuis.strftime("%Y/%m/%d"), maxdate=jusqu_a.strftime("%Y/%m/%d"),
                  retmax=cfg["collecte"].get("max_par_requete", 150), retmode="json")
    ids = http.get(EUTILS + "esearch.fcgi", params=params).json()["esearchresult"].get("idlist", [])
    articles = []
    for i in range(0, len(ids), 100):
        time.sleep(0.4)  # 3 requêtes/s maximum sans clé
        r = http.get(EUTILS + "efetch.fcgi",
                     params=dict(base, db="pubmed", id=",".join(ids[i:i + 100]), retmode="xml"))
        articles += analyser(r.content)
    log.info("  PubMed [%s] : %d", theme["id"], len(articles))
    return articles


def _texte(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def _date(art):
    # `art` est l'élément <Article> : chemins relatifs à lui
    for chemin in ("ArticleDate", "Journal/JournalIssue/PubDate"):
        d = art.find(chemin)
        if d is None:
            continue
        an = _texte(d.find("Year"))
        if not an:
            md = _texte(d.find("MedlineDate"))
            an = md[:4] if md[:4].isdigit() else ""
        if not an:
            continue
        mois = _texte(d.find("Month"))
        mois = int(mois) if mois.isdigit() else MOIS.get(mois[:3].lower(), 1)
        jour = _texte(d.find("Day"))
        jour = int(jour) if jour.isdigit() else 1
        return f"{an}-{mois:02d}-{jour:02d}"
    return ""


def analyser(xml_bytes: bytes) -> list[dict]:
    racine = ET.fromstring(xml_bytes)
    sortie = []
    for pa in racine.findall("PubmedArticle"):
        mc = pa.find("MedlineCitation")
        art = mc.find("Article")
        pmid = _texte(mc.find("PMID"))
        parties = []
        for at in art.findall("Abstract/AbstractText"):
            label = at.get("Label")
            txt = _texte(at)
            parties.append(f"{label}: {txt}" if label and txt else txt)
        auteurs = []
        for au in art.findall("AuthorList/Author"):
            nom = _texte(au.find("LastName"))
            auteurs.append(f"{nom} {_texte(au.find('Initials'))}".strip() if nom
                           else _texte(au.find("CollectiveName")))
        ids = {a.get("IdType"): _texte(a) for a in pa.findall("PubmedData/ArticleIdList/ArticleId")}
        types = [_texte(t) for t in art.findall("PublicationTypeList/PublicationType")]
        pmcid = ids.get("pmc", "")
        sortie.append(nouvel_article(
            titre=_texte(art.find("ArticleTitle")),
            resume=" ".join(p for p in parties if p),
            auteurs=auteurs,
            revue=_texte(art.find("Journal/Title")) or _texte(art.find("Journal/ISOAbbreviation")),
            date=_date(art), pmid=pmid, doi=ids.get("doi", ""), pmcid=pmcid,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            url_libre=f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else "",
            types=[t for t in types if t != "Journal Article"],
            retracte="Retracted Publication" in types,
            sources=["pubmed"],
        ))
    return sortie
