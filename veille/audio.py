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
         "jours_conserves": 7, "max_par_jour": 25, "pertinence_min": 4, "jour": True}
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
    """{id article (ou jour:AAAA-MM-JJ): chemin relatif du MP3} pour le site (fichiers présents seulement)."""
    dossier = dossier or DOSSIER
    return {k: f"audio/{v['fichier']}" for k, v in charger_manifeste(dossier).items()
            if (dossier / v.get("fichier", "?")).exists()}


# ================================================================ audio du jour
# Un seul MP3 (3 à 5 min, une seule voix) qui présente les articles que la notification du matin
# enverra. La sélection de la nuit est enregistrée (data/selection-du-jour.json, poussé avec la base)
# et reprise telle quelle par notifications.py : l'audio et les notifications parlent des mêmes articles.
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
OCTETS_PAR_SECONDE = 6000          # edge-tts : MP3 mono à 48 kbit/s


def jour_local(cfg: dict) -> dt.date:
    """Date du jour à l'heure du lecteur (celle des notifications)."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo((cfg.get("notifications") or {}).get("fuseau", "Europe/Paris"))).date()
    except Exception:
        return aujourd_hui()


def date_parlee(jour: dt.date, avec_jour: bool = True) -> str:
    d = f"{'1er' if jour.day == 1 else jour.day} {MOIS[jour.month - 1]}"
    return f"{JOURS[jour.weekday()]} {d}" if avec_jour else d


def _fichier_selection():
    from .pipeline import DATA
    return DATA / "selection-du-jour.json"


def enregistrer_selection(cfg: dict, base, jour: dt.date | None = None) -> list[dict]:
    """Choisit, comme la notification du matin, les articles du jour et les enregistre."""
    from . import notifications
    jour = jour or jour_local(cfg)
    n = cfg.get("notifications") or {}
    exclus = set(notifications._etat().get("envoyes", {}))
    if n.get("ignorer_deja_vus", True):
        exclus |= notifications.deja_vus_dans_l_appli()
    choix = [a for a, _, _ in notifications.selectionner(cfg, base, exclus)]
    f = _fichier_selection()
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps({"jour": jour.isoformat(), "ids": [a["id"] for a in choix]}, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    log.info("Audio du jour : %d articles retenus (les mêmes que la notification du matin)", len(choix))
    return choix


def selection_enregistree(jour: dt.date) -> list[str] | None:
    """Identifiants choisis la nuit pour ce jour-là, ou None (pas de sélection, ou d'un autre jour)."""
    f = _fichier_selection()
    try:
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        return None
    return list(d.get("ids") or []) if d.get("jour") == jour.isoformat() else None


CONSIGNES_SCRIPT = """Tu écris le texte d'une courte chronique audio, lue par une voix de synthèse, pour un {profil}
Objectif : 3 à 5 minutes à l'oral, soit 450 à 700 mots au total.
- Commence par une introduction très courte : « Bonjour, voici la veille SciFeed du {date}. » puis annonce le nombre d'articles.
- Pour chaque article, 3 à 5 phrases simples : le sujet, la population, le résultat principal, le niveau de preuve
  (dit en mots : étude préliminaire, essai randomisé solide…) et l'intérêt pour la pratique clinique.
- Transitions naturelles entre les articles (« Deuxième étude… », « On change de sujet… »). Termine par une phrase de conclusion brève.
- Écris pour l'oreille : développe les sigles (SII → syndrome de l'intestin irritable, TCC → thérapie cognitivo-comportementale),
  aucun intervalle de confiance, aucune valeur de p, aucun chiffre illisible à l'oral ; au plus un chiffre simple par article
  (« deux fois plus », « 120 adultes »). Pas de liste à puces, pas de titre, pas de markdown, pas d'émoji.
- N'invente rien : utilise uniquement les fiches fournies. Nuance si l'étude est petite ou préliminaire.
Réponds par un SEUL objet JSON : {{"script": "le texte complet à lire"}}"""


def _fiche_pour_script(i: int, a: dict) -> str:
    f = a.get("fiche") or {}
    champs = [("Titre", f.get("titre_court") or a.get("titre")), ("Titre original", a.get("titre")),
              ("Revue", a.get("revue")), ("Type d'étude", f.get("type_etude")), ("Population", f.get("population")),
              ("Intervention", f.get("intervention")), ("Verdict", f.get("verdict")),
              ("Résultats", " ; ".join(f.get("resultats_cles") or [])), ("Conclusion", f.get("conclusion")),
              ("Limites", " ; ".join(f.get("limites") or [])),
              ("Niveau de preuve (1 à 5)", f.get("niveau_preuve")), ("Pour le lecteur", f.get("pertinence_raison")),
              ("En pratique", f.get("conclusion_simple"))]
    if not f and a.get("resume"):
        champs.append(("Abstract (anglais)", a["resume"][:1500]))
    if a.get("preprint"):
        champs.append(("Attention", "preprint non relu par des pairs"))
    return f"### Article {i}\n" + "\n".join(f"{k} : {v}" for k, v in champs if v)


ORDINAUX = ["Premier article", "Deuxième article", "Troisième article", "Quatrième article", "Cinquième article",
            "Sixième article", "Septième article", "Huitième article", "Neuvième article", "Dixième article"]


def script_secours(articles: list[dict], jour: dt.date) -> str:
    """Sans IA : titre court, verdict et conclusion simple de chaque fiche, avec des transitions."""
    n = len(articles)
    morceaux_txt = [f"Bonjour, voici la veille SciFeed du {date_parlee(jour)}. "
                    f"{'Un article' if n == 1 else f'{n} articles'} aujourd'hui."]
    for i, a in enumerate(articles):
        f = a.get("fiche") or {}
        ordinal = ORDINAUX[i] if i < len(ORDINAUX) else f"Article {i + 1}"
        titre = f.get("titre_court") or a.get("titre") or ""
        phrases = [f"{ordinal} : {_phrase(titre)}"]
        for t in (f.get("verdict"), f.get("conclusion_simple")):
            if t and str(t).rstrip().endswith("…"):         # phrase coupée (texte trop long) : pas lue
                continue
            if t and _phrase(t) not in phrases:
                phrases.append(_phrase(t))
        if a.get("preprint"):
            phrases.append("Attention, c'est un preprint, pas encore relu par des pairs.")
        morceaux_txt.append(" ".join(phrases))
    morceaux_txt.append("C'est tout pour aujourd'hui. Les fiches complètes sont dans l'appli SciFeed. Bonne journée.")
    return "\n\n".join(morceaux_txt)


def script_ia(cfg: dict, articles: list[dict], jour: dt.date, client=None) -> str | None:
    """Texte parlé écrit par l'IA des fiches (mêmes fournisseurs, quotas et repli) ; None si elle échoue."""
    from .resume_ia import ChaineLLM, _extraire_json
    ia = cfg.get("ia") or {}
    if not ia.get("actif", True) and client is None:
        return None
    try:
        client = client or ChaineLLM(ia)
        if client is not None and not getattr(client, "cle", "x") and "localhost" not in getattr(client, "url", ""):
            return None
        systeme = CONSIGNES_SCRIPT.format(profil=(ia.get("profil_lecteur") or "psychologue clinicien.").strip(),
                                          date=date_parlee(jour))
        texte = "\n\n".join(_fiche_pour_script(i, a) for i, a in enumerate(articles, 1))
        contenu, modele = client.completer(systeme, texte)
        script = str(_extraire_json(contenu).get("script") or "").strip()
    except Exception as ex:
        log.warning("Audio du jour : script de l'IA en échec (%s), script de secours", ex)
        return None
    script = re.sub(r"[*#_`]+", "", script)                     # pas de markdown lu à voix haute
    if len(script.split()) < 40 * len(articles):
        log.warning("Audio du jour : script de l'IA trop court (%d mots), script de secours", len(script.split()))
        return None
    log.info("Audio du jour : script écrit par %s (%d mots)", modele, len(script.split()))
    return script


def generer_jour(cfg: dict, base=None, client=None, jour: dt.date | None = None) -> dict | None:
    """MP3 du jour (audio/jour-AAAA-MM-JJ.mp3). Jamais d'exception : au pire, pas d'audio aujourd'hui."""
    r = reglages(cfg)
    if not r.get("actif", True) or not r.get("jour", True):
        return None
    debut = time.monotonic()
    try:
        if base is None:
            from .pipeline import charger
            base = charger()
        jour = jour or jour_local(cfg)
        articles = enregistrer_selection(cfg, base, jour)
        if not articles:
            return None
        cle = f"jour:{jour.isoformat()}"
        nom = f"jour-{jour.isoformat()}.mp3"
        e = hashlib.sha1(json.dumps([[a["id"], a.get("fiche")] for a in articles], ensure_ascii=False,
                                    sort_keys=True).encode("utf-8")).hexdigest()[:16]
        DOSSIER.mkdir(exist_ok=True)
        manifeste = charger_manifeste()
        v = manifeste.get(cle)
        if v and v.get("empreinte") == e and (DOSSIER / nom).exists():
            log.info("Audio du jour : déjà fait, mêmes articles")
            return v
        script = script_ia(cfg, articles, jour, client) or script_secours(articles, jour)
        donnees = synthetiser(script, r["voix"])
        if len(donnees) < 1000:
            raise RuntimeError("réponse vide du service de voix")
        (DOSSIER / nom).write_bytes(donnees)
        titres = [(a.get("fiche") or {}).get("titre_court") or a.get("titre", "") for a in articles]
        v = {"fichier": nom, "jour": jour.isoformat(), "empreinte": e, "octets": len(donnees),
             "duree": round(len(donnees) / OCTETS_PAR_SECONDE), "ids": [a["id"] for a in articles],
             "titres": titres, "mots": len(script.split())}
        manifeste[cle] = v
        purger(manifeste, r)
        (DOSSIER / MANIFESTE).write_text(json.dumps(manifeste, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("Audio du jour : %s, %d mots, %d s d'écoute, %d Ko (%.0f s de préparation)", nom, v["mots"],
                 v["duree"], len(donnees) // 1024, time.monotonic() - debut)
        return v
    except Exception as ex:
        log.warning("Audio du jour en échec (%s)", ex)
        return None


def episodes(dossier=None) -> list[dict]:
    """Audios du jour présents, du plus récent au plus ancien (pour le site et le flux podcast)."""
    dossier = dossier or DOSSIER
    eps = [dict(v, cle=k) for k, v in charger_manifeste(dossier).items()
           if k.startswith("jour:") and (dossier / v.get("fichier", "?")).exists()]
    return sorted(eps, key=lambda v: v["jour"], reverse=True)


def podcast(eps: list[dict], titre: str, adresse: str) -> str:
    """Flux podcast (RSS 2.0 + balises iTunes) des audios du jour, pour AntennaPod & co."""
    import email.utils
    from html import escape as e
    base = adresse.rstrip("/") + "/" if adresse else ""
    items = []
    for v in eps:
        jour = dt.date.fromisoformat(v["jour"])
        date = email.utils.format_datetime(dt.datetime.combine(jour, dt.time(5, 0), dt.timezone.utc))
        d = int(v.get("duree") or 0)
        resume = " · ".join(v.get("titres") or [])
        items.append(
            "<item>"
            f"<title>{e(titre)} — veille du {e(date_parlee(jour, avec_jour=False))}</title>"
            f"<guid isPermaLink=\"false\">{e(v['cle'])}-{e(v['empreinte'])}</guid>"
            f"<pubDate>{date}</pubDate>"
            f"<description>{e(resume)}</description>"
            f"<enclosure url=\"{e(base + 'audio/' + v['fichier'])}\" length=\"{int(v.get('octets') or 0)}\" type=\"audio/mpeg\"/>"
            f"<itunes:duration>{d // 3600:02d}:{d % 3600 // 60:02d}:{d % 60:02d}</itunes:duration>"
            "</item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>'
            f"<title>{e(titre)} — audio du jour</title><link>{e(base or './')}</link><language>fr</language>"
            f"<description>Les articles du jour de {e(titre)}, en quelques minutes.</description>"
            f"<itunes:image href=\"{e(base + 'icone-512.png')}\"/>"
            f"<itunes:author>{e(titre)}</itunes:author><itunes:explicit>false</itunes:explicit>"
            f"{''.join(items)}</channel></rss>")
