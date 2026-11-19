"""Flux RSS/Atom (revues, preprints, blogs) filtrés par vos thèmes."""
from __future__ import annotations

import datetime as dt
import re

import feedparser

from ..core import nouvel_article, themes_correspondants, log

RE_DOI = re.compile(r"10\.\d{4,9}/[^\s?#&\"<>]+", re.I)


def _date(e):
    for champ in ("published_parsed", "updated_parsed", "created_parsed"):
        t = e.get(champ)
        if t:
            return dt.date(t.tm_year, t.tm_mon, t.tm_mday)
    return None


def _doi(e):
    for champ in ("prism_doi", "dc_identifier", "id", "link"):
        m = RE_DOI.search(str(e.get(champ, "")))
        if m:
            return m.group(0).rstrip(".")
    return ""


def analyser(contenu: bytes, nom: str, url_flux: str, depuis: dt.date) -> list[dict]:
    flux = feedparser.parse(contenu)
    preprint = "rxiv" in (nom + url_flux).lower()
    sortie = []
    for e in flux.entries:
        d = _date(e)
        if d and d < depuis:
            continue
        resume = e.get("summary") or e.get("description") or ""
        if e.get("content"):
            resume = max([c.get("value", "") for c in e.content] + [resume], key=len)
        sortie.append(nouvel_article(
            titre=e.get("title", ""), resume=resume,
            auteurs=[a.get("name", "") for a in e.get("authors", [])] or
                    ([e.get("author")] if e.get("author") else []),
            revue=nom, date=d.isoformat() if d else "", doi=_doi(e),
            url=e.get("link", ""), preprint=preprint, sources=["rss"],
        ))
    return sortie


def collecter(cfg, http, themes, depuis):
    opts = cfg["sources"].get("rss", {})
    from .. import sante
    articles = []
    for f in opts.get("flux", []) or []:
        try:
            lus = analyser(http.get(f["url"], tentatives=2).content, f["nom"], f["url"], depuis)
        except Exception as ex:  # un flux en panne ne bloque jamais le reste
            log.warning("  RSS ignoré (%s) : %s", f["nom"], ex)
            sante.noter_source(f"RSS {f['nom']}", echec=True)
            continue
        sante.noter_source(f"RSS {f['nom']}", recus=len(lus))
        gardes = []
        for a in lus:
            a["themes"] = themes_correspondants(a, themes)
            if a["themes"]:
                gardes.append(a)
        log.info("  RSS %s : %d/%d retenus", f["nom"], len(gardes), len(lus))
        articles += gardes
    for f in opts.get("flux_libres", []) or []:
        try:
            lus = analyser(http.get(f["url"], tentatives=2).content, f["nom"], f["url"], depuis)
        except Exception as ex:
            log.warning("  RSS ignoré (%s) : %s", f["nom"], ex)
            continue
        for a in lus:
            a["themes"] = [f.get("theme", "divers")]
            a["libre"] = True
        log.info("  RSS libre %s : %d", f["nom"], len(lus))
        articles += lus
    return articles
