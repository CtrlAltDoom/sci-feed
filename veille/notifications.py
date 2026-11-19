"""Notifications du matin via ntfy (appli gratuite Android / iOS, https://ntfy.sh).

Chaque matin : les N articles récents les mieux classés (même score que le tri « Pour moi » du site),
avec un titre court et une conclusion simple rédigés par l'IA, envoyés sur le canal ntfy du lecteur.
Le nom du canal est dans le secret GitHub NTFY_TOPIC (jamais dans le dépôt public).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time

import requests

from . import pipeline, revues
from .core import aujourd_hui, bonus_serieux, interet, log, themes_correspondants
from .resume_ia import ClientLLM, _extraire_json


def _fichier():
    return pipeline.DATA / "notifications.json"


def _etat() -> dict:
    f = _fichier()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"envoyes": {}}


def _sauver_etat(etat: dict):
    limite = (aujourd_hui() - dt.timedelta(days=90)).isoformat()
    etat["envoyes"] = {k: v for k, v in etat.get("envoyes", {}).items() if v >= limite}
    pipeline.DATA.mkdir(exist_ok=True)
    _fichier().write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- sélection
def score(a: dict, cfg: dict, info_revue: dict | None, etiquettes: list[str]) -> float:
    """Même calcul que le tri « Pour moi » du site (web/app.js, scorePourMoi)."""
    s = interet(a, cfg, etiquettes) + bonus_serieux(a, info_revue, cfg)
    f = a.get("fiche") or {}
    if f.get("pertinence"):
        s += f["pertinence"] - 3
    ajout = dt.date.fromisoformat(a.get("ajoute_le") or aujourd_hui().isoformat())
    try:
        ref = dt.date.fromisoformat((a.get("date") or "")[:10])
    except ValueError:
        ref = ajout
    ref = max(min(ref, ajout), ajout - dt.timedelta(days=30))
    age = max(0, (aujourd_hui() - ref).days)
    return s - age / ((cfg.get("interet") or {}).get("jours_par_point", 2))


def selectionner(cfg: dict, base, deja: set[str]) -> list[tuple[dict, dict | None, list[str]]]:
    n = cfg.get("notifications", {})
    infos = revues.charger()
    depuis = (aujourd_hui() - dt.timedelta(days=n.get("fenetre_jours", 2))).isoformat()
    inclure, exclure = set(n.get("inclure") or []), set(n.get("exclure") or [])
    candidats = []
    for a in base.articles:
        if a["id"] in deja or a.get("ajoute_le", "") < depuis or a.get("retracte"):
            continue
        e = themes_correspondants(a, cfg.get("etiquettes", []))
        ids = set(a.get("themes", [])) | set(e)
        if inclure and not ids & inclure or ids & exclure:
            continue
        info = revues.resume(infos.get(a.get("revue_oa") or ""))
        if (info or {}).get("niveau", 0) < n.get("revue_min", 0):
            continue
        if ((a.get("fiche") or {}).get("niveau_preuve") or 0) < n.get("preuve_min", 0):
            continue
        candidats.append((score(a, cfg, info, e), a, info, e))
    candidats.sort(key=lambda x: x[0], reverse=True)
    return [(a, info, e) for _, a, info, e in candidats[:n.get("nombre", 5)]]


# ---------------------------------------------------------------- textes courts (IA)
CONSIGNES = """Tu prépares des notifications de téléphone pour un {profil}
Pour chaque article, à partir de l'abstract UNIQUEMENT, rédige en français :
- "titre_court" : 50 caractères maximum. Le sujet et la population, clairement, sans jargon inutile ni sigle obscur.
- "conclusion_simple" : UNE phrase de 140 caractères maximum. Pas le résultat chiffré, mais ce que l'on peut en conclure
  en pratique, au vu des résultats ET des limites. Aucun chiffre. Nuance si l'étude est petite, préliminaire ou
  sans groupe contrôle (« à confirmer », « piste »). N'affirme jamais plus que l'abstract.
Réponds par un SEUL objet JSON : {{"items": [{{"id": "...", "titre_court": "...", "conclusion_simple": "..."}}]}}"""


def _couper(texte: str, maxi: int) -> str:
    texte = re.sub(r"\s+", " ", (texte or "")).strip()
    return texte if len(texte) <= maxi else texte[:maxi - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def textes_courts(cfg: dict, articles: list[dict], client=None) -> bool:
    """Complète fiche.titre_court / fiche.conclusion_simple des articles qui n'en ont pas (un seul appel)."""
    a_faire = [a for a in articles if len(a.get("resume", "")) >= 200
               and not ((a.get("fiche") or {}).get("conclusion_simple"))]
    if not a_faire:
        return False
    ia = cfg.get("ia", {})
    client = client or ClientLLM(ia)
    if not client.cle and "localhost" not in client.url:
        return False
    par_id = {f"a{i}": a for i, a in enumerate(a_faire)}
    texte = "\n\n".join(f"### id: {k}\nTitre : {a['titre']}\nAbstract : {a['resume'][:3000]}" for k, a in par_id.items())
    systeme = CONSIGNES.format(profil=ia.get("profil_lecteur", "").strip())
    for essai in range(2):
        try:
            contenu, modele = client.completer(systeme, texte)
            items = _extraire_json(contenu).get("items", [])
            break
        except Exception as ex:
            log.warning("Notifications : textes courts en échec (%s)", ex)
            items = []
    for it in items:
        a = par_id.get(str(it.get("id", "")).strip())
        if a is None or not it.get("conclusion_simple"):
            continue
        a["fiche"] = a.get("fiche") or {}
        a["fiche"]["titre_court"] = _couper(it.get("titre_court", ""), 60)
        a["fiche"]["conclusion_simple"] = _couper(it.get("conclusion_simple", ""), 180)
    return bool(items)


