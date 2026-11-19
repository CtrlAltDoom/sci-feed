"""Orchestration : collecte -> dédoublonnage -> enrichissement -> sauvegarde."""
from __future__ import annotations

import datetime as dt
import json
import time

from . import sante
from .core import (RACINE, Base, Http, aujourd_hui, est_exclu, log, themes_correspondants)
from .sources import clinicaltrials, europepmc, openalex, pubmed, rss

DATA = RACINE / "data"
FICHIER = DATA / "articles.json"
ETAT = DATA / "etat.json"
SOURCES_API = {"pubmed": pubmed, "europepmc": europepmc, "openalex": openalex,
               "clinicaltrials": clinicaltrials}
# OpenAlex (recherche avec racinisation) et ClinicalTrials.gov (recherche dans toute la fiche,
# y compris lieux et critères) renvoient beaucoup de bruit : leurs résultats sont refiltrés.
FILTRE_LOCAL = {"openalex", "clinicaltrials"}


def charger() -> Base:
    if FICHIER.exists():
        return Base(json.loads(FICHIER.read_text(encoding="utf-8")))
    return Base()


def sauvegarder(base: Base, etat: dict | None = None):
    DATA.mkdir(exist_ok=True)
    arts = sorted(base.articles, key=lambda a: (a.get("ajoute_le", ""), a.get("date", "")),
                  reverse=True)
    FICHIER.write_text(json.dumps(arts, ensure_ascii=False, indent=0), encoding="utf-8")
    if etat is not None:
        ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=2), encoding="utf-8")


def _etat() -> dict:
    return json.loads(ETAT.read_text(encoding="utf-8")) if ETAT.exists() else {}


def enrichir(http: Http, base: Base, maxi: int = 40):
    """Complète l'abstract (et le PMID) des articles qui n'en ont pas, via Europe PMC."""
    a_faire = [a for a in base.articles if a.get("doi") and len(a.get("resume", "")) < 200
               and not a.get("essai_registre")][:maxi]
    # Europe PMC répond parfois en 20 s par requête : on interroge les DOI par lots de 20
    for i in range(0, len(a_faire), 20):
        lot = {a["doi"]: a for a in a_faire[i:i + 20]}
        requete = " OR ".join(f'DOI:"{d}"' for d in lot)
        try:
            data = http.get(europepmc.API, params={"query": requete, "format": "json",
                                                   "resultType": "core", "pageSize": 100}).json()
            for t in europepmc.analyser(data.get("resultList", {}).get("result", [])):
                a = lot.get(t.get("doi"))
                if a:
                    t["sources"] = a["sources"]  # ne pas compter Europe PMC comme source de veille
                    base.ajouter(t)
        except Exception as ex:
            log.debug("enrichissement (lot %d) : %s", i // 20, ex)
        time.sleep(0.2)


def collecter(cfg: dict) -> int:
    http = Http(cfg.get("contact_email", ""))
    base = charger()
    etat = _etat()
    jour = aujourd_hui()
    c = cfg["collecte"]
    recul = c.get("jours_glissants", 4) if etat.get("derniere_collecte") else c.get("jours_initiaux", 21)
    depuis = jour - dt.timedelta(days=recul)
    themes = cfg.get("themes", [])
    log.info("Collecte depuis le %s (%d thèmes)", depuis, len(themes))

    recus = []
    for nom, module in SOURCES_API.items():
        if not cfg["sources"].get(nom, {}).get("actif", False):
            continue
        for th in themes:
            try:
                lot = module.collecter(cfg, http, th, depuis, jour)
            except Exception as ex:  # une source en panne ne bloque jamais les autres
                log.warning("  %s [%s] en échec : %s", nom, th["id"], ex)
                sante.noter_source(nom, echec=True)
                continue
            sante.noter_source(nom, recus=len(lot))
            if nom in FILTRE_LOCAL:
                # recherche plein texte trop large côté serveur : on revérifie les mots-clés du thème
                lot = [a for a in lot if themes_correspondants(a, [th])]
                log.info("    après filtrage local : %d", len(lot))
            for a in lot:
                a["themes"] = sorted(set(a["themes"]) | {th["id"]})
            recus += lot
    if cfg["sources"].get("rss", {}).get("actif", False):
        recus += rss.collecter(cfg, http, themes, depuis)

    nouveaux = 0
    for a in recus:
        if est_exclu(a, c.get("exclure")):
            continue
        if not a.get("libre"):
            a["themes"] = sorted(set(a["themes"]) | set(themes_correspondants(a, themes)))
        nouveaux += base.ajouter(a)

    enrichir(http, base)
    from . import libre, revues   # import local : ces modules dépendent de pipeline
    try:
        revues.completer(cfg, http, base)
    except Exception as ex:       # facultatif : ne bloque jamais la veille
        log.warning("Infos revues en échec : %s", ex)
    try:
        libre.completer(cfg, http, base)
    except Exception as ex:
        log.warning("Textes intégraux libres (Unpaywall) en échec : %s", ex)
    sante.noter(nouveaux=nouveaux)
    limite =(jour - dt.timedelta(days=c.get("conserver_jours", 180))).isoformat()
    base = Base([a for a in base.articles if a.get("ajoute_le", "") >= limite])
    etat["derniere_collecte"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    sauvegarder(base, etat)
    log.info("Collecte terminée : %d nouveaux, %d au total", nouveaux, len(base.articles))
    return nouveaux
