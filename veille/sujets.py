"""Sujets de recherche ajoutés par le lecteur dans l'appli (Filtres › Ajouter un sujet).

Ils sont gardés dans le gist de synchronisation (clé « sujets » de veille-synchro.json) :
  {"m_fibro": '{"nom": "Fibromyalgie", "mots": ["fibromyalg*", "central sensitization"], "titre": false}'}
Dans l'appli, ils filtrent tout de suite les articles déjà collectés. Ici, la collecte les ajoute
aux thèmes de config.yaml : chaque nuit, PubMed, Europe PMC, OpenAlex… sont aussi interrogés
avec ces mots-clés (un article est retenu s'il contient au moins un des mots-clés).
Garde-fous : 12 sujets au plus, 25 mots-clés par sujet, mots de 3 lettres ou plus."""
import json
import re

from .core import log

MAX_SUJETS, MAX_MOTS = 12, 25


def depuis_etat(etat: dict | None, deja: set[str] | None = None) -> list[dict]:
    """Thèmes de collecte (même forme que ceux de config.yaml) tirés de l'état de l'appli."""
    if not isinstance(etat, dict) or not isinstance(etat.get("sujets"), dict):
        return []
    deja = deja or set()
    themes = []
    for ident, valeur in sorted(etat["sujets"].items()):
        if len(themes) >= MAX_SUJETS:
            log.warning("Sujets de l'appli : plus de %d, les suivants sont ignorés", MAX_SUJETS)
            break
        if not re.fullmatch(r"m_[a-z0-9_]{1,40}", str(ident)) or ident in deja or not valeur:
            continue
        try:
            d = json.loads(valeur) if isinstance(valeur, str) else valeur
            nom = str(d["nom"]).strip()[:40]
            mots = [str(m).strip() for m in d["mots"] if len(str(m).replace("*", "").strip()) >= 3][:MAX_MOTS]
        except Exception:      # sujet mal formé : ignoré, jamais bloquant
            continue
        if not nom or not mots:
            continue
        th = {"id": ident, "nom": nom, "court": nom, "famille": "perso", "groupes": [mots],
              "titre_seulement": bool(d.get("titre")), "_groupes": [mots], "_groupes_titre": [], "perso": True}
        themes.append(th)
    return themes


def ajouter_aux_themes(cfg: dict, etat: dict | None) -> list[dict]:
    """Thèmes de config.yaml + sujets de l'appli (ceux-ci après, sans écraser un thème existant)."""
    themes = list(cfg.get("themes", []))
    persos = depuis_etat(etat, {t["id"] for t in themes})
    if persos:
        log.info("Sujets ajoutés dans l'appli : %s", ", ".join(t["nom"] for t in persos))
    return themes + persos
