"""Textes intégraux gratuits et légaux via Unpaywall (https://unpaywall.org).

OpenAlex, PubMed (PMC) et Europe PMC donnent déjà un lien libre pour une bonne part des articles.
Unpaywall complète les autres (dépôts d'archives ouvertes, versions auteur acceptées…).
Un article sans version libre est revérifié de temps en temps : la version libre arrive souvent
quelques semaines après la publication (embargo, dépôt dans HAL ou PubMed Central…).
"""
from __future__ import annotations

import datetime as dt
import time

from .core import aujourd_hui, log

API = "https://api.unpaywall.org/v2/"


def _a_verifier(a: dict, auj: dt.date, revoir: int, age_max: int) -> bool:
    if not a.get("doi") or a.get("url_libre") or a.get("essai_registre"):
        return False
    vu = a.get("libre_verifie")
    if not vu:
        return True
    # revérifier les articles récents seulement (au-delà, la situation ne change presque plus)
    publie = (a.get("date") or a.get("ajoute_le") or "")[:10]
    try:
        if (auj - dt.date.fromisoformat(publie)).days > age_max:
            return False
    except ValueError:
        pass
    return (auj - dt.date.fromisoformat(vu)).days >= revoir


def meilleur_lien(data: dict) -> str:
    loc = data.get("best_oa_location") or {}
    return loc.get("url_for_pdf") or loc.get("url") or loc.get("url_for_landing_page") or ""


def completer(cfg: dict, http, base) -> int:
    o = cfg.get("texte_libre", {})
    email = cfg.get("contact_email", "")
    if not o.get("actif", True):
        return 0
    if not email:                     # Unpaywall exige une adresse de contact (secret CONTACT_EMAIL)
        log.info("Unpaywall ignoré : pas d'e-mail de contact (secret CONTACT_EMAIL)")
        return 0
    auj = aujourd_hui()
    a_faire = [a for a in base.articles
               if _a_verifier(a, auj, o.get("revoir_jours", 30), o.get("age_max_jours", 365))]
    a_faire = a_faire[:o.get("max_par_passage", 200)]
    trouves = echecs = 0
    for a in a_faire:
        try:
            r = http.get(API + a["doi"], params={"email": email}, tentatives=1, timeout=20)
            lien = meilleur_lien(r.json())
            if lien:
                a["url_libre"] = lien
                trouves += 1
        except Exception as ex:
            code = getattr(getattr(ex, "response", None), "status_code", None)
            if code != 404:           # 404 = DOI inconnu d'Unpaywall : vérifié, rien à trouver
                echecs += 1
                log.debug("Unpaywall %s : %s", a["doi"], ex)
                if echecs >= 10:
                    log.warning("Unpaywall semble indisponible, la suite au prochain passage")
                    break
                continue              # erreur passagère : on réessaiera au prochain passage
        a["libre_verifie"] = auj.isoformat()
        time.sleep(0.1)
    if a_faire:
        log.info("Unpaywall : %d texte(s) libre(s) trouvé(s) sur %d vérifiés", trouves, len(a_faire))
    return trouves
