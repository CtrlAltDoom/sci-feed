"""Santé de la veille : repérer les pannes silencieuses et prévenir le lecteur (ntfy).

Chaque passage quotidien note ce qu'il a obtenu (data/sante.json) : résultats et échecs par source,
nouveaux articles, fiches IA rédigées, file d'attente. Si un problème dure, une notification ntfy
« ⚠️ SciFeed » part (au plus une fois par jour, rappel tous les 7 jours si ça persiste), puis une
notification « ✅ » quand tout est revenu dans l'ordre.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import requests

from . import pipeline
from .core import aujourd_hui, log

HISTORIQUE = 30          # passages gardés


def _fichier():
    return pipeline.DATA / "sante.json"


def charger() -> dict:
    f = _fichier()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"passages": [], "alertes": {}}


def sauver(etat: dict):
    etat["passages"] = etat.get("passages", [])[-HISTORIQUE:]
    pipeline.DATA.mkdir(exist_ok=True)
    _fichier().write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- relevé d'un passage
class Releve:
    """Ce qu'un passage de la veille a obtenu ; complété par la collecte et les fiches IA."""

    def __init__(self):
        self.p = {"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                  "sources": {}, "nouveaux": None, "fiches": None, "attente": None, "ia_erreur": ""}

    def source(self, nom: str, recus: int = 0, echec: bool = False):
        s = self.p["sources"].setdefault(nom, {"essais": 0, "echecs": 0, "recus": 0})
        s["essais"] += 1
        s["echecs"] += int(echec)
        s["recus"] += recus

    def enregistrer(self):
        etat = charger()
        etat.setdefault("passages", []).append(self.p)
        sauver(etat)


RELEVE: Releve | None = None     # relevé du passage en cours (None : rien n'est noté, ex. dans les tests)


def noter_source(nom, recus=0, echec=False):
    if RELEVE:
        RELEVE.source(nom, recus, echec)


def noter(**valeurs):
    if RELEVE:
        RELEVE.p.update(valeurs)


# ---------------------------------------------------------------- diagnostic
def problemes(passages: list[dict], cfg: dict) -> dict[str, str]:
    """Problèmes qui durent, d'après les derniers passages complets. Clé stable -> message lisible."""
    s = cfg.get("sante", {})
    jours_source = s.get("source_jours", 2)
    jours_ia = s.get("ia_jours", 2)
    jours_vide = s.get("collecte_vide_jours", 3)
    complets = [p for p in passages if p.get("nouveaux") is not None]
    out = {}

    # une source en panne (tous ses appels en échec, ou plus aucun résultat) plusieurs passages de suite
    noms = set().union(*(p["sources"] for p in complets[-jours_source:])) if complets else set()
    for nom in sorted(noms):
        derniers = [p["sources"].get(nom) for p in complets[-jours_source:]]
        if len(derniers) < jours_source or None in derniers:
            continue
        if all(d["essais"] and d["echecs"] == d["essais"] for d in derniers):
            out[f"source:{nom}"] = f"{nom} : en échec depuis {jours_source} passages"
        elif all(d["recus"] == 0 and d["echecs"] for d in derniers):
            out[f"source:{nom}"] = f"{nom} : erreurs et aucun résultat depuis {jours_source} passages"

    # plus aucune fiche IA alors que des articles attendent
    derniers = [p for p in passages if p.get("fiches") is not None][-jours_ia:]
    if len(derniers) == jours_ia and all(p["fiches"] == 0 and (p.get("attente") or 0) > 0 for p in derniers):
        raison = derniers[-1].get("ia_erreur") or "aucune réponse exploitable"
        out["ia"] = f"Fiches IA : 0 depuis {jours_ia} passages ({raison[:120]})"

    # plus aucun nouvel article depuis plusieurs jours
    derniers = complets[-jours_vide:]
    if len(derniers) == jours_vide and all(p["nouveaux"] == 0 for p in derniers):
        out["collecte"] = f"Aucun nouvel article depuis {jours_vide} passages"
    return out


def collecte_en_retard(cfg: dict) -> dict[str, str]:
    """La tâche quotidienne n'a pas tourné (GitHub l'a désactivée, ou elle échoue avant la fin)."""
    etat = pipeline._etat()
    derniere = etat.get("derniere_collecte")
    heures = cfg.get("sante", {}).get("retard_heures", 36)
    if not derniere:
        return {}
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(derniere)
    if age > dt.timedelta(hours=heures):
        return {"retard": f"Pas de collecte depuis {age.days} j {age.seconds // 3600} h "
                          "(tâche « Veille quotidienne » arrêtée ou en échec)"}
    return {}


# ---------------------------------------------------------------- alerte
def envoyer_ntfy(cfg: dict, titre: str, message: str, priorite: int = 4, tags=None, click: str = ""):
    canal = os.environ.get("NTFY_TOPIC", "")
    if not canal:
        return False
    serveur = cfg.get("notifications", {}).get("serveur", "https://ntfy.sh").rstrip("/")
    en_tetes = {"Authorization": f"Bearer {os.environ['NTFY_TOKEN']}"} if os.environ.get("NTFY_TOKEN") else {}
    corps = {"topic": canal, "title": titre, "message": message, "priority": priorite, "tags": tags or []}
    if click:
        corps["click"] = click
    r = requests.post(serveur, json=corps, headers=en_tetes, timeout=30)
    r.raise_for_status()
    return True


def _lien_actions() -> str:
    depot = os.environ.get("GITHUB_REPOSITORY", "")
    return f"https://github.com/{depot}/actions" if depot else ""


def alerter(cfg: dict, actuels: dict[str, str], etat: dict | None = None) -> str:
    """Prévient si de nouveaux problèmes apparaissent (ou rappel après N jours), et quand ils disparaissent.
    Renvoie "alerte", "retabli" ou ""."""
    if not cfg.get("sante", {}).get("actif", True):
        return ""
    etat = etat if etat is not None else charger()
    connus: dict = etat.setdefault("alertes", {})      # clé -> date du dernier signalement
    auj = aujourd_hui()
    rappel = dt.timedelta(days=cfg.get("sante", {}).get("rappel_jours", 7))
    nouveaux = {k: m for k, m in actuels.items()
                if k not in connus or auj - dt.date.fromisoformat(connus[k]) >= rappel}
    resolus = [k for k in connus if k not in actuels]
    resultat = ""
    try:
        if nouveaux:
            texte = "\n".join(f"• {m}" for m in actuels.values())
            if envoyer_ntfy(cfg, "⚠️ SciFeed : quelque chose ne va pas", texte, 4, ["warning"], _lien_actions()):
                for k in actuels:
                    if k in nouveaux:
                        connus[k] = auj.isoformat()
                resultat = "alerte"
        elif resolus and not actuels:
            if envoyer_ntfy(cfg, "✅ SciFeed : tout est rentré dans l'ordre",
                            "Les problèmes signalés ont disparu.", 3, ["white_check_mark"]):
                resultat = "retabli"
        for k in resolus:
            connus.pop(k, None)
    except Exception as ex:          # l'alerte ne doit jamais faire échouer la veille
        log.warning("Santé : alerte non envoyée (%s)", ex)
    sauver(etat)
    if actuels:
        log.warning("Santé : %s", " | ".join(actuels.values()))
    return resultat


def verifier(cfg: dict, avec_retard: bool = False) -> str:
    etat = charger()
    actuels = problemes(etat.get("passages", []), cfg)
    if avec_retard:
        actuels.update(collecte_en_retard(cfg))
    return alerter(cfg, actuels, etat)
