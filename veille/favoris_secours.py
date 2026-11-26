"""Copie de secours des favoris, dans un gist secret à part (jamais dans le dépôt public).

Le gist de synchronisation de l'appli (SYNC_GIST_ID) peut être vidé par accident (nouveau
téléphone, fausse manœuvre…). Chaque nuit, la veille recopie donc chaque favori, avec sa fiche
complète, dans un second gist secret, « scifeed-favoris-secours.json ». Il faut pour cela un jeton
GitHub qui n'a que le droit « gist », dans le secret GIST_TOKEN. Le gist de secours est retrouvé
(ou créé au premier passage) grâce à ce jeton : son identifiant n'est écrit nulle part.

Sans GIST_TOKEN, il n'y a pas de copie, et rien ne casse : les favoris restent protégés par le
gist de synchronisation seul.
"""
from __future__ import annotations

import json
import os

import requests

from .core import log

API = "https://api.github.com"
FICHIER = "scifeed-favoris-secours.json"
DESCRIPTION = "SciFeed : copie de secours des favoris (créée par la veille, ne pas supprimer)"


class Illisible(Exception):
    """La copie de secours existe peut-être mais n'a pas pu être lue : ne rien effacer."""


def jeton() -> str:
    return os.environ.get("GIST_TOKEN", "").strip()


def configure() -> bool:
    return bool(jeton())


def _en_tetes() -> dict:
    return {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {jeton()}"}


def lire() -> tuple[str | None, dict]:
    """(identifiant du gist de secours ou None s'il n'existe pas encore, copie {id: {...}}).
    Lève Illisible si GitHub ne répond pas ou si le contenu est abîmé."""
    try:
        for page in range(1, 31):
            r = requests.get(f"{API}/gists", headers=_en_tetes(),
                             params={"per_page": 100, "page": page}, timeout=30)
            r.raise_for_status()
            liste = r.json()
            g = next((x for x in liste if FICHIER in (x.get("files") or {})), None)
            if g:
                break
            if len(liste) < 100:
                return None, {}
        else:
            return None, {}
        r = requests.get(f"{API}/gists/{g['id']}", headers=_en_tetes(), timeout=30)
        r.raise_for_status()
        f = (r.json().get("files") or {}).get(FICHIER) or {}
        contenu = f.get("content", "")
        if f.get("truncated") and f.get("raw_url"):
            rr = requests.get(f["raw_url"], headers=_en_tetes(), timeout=60)
            rr.raise_for_status()
            contenu = rr.text
        donnees = json.loads(contenu)
        copie = donnees.get("favoris")
        if not isinstance(copie, dict):
            raise ValueError("pas de liste de favoris")
        return g["id"], copie
    except Exception as ex:
        raise Illisible(str(ex)) from ex


def ecrire(gist_id: str | None, copie: dict) -> str | None:
    """Enregistre la copie (crée le gist secret s'il n'existe pas). Renvoie son identifiant,
    ou None en cas d'échec (on retentera la nuit suivante ; la purge, elle, s'appuie sur la
    copie en mémoire, donc rien n'est perdu)."""
    contenu = json.dumps({"note": "Favoris de l'appli SciFeed : ces articles ne sont jamais effacés de la base.",
                          "favoris": dict(sorted(copie.items()))}, ensure_ascii=False, indent=1)
    corps = {"files": {FICHIER: {"content": contenu}}}
    try:
        if gist_id:
            r = requests.patch(f"{API}/gists/{gist_id}", headers=_en_tetes(), json=corps, timeout=60)
        else:
            r = requests.post(f"{API}/gists", headers=_en_tetes(),
                              json=dict(corps, description=DESCRIPTION, public=False), timeout=60)
        r.raise_for_status()
        return r.json().get("id") or gist_id
    except Exception as ex:
        log.warning("Copie de secours des favoris non enregistrée (gist) : %s", ex)
        return None
