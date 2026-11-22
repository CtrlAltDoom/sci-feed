"""Fiches en MP3 (voix neuronales gratuites de Microsoft Edge, via edge-tts) : à écouter écran éteint.

Chaque jour, après les fiches IA : un MP3 pour chaque article récent qui a une fiche et qui compte
(notifié, à notifier, favori, ou très pertinent). Le texte lu est celui du bouton « Écouter » de
l'appli (web/app.js, fonction texte). Les MP3 ne vont jamais dans le dépôt : ils sont dans audio/
(ignoré par git), gardé d'un jour à l'autre par le cache de GitHub Actions, et recopiés dans
site/audio/ à chaque génération du site. Un MP3 n'est refait que si son texte a changé.
Toute erreur (réseau, service muet…) n'est qu'un avertissement : la veille continue sans MP3.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time

from .core import RACINE, aujourd_hui, log

DOSSIER = RACINE / "audio"
MANIFESTE = "audio.json"


def reglages(cfg: dict) -> dict:
    r = {"actif": True, "voix": "fr-FR-DeniseNeural", "voix_en": "en-US-AriaNeural",
         "jours_conserves": 7, "max_par_jour": 25, "pertinence_min": 4}
    r.update(cfg.get("audio") or {})
    return r


def nom_fichier(id_article: str) -> str:
    return hashlib.sha1(id_article.encode("utf-8")).hexdigest()[:16] + ".mp3"


# ---------------------------------------------------------------- texte lu (comme texte(a) dans web/app.js)
def _phrase(t) -> str:
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if not t or re.search(r"[.!?]$", t) else t + "."


def morceaux(a: dict) -> list[tuple[str, str]]:
    """[(langue, texte)] : le titre original est lu en anglais, la fiche en français."""
    f = a.get("fiche") or {}
    m: list[tuple[str, str]] = []
    fr = lambda t: m.append(("fr", _phrase(t))) if t else None
    if f.get("titre_court"):
        fr(f["titre_court"])
    elif a.get("titre"):
        m.append(("en", _phrase(a["titre"])))
    fr(f.get("verdict"))
    if f.get("population"):
        fr("Population : " + str(f["population"]))
    if f.get("intervention"):
        fr("Intervention : " + str(f["intervention"]))
    for x in f.get("resultats_cles") or []:
        fr(x)
    if f.get("conclusion"):
        fr("Conclusion des auteurs : " + str(f["conclusion"]))
    if f.get("limites"):
        fr("Limites : " + ". ".join(str(x) for x in f["limites"]))
    if f.get("pertinence_raison"):
        fr("Pour toi : " + str(f["pertinence_raison"]))
    # phrases consécutives de même langue : un seul appel à la voix
    groupes: list[tuple[str, str]] = []
    for lang, t in m:
        if groupes and groupes[-1][0] == lang:
            groupes[-1] = (lang, groupes[-1][1] + " " + t)
        else:
            groupes.append((lang, t))
    return groupes


def empreinte(a: dict, r: dict) -> str:
    brut = json.dumps([morceaux(a), r["voix"], r["voix_en"]], ensure_ascii=False)
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- sélection
def selectionner(cfg: dict, base, favoris: set[str] | None = None) -> list[dict]:
    """Articles récents avec fiche IA : notifiés (ou en tête pour la prochaine notification),
    favoris, ou de pertinence au moins pertinence_min. Les plus intéressants d'abord."""
    r = reglages(cfg)
    depuis = (aujourd_hui() - dt.timedelta(days=int(r["jours_conserves"]))).isoformat()
    recents = [a for a in base.articles if a.get("fiche") and not a.get("retracte")
               and a.get("ajoute_le", "") >= depuis]
    if not recents:
        return []
    from . import notifications   # import local : notifications dépend de pipeline
    envoyes = set(notifications._etat().get("envoyes", {}))
    try:                           # ceux que la notification de demain matin choisira (même calcul)
        a_notifier = {a["id"] for a, _, _ in notifications.selectionner(cfg, base, envoyes)}
    except Exception as ex:
        log.debug("audio : sélection des notifications impossible (%s)", ex)
        a_notifier = set()
    favoris = favoris or set()
    pmin = r["pertinence_min"]

    def raison(a):
        if a["id"] in envoyes or a["id"] in a_notifier:
            return 0
        if a["id"] in favoris:
            return 1
        if ((a.get("fiche") or {}).get("pertinence") or 0) >= pmin:
            return 2
        return None

    choix = [(raison(a), a) for a in recents]
    choix = [(k, a) for k, a in choix if k is not None]
    choix.sort(key=lambda x: x[1].get("ajoute_le", ""), reverse=True)        # les plus récents d'abord…
    choix.sort(key=lambda x: (x[0], -((x[1].get("fiche") or {}).get("pertinence") or 0)))  # …à raison égale
    return [a for _, a in choix]