# ---------------------------------------------------------------- mise en forme et envoi
def _points(n: int) -> str:
    return "●" * n + "○" * (3 - n) if n else ""


def contenu(a: dict, info: dict | None, etiquettes: list[str]) -> tuple[str, str]:
    from .site import type_etude
    f = a.get("fiche") or {}
    titre = f.get("titre_court") or _couper(a.get("titre", ""), 80)
    if "animal" in etiquettes:
        titre = "🐁 " + titre
    phrase = f.get("conclusion_simple") or f.get("verdict") or ""
    et = type_etude(a)
    population = f.get("population") or ""
    if population.strip().lower() in ("null", "none", "non précisé", "n/a"):
        population = ""
    repere = " · ".join(x for x in [
        " · ".join([et["type"]] + et["details"][:2]).strip(" ·"),
        _couper(population, 40),
        f"{_couper(a.get('revue', ''), 40)} {_points((info or {}).get('niveau', 0))}".strip(),
        "preprint non relu" if a.get("preprint") else "",
    ] if x)
    return titre, "\n".join(x for x in [phrase, repere] if x)


def adresse_site(cfg: dict) -> str:
    if cfg.get("site_url"):
        return cfg["site_url"]
    depot = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in depot:
        proprio, nom = depot.split("/", 1)
        return f"https://{proprio.lower()}.github.io/{nom}/"
    return ""


def envoyer(cfg: dict, messages: list[dict]):
    n = cfg.get("notifications", {})
    serveur = n.get("serveur", "https://ntfy.sh").rstrip("/")
    canal = os.environ.get("NTFY_TOPIC", "")
    en_tetes = {"Authorization": f"Bearer {os.environ['NTFY_TOKEN']}"} if os.environ.get("NTFY_TOKEN") else {}
    priorite = int(n.get("priorite", 3))
    for m in messages:
        r = requests.post(serveur, json=dict(m, topic=canal, priority=priorite), headers=en_tetes, timeout=30)
        r.raise_for_status()
        time.sleep(1)


def notifier(cfg: dict, essai: bool = False, forcer: bool = False, client=None) -> int:
    n = cfg.get("notifications", {})
    if not n.get("actif", True) and not forcer:
        return 0
    if not os.environ.get("NTFY_TOPIC") and not essai:
        log.warning("Notifications : pas de canal (secret NTFY_TOPIC) : rien envoyé.")
        return 0
    etat = _etat()
    # fenêtre horaire (les tâches GitHub partent en retard et ignorent l'heure d'été : on vérifie ici)
    try:
        from zoneinfo import ZoneInfo
        maintenant = dt.datetime.now(ZoneInfo(n.get("fuseau", "Europe/Paris")))
    except Exception:
        maintenant = dt.datetime.now()
    heure = maintenant.strftime("%H:%M")
    if not (essai or forcer):
        if etat.get("dernier_envoi") == maintenant.date().isoformat():
            log.info("Notifications : déjà envoyées aujourd'hui.")
            return 0
        if not n.get("heure_min", "06:30") <= heure <= n.get("heure_max", "10:00"):
            log.info("Notifications : %s, hors de la plage %s-%s.", heure, n.get("heure_min", "06:30"), n.get("heure_max", "10:00"))
            return 0

    base = pipeline.charger()
    choix = selectionner(cfg, base, set(etat.get("envoyes", {})))
    if not choix:
        log.info("Notifications : aucun nouvel article à signaler.")
        return 0
    if textes_courts(cfg, [a for a, _, _ in choix], client):
        pipeline.sauvegarder(base)          # les textes courts servent aussi au site
    site = adresse_site(cfg)
    textes = [(a, *contenu(a, info, e)) for a, info, e in choix]

    if n.get("format", "par_article") == "resume":
        corps = "\n\n".join(f"{i}. {t}\n{m.splitlines()[0] if m else ''}" for i, (_, t, m) in enumerate(textes, 1))
        messages = [{"title": f"SciFeed : {len(textes)} articles ce matin", "message": corps,
                     "click": site or textes[0][0].get("url", ""), "tags": ["books"]}]
    else:
        messages = []
        for a, t, m in reversed(textes):        # le plus pertinent arrive en dernier = en haut de la liste
            msg = {"title": t, "message": m, "click": a.get("url") or site}
            if site:
                msg["actions"] = [{"action": "view", "label": "Ouvrir SciFeed", "url": site}]
            messages.append(msg)

    if essai:
        for m in messages:
            print(f"\n[{m['title']}]\n{m['message']}\n→ {m['click']}")
        return len(messages)
    envoyer(cfg, messages)
    for a, _, _ in choix:
        etat.setdefault("envoyes", {})[a["id"]] = aujourd_hui().isoformat()
    etat["dernier_envoi"] = maintenant.date().isoformat()
    _sauver_etat(etat)
    log.info("Notifications : %d envoyée(s).", len(messages))
    return len(messages)
