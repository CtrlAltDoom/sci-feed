"""Outils communs : configuration, HTTP, modèle d'article, dédoublonnage, filtrage."""
from __future__ import annotations

import datetime as dt
import html
import logging
import os
import re
import time
import unicodedata
from pathlib import Path

import requests
import yaml

log = logging.getLogger("veille")
RACINE = Path(__file__).resolve().parent.parent

DESIGNS_FORTS = ["randomized", "randomised", "controlled trial", "meta-analysis",
                 "meta-analyses", "meta-analytic", "systematic review", "umbrella review"]


# ---------------------------------------------------------------- configuration
def charger_config(chemin: str | Path | None = None) -> dict:
    chemin = Path(chemin) if chemin else RACINE / "config.yaml"
    with open(chemin, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # e-mail de contact hors du dépôt public : variable d'environnement prioritaire
    if os.environ.get("CONTACT_EMAIL"):
        cfg["contact_email"] = os.environ["CONTACT_EMAIL"]
    cfg.setdefault("collecte", {})
    cfg.setdefault("sources", {})
    cfg.setdefault("ia", {})
    for th in cfg.get("themes", []):
        groupes = [list(g) for g in th.get("groupes", []) if g]
        if th.get("designs_forts_seulement"):
            groupes.append(DESIGNS_FORTS)
        th["_groupes"] = groupes
    return cfg


def aujourd_hui() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


# ---------------------------------------------------------------- HTTP
class Http:
    """Session HTTP polie, avec reprises automatiques."""

    def __init__(self, email: str = ""):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = (
            f"VeilleScientifique/1.0 (open-source; mailto:{email or 'anonyme@example.com'})")

    def get(self, url, params=None, tentatives=3, timeout=40, **kw):
        derniere = None
        for i in range(tentatives):
            try:
                r = self.s.get(url, params=params, timeout=timeout, **kw)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                derniere = e
                if i < tentatives - 1:
                    time.sleep(3 * (i + 1))
        raise derniere


# ---------------------------------------------------------------- texte
_TAG = re.compile(r"<[^>]+>")


def nettoyer(texte: str | None) -> str:
    if not texte:
        return ""
    texte = html.unescape(_TAG.sub(" ", str(texte)))
    return re.sub(r"\s+", " ", texte).strip()


def titre_normalise(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)[:150]


def doi_propre(doi: str | None) -> str:
    if not doi:
        return ""
    doi = str(doi).strip().lower()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi)
    return doi if doi.startswith("10.") else ""


# ---------------------------------------------------------------- filtrage par mots-clés
def _motif(terme: str) -> re.Pattern:
    # espaces et tirets interchangeables : "gut-brain" = "gut brain" = "gut–brain"
    morceaux = [re.escape(m) for m in re.split(r"[\s\-‐–]+", terme.lower().strip()) if m]
    t = r"[\s\-‐–]*".join(morceaux)
    return re.compile(rf"(?<![a-z0-9]){t}(?![a-z0-9])")


_cache_motifs: dict[str, re.Pattern] = {}


def contient(texte: str, terme: str) -> bool:
    if terme not in _cache_motifs:
        _cache_motifs[terme] = _motif(terme)
    return bool(_cache_motifs[terme].search(texte))


def themes_correspondants(article: dict, themes: list[dict]) -> list[str]:
    texte = (f"{article.get('titre', '')} {article.get('resume', '')} "
             f"{' '.join(article.get('mots_cles') or [])}").lower()
    ids = []
    for th in themes:
        if all(any(contient(texte, t) for t in g) for g in th["_groupes"]):
            ids.append(th["id"])
    return ids


def est_exclu(article: dict, exclure: list[str]) -> bool:
    titre = (article.get("titre") or "").lower()
    return any(contient(titre, t) for t in exclure or [])


# ---------------------------------------------------------------- article
def nouvel_article(**champs) -> dict:
    a = {
        "id": "", "titre": "", "resume": "", "auteurs": [], "revue": "", "date": "",
        "doi": "", "pmid": "", "pmcid": "", "nct": "", "url": "", "url_libre": "",
        "types": [], "preprint": False, "retracte": False, "essai_registre": False,
        "sources": [], "themes": [], "ajoute_le": aujourd_hui().isoformat(), "fiche": None,
    }
    a.update({k: v for k, v in champs.items() if v not in (None, "")})
    a["doi"] = doi_propre(a["doi"])
    a["titre"] = nettoyer(a["titre"]).rstrip(".")
    a["resume"] = nettoyer(a["resume"])
    a["auteurs"] = [nettoyer(x) for x in a["auteurs"] if x][:12]
    if not a["url"]:
        if a["doi"]:
            a["url"] = f"https://doi.org/{a['doi']}"
        elif a["pmid"]:
            a["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/"
    return a


def cles(a: dict) -> list[str]:
    k = []
    if a.get("doi"):
        k.append("doi:" + a["doi"])
    if a.get("pmid"):
        k.append("pmid:" + str(a["pmid"]))
    if a.get("nct"):
        k.append("nct:" + a["nct"])
    tn = titre_normalise(a.get("titre", ""))
    if len(tn) > 25:
        k.append("t:" + tn)
    return k


def fusionner(dest: dict, src: dict) -> dict:
    """Complète `dest` avec les informations de `src` sans rien perdre."""
    for champ in ("doi", "pmid", "pmcid", "nct", "revue", "date", "url_libre"):
        if not dest.get(champ) and src.get(champ):
            dest[champ] = src[champ]
    if len(src.get("resume", "")) > len(dest.get("resume", "")) + 40:
        dest["resume"] = src["resume"]
    if len(src.get("auteurs", [])) > len(dest.get("auteurs", [])):
        dest["auteurs"] = src["auteurs"]
    if "pubmed.ncbi" in src.get("url", "") and not dest.get("url"):
        dest["url"] = src["url"]
    for liste in ("types", "sources", "themes"):
        dest[liste] = sorted(set(dest.get(liste, [])) | set(src.get(liste, [])))
    dest["retracte"] = dest.get("retracte") or src.get("retracte", False)
    # un article indexé dans PubMed avec une revue n'est plus considéré comme preprint
    dest["preprint"] = bool(dest.get("preprint") or src.get("preprint")) and \
        "pubmed" not in dest["sources"]
    if not dest.get("fiche") and src.get("fiche"):
        dest["fiche"] = src["fiche"]
    return dest


class Base:
    """Ensemble d'articles dédoublonnés (DOI, PMID, NCT ou titre)."""

    def __init__(self, articles: list[dict] | None = None):
        self.articles: list[dict] = []
        self.index: dict[str, dict] = {}
        for a in articles or []:
            self.ajouter(a)

    def ajouter(self, a: dict) -> bool:
        """Retourne True si l'article est nouveau."""
        existant = next((self.index[k] for k in cles(a) if k in self.index), None)
        if existant:
            fusionner(existant, a)
            for k in cles(existant):
                self.index[k] = existant
            return False
        if not a.get("id"):
            a["id"] = (cles(a) or ["x:" + str(len(self.articles))])[0]
        self.articles.append(a)
        for k in cles(a):
            self.index[k] = a
        return True
