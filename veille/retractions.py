"""Alerte si un article mis en favori est rétracté.

Chaque jour, les favoris de l'appli (lus dans le gist de synchronisation, secret SYNC_GIST_ID)
sont revérifiés auprès d'OpenAlex, qui reprend la base Retraction Watch. Un favori nouvellement
rétracté est marqué dans la base (badge « RÉTRACTÉ » sur le site) et signalé par une notification.
Tout est facultatif : sans gist, ou si OpenAlex ne répond pas, rien ne se passe et rien ne casse.
"""
from __future__ import annotations

import os

from .core import log

API = "https://api.openalex.org/works"
PAR_REQUETE = 50                       # OpenAlex accepte jusqu'à 100 DOI par filtre


def favoris() -> set[str] | None:
    from . import notifications        # import local : notifications dépend de pipeline
    if not notifications.gist_configure():
        return None
    etat = notifications.etat_appli()
    if etat is None:
        return None
    return {k for k, v in (etat.get("favoris") or {}).items() if v}


def verifier(cfg: dict, http, base) -> list[dict]:
    """Revérifie les favoris non encore marqués rétractés ; renvoie ceux qui viennent de l'être."""
    if not cfg.get("retractions", {}).get("actif", True):
        return []
    ids = favoris()
    if not ids:
        return []
    cibles = {a["doi"].lower(): a for a in base.articles
              if a["id"] in ids and a.get("doi") and not a.get("retracte")}
    if not cibles:
        return []
    params = {"select": "doi,is_retracted", "mailto": cfg.get("contact_email", "")}
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    dois = sorted(cibles)
    nouveaux = []
    for i in range(0, len(dois), PAR_REQUETE):
        lot = dois[i:i + PAR_REQUETE]
        data = http.get(API, params=dict(params, filter="doi:" + "|".join(lot), **{"per-page": len(lot)})).json()
        for w in data.get("results", []):
            doi = (w.get("doi") or "").lower().replace("https://doi.org/", "")
            a = cibles.get(doi)
            if a is not None and w.get("is_retracted"):
                a["retracte"] = True
                nouveaux.append(a)
    log.info("Rétractations : %d favoris vérifiés, %d nouvellement rétractés", len(cibles), len(nouveaux))
    return nouveaux


def alerter(cfg: dict, articles: list[dict]) -> bool:
    if not articles:
        return False
    from . import sante
    liste = "\n".join(f"• {a.get('titre', '')[:140]}" for a in articles[:10])
    titre = ("⚠️ SciFeed : un de tes favoris a été rétracté" if len(articles) == 1
             else f"⚠️ SciFeed : {len(articles)} de tes favoris ont été rétractés")
    return sante.envoyer_ntfy(cfg, titre, liste + "\n\nTouche pour voir la notice.", 4, ["warning"],
                              articles[0].get("url") or "")