def favoris_appli() -> set[str]:
    from . import notifications
    if not notifications.gist_configure():
        return set()
    etat = notifications.etat_appli() or {}
    return {k for k, v in (etat.get("favoris") or {}).items() if v}


# ---------------------------------------------------------------- voix
def synthetiser(texte: str, voix: str) -> bytes:
    """MP3 d'un texte (edge-tts, service gratuit sans clé). Remplacé par un faux dans les tests."""
    import asyncio

    import edge_tts

    async def _go():
        morceaux_audio = []
        async for c in edge_tts.Communicate(texte, voix).stream():
            if c.get("type") == "audio":
                morceaux_audio.append(c["data"])
        return b"".join(morceaux_audio)

    return asyncio.run(_go())


def mp3(a: dict, r: dict) -> bytes:
    # même format MP3 pour les deux voix : les morceaux se mettent bout à bout
    return b"".join(synthetiser(t, r["voix"] if lang == "fr" else r["voix_en"]) for lang, t in morceaux(a))


# ---------------------------------------------------------------- manifeste
def charger_manifeste(dossier=None) -> dict:
    f = (dossier or DOSSIER) / MANIFESTE
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        return {}


def purger(manifeste: dict, r: dict, dossier=None) -> int:
    """Efface les MP3 générés il y a plus de jours_conserves jours, et les fichiers orphelins."""
    dossier = dossier or DOSSIER
    limite = (aujourd_hui() - dt.timedelta(days=int(r["jours_conserves"]))).isoformat()
    for k in [k for k, v in manifeste.items() if v.get("jour", "") < limite]:
        del manifeste[k]
    gardes = {v["fichier"] for v in manifeste.values()}
    effaces = 0
    for f in dossier.glob("*.mp3"):
        if f.name not in gardes:
            f.unlink()
            effaces += 1
    for k in [k for k, v in manifeste.items() if not (dossier / v["fichier"]).exists()]:
        del manifeste[k]
    return effaces


def generer(cfg: dict, base=None, favoris: set[str] | None = None) -> dict:
    """Crée ou met à jour les MP3 ; renvoie un relevé {nouveaux, gardes, echecs, effaces, octets, secondes}."""
    r = reglages(cfg)
    releve = {"nouveaux": 0, "gardes": 0, "echecs": 0, "effaces": 0, "octets": 0, "secondes": 0.0}
    if not r.get("actif", True):
        return releve
    debut = time.monotonic()
    try:
        if base is None:
            from .pipeline import charger
            base = charger()
        if favoris is None:
            favoris = favoris_appli()
        DOSSIER.mkdir(exist_ok=True)
        manifeste = charger_manifeste()
        choix = selectionner(cfg, base, favoris)
        a_faire = []
        for a in choix:
            e = empreinte(a, r)
            v = manifeste.get(a["id"])
            if v and v.get("empreinte") == e and (DOSSIER / v["fichier"]).exists():
                releve["gardes"] += 1
            else:
                a_faire.append((a, e))
        for a, e in a_faire[:int(r["max_par_jour"])]:
            try:
                donnees = mp3(a, r)
                if len(donnees) < 1000:
                    raise RuntimeError("réponse vide")
            except Exception as ex:
                releve["echecs"] += 1
                log.warning("audio : MP3 de %s en échec (%s)", a["id"], ex)
                if releve["echecs"] >= 3 and not releve["nouveaux"]:
                    log.warning("audio : service de voix indisponible, on s'arrête là pour aujourd'hui")
                    break
                continue
            nom = nom_fichier(a["id"])
            (DOSSIER / nom).write_bytes(donnees)
            manifeste[a["id"]] = {"fichier": nom, "jour": aujourd_hui().isoformat(), "empreinte": e}
            releve["nouveaux"] += 1
        releve["effaces"] = purger(manifeste, r)
        (DOSSIER / MANIFESTE).write_text(json.dumps(manifeste, ensure_ascii=False, indent=1), encoding="utf-8")
        releve["octets"] = sum((DOSSIER / v["fichier"]).stat().st_size for v in manifeste.values())
    except Exception as ex:                 # jamais d'échec de la veille à cause des MP3
        log.warning("audio : génération des MP3 en échec (%s)", ex)
    releve["secondes"] = round(time.monotonic() - debut, 1)
    log.info("audio : %d MP3 créés, %d inchangés, %d échecs, %d effacés (%d Mo au total, %.0f s)",
             releve["nouveaux"], releve["gardes"], releve["echecs"], releve["effaces"],
             releve["octets"] // 1_000_000, releve["secondes"])
    return releve


def pour_le_site(dossier=None) -> dict[str, str]:
    """{id article: chemin relatif du MP3} pour data.json (fichiers présents seulement)."""
    dossier = dossier or DOSSIER
    return {k: f"audio/{v['fichier']}" for k, v in charger_manifeste(dossier).items()
            if (dossier / v.get("fichier", "?")).exists()}
