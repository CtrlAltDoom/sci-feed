"""Fiches de lecture IA via n'importe quelle API compatible OpenAI (OpenRouter, Gemini, Groq, Ollama…)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time

import requests

from . import revues, sante
from .core import aujourd_hui, bonus_serieux, interet, log
from .pipeline import charger, sauvegarder

TYPES = ["méta-analyse", "revue systématique", "essai randomisé", "essai non randomisé",
         "cohorte", "cas-témoins", "transversale", "qualitative", "méthodes mixtes",
         "validation psychométrique", "revue narrative", "étude de cas", "protocole",
         "expérimentale", "autre"]
QUALITES = ["élevée", "correcte", "faible", "non évaluable"]

CONSIGNES = """Tu es un assistant de veille scientifique rigoureux. Tu lis des abstracts et tu rédiges, en {langue}, une fiche ultra-synthétique pour un lecteur qui doit trier vite.

Lecteur : {profil}

Règles strictes :
- Utilise UNIQUEMENT ce que dit l'abstract. N'invente aucun chiffre ni aucune information. Si une information est absente : null (ou liste vide).
- Phrases très courtes, style télégraphique, vocabulaire clinique précis. Garde les chiffres clés (n, effet, IC, p) quand ils sont donnés.
- "niveau_preuve" (1 à 5) dépend du design ET de ce qu'on voit de la méthode : 5 = méta-analyse/revue systématique d'essais ou grand essai randomisé solide ; 4 = essai randomisé ; 3 = essai non randomisé, grande cohorte ; 2 = transversale, cas-témoins, petite étude ; 1 = étude de cas, avis, revue narrative, données préliminaires.
- "qualite_methodo" : jugement prudent d'après l'abstract (effectif, groupe contrôle, aveugle, pré-enregistrement, outils validés…). Si impossible à juger : "non évaluable".
- "pertinence" (1 à 5) : intérêt pour CE lecteur et sa pratique clinique.
- type_etude parmi : {types}.

Réponds par un SEUL objet JSON valide, sans texte autour, de la forme :
{{"fiches": [{{"id": "...", "verdict": "1 phrase (max 25 mots) : ce que l'étude montre/apporte",
"type_etude": "...", "design": ["0 à 3 précisions de méthode en 1 à 3 mots, si l'abstract les donne : double aveugle, contre placebo, multicentrique, pilote, en cross-over, longitudinale…"],
"population": "effectif + qui, ou null", "intervention": "intervention/exposition et comparateur, ou null",
"resultats_cles": ["2 à 3 puces courtes"], "conclusion": "conclusion des auteurs en 1 phrase",
"limites": ["0 à 2 limites visibles"], "niveau_preuve": 1, "qualite_methodo": "...",
"pertinence": 1, "pertinence_raison": "max 15 mots", "mots_cles_fr": ["2 à 4 mots-clés"],
"titre_court": "titre en français, 50 caractères max, sujet et population, sans jargon",
"conclusion_simple": "UNE phrase de 140 caractères max : ce qu'on peut en conclure en pratique au vu des résultats et des limites, sans chiffre, nuancée si l'étude est préliminaire"}}]}}
Une fiche par article, avec le même "id"."""


def _extraire_json(texte: str):
    texte = re.sub(r"^```(?:json)?|```$", "", texte.strip(), flags=re.M).strip()
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut < 0 or fin < 0:
        raise ValueError("pas de JSON dans la réponse")
    return json.loads(texte[debut:fin + 1])


def _entier(v, lo=1, hi=5):
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def _liste(v, n=3):
    if isinstance(v, str):
        v = [v]
    return [str(x).strip() for x in (v or []) if str(x).strip()][:n]


def valider(f: dict, modele: str) -> dict:
    typ = str(f.get("type_etude") or "autre").lower().strip()
    qual = str(f.get("qualite_methodo") or "non évaluable").lower().strip()
    return {
        "verdict": str(f.get("verdict") or "").strip(),
        "type_etude": typ if typ in TYPES else "autre",
        "design": [d[:30] for d in _liste(f.get("design"), 3)],
        "population": (str(f["population"]).strip() if f.get("population") else None),
        "intervention": (str(f["intervention"]).strip() if f.get("intervention") else None),
        "resultats_cles": _liste(f.get("resultats_cles"), 3),
        "conclusion": (str(f["conclusion"]).strip() if f.get("conclusion") else None),
        "limites": _liste(f.get("limites"), 2),
        "niveau_preuve": _entier(f.get("niveau_preuve")),
        "qualite_methodo": qual if qual in QUALITES else "non évaluable",
        "pertinence": _entier(f.get("pertinence")),
        "pertinence_raison": str(f.get("pertinence_raison") or "").strip(),
        "mots_cles_fr": _liste(f.get("mots_cles_fr"), 4),
        "titre_court": str(f.get("titre_court") or "").strip()[:70] or None,
        "conclusion_simple": str(f.get("conclusion_simple") or "").strip()[:200] or None,
        "modele": modele, "date": aujourd_hui().isoformat(),
    }


class ClientLLM:
    def __init__(self, ia: dict):
        self.url = ia.get("base_url", "https://openrouter.ai/api/v1").rstrip("/") + "/chat/completions"
        self.cle = os.environ.get(ia.get("cle_env", "LLM_API_KEY"), "")
        self.modeles = list(ia.get("modeles") or [])
        self.temperature = ia.get("temperature", 0.1)
        # les modèles gratuits sont souvent des modèles "qui réfléchissent" : réflexion courte = plus rapide
        self.effort = ia.get("effort_raisonnement", "low")
        self.reasoning_effort = ia.get("reasoning_effort")
        self.morts: set[str] = set()  # modèles épuisés pour cette exécution
        # si tous les modèles configurés échouent (renommés, retirés…), on essaie quelques modèles
        # gratuits du moment, lus dans la liste publique d'OpenRouter
        self.secours_auto = ia.get("secours_auto", True) and "openrouter.ai" in self.url
        self.nb_secours = ia.get("secours_max", 3)
        self._secours_charges = False

    def _ajouter_secours(self) -> bool:
        if not self.secours_auto or self._secours_charges:
            return False
        self._secours_charges = True
        try:
            r = requests.get(self.url.rsplit("/chat/", 1)[0] + "/models", timeout=30)
            r.raise_for_status()
            gratuits = [m for m in r.json().get("data", [])
                        if str(m.get("id", "")).endswith(":free")
                        and (m.get("context_length") or 0) >= 32000
                        and "text" in str((m.get("architecture") or {}).get("output_modalities", ["text"]))]
        except Exception as ex:
            log.warning("IA : liste des modèles gratuits indisponible (%s)", ex)
            return False
        gratuits.sort(key=lambda m: m.get("context_length") or 0, reverse=True)
        nouveaux = [m["id"] for m in gratuits if m["id"] not in self.modeles][:self.nb_secours]
        if nouveaux:
            log.warning("IA : modèles configurés indisponibles, essai de secours : %s", ", ".join(nouveaux))
            self.modeles += nouveaux
        return bool(nouveaux)

    def completer(self, systeme: str, utilisateur: str) -> tuple[str, str]:
        try:
            return self._completer(systeme, utilisateur)
        except RuntimeError:
            if self._ajouter_secours():
                return self._completer(systeme, utilisateur)
            raise

    def _completer(self, systeme: str, utilisateur: str) -> tuple[str, str]:
        en_tetes = {"Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/", "X-Title": "Veille scientifique"}
        if self.cle:
            en_tetes["Authorization"] = f"Bearer {self.cle}"
        erreur = None
        for m in [x for x in self.modeles if x not in self.morts]:
            for essai in range(2):
                try:
                    corps = {"model": m, "temperature": self.temperature,
                             "messages": [{"role": "system", "content": systeme},
                                          {"role": "user", "content": utilisateur}]}
                    if self.effort and "openrouter.ai" in self.url:
                        corps["reasoning"] = {"effort": self.effort}
                    elif self.reasoning_effort:          # Gemini (API compatible OpenAI) : "low", "none"…
                        corps["reasoning_effort"] = self.reasoning_effort
                    r = requests.post(self.url, headers=en_tetes, timeout=300, json=corps)
                    if r.status_code == 429:
                        if essai == 0:
                            time.sleep(20)
                            continue
                        self.morts.add(m)
                        raise RuntimeError(f"{m} : quota atteint (429)")
                    r.raise_for_status()
                    data = r.json()
                    contenu = data["choices"][0]["message"]["content"] or ""
                    return contenu, data.get("model", m)
                except Exception as ex:
                    erreur = ex
                    code = getattr(getattr(ex, "response", None), "status_code", None)
                    if code in (400, 402, 404):      # modèle inconnu, retiré ou devenu payant
                        self.morts.add(m)
                        break
                    if essai == 0 and not isinstance(ex, RuntimeError):
                        time.sleep(5)
                        continue
                    break
        raise RuntimeError(f"aucun modèle disponible ({erreur})")


def _local(url: str) -> bool:
    return "localhost" in url or "127.0.0.1" in url


class ChaineLLM:
    """Plusieurs fournisseurs essayés dans l'ordre (ia.fournisseurs). Quand l'un est épuisé (quota,
    clé refusée, panne) ou a utilisé sa part (max_requetes, duree_max_minutes), le suivant prend le
    relais. Un fournisseur sans clé est simplement ignoré : la chaîne ne casse jamais la veille."""

    def __init__(self, ia: dict):
        commun = {k: v for k, v in ia.items() if k != "fournisseurs"}
        self.clients: list[ClientLLM] = []
        for f in ia.get("fournisseurs") or [{}]:
            c = ClientLLM({**commun, **(f or {})})
            c.nom = (f or {}).get("nom") or c.url.split("/")[2]
            c.max_requetes = (f or {}).get("max_requetes")
            c.duree_max = ((f or {}).get("duree_max_minutes") or 0) * 60
            c.nb_requetes, c.duree, c.epuise = 0, 0.0, False
            if c.cle or _local(c.url):
                self.clients.append(c)
            else:
                log.info("IA : %s ignoré (secret %s absent)", c.nom, (f or {}).get("cle_env", "LLM_API_KEY"))
        self.cle = next((c.cle for c in self.clients if c.cle), "")
        self.url = self.clients[0].url if self.clients else ""

    def _disponible(self, c: ClientLLM) -> bool:
        return not (c.epuise or (c.max_requetes and c.nb_requetes >= c.max_requetes)
                    or (c.duree_max and c.duree >= c.duree_max))

    def completer(self, systeme: str, utilisateur: str) -> tuple[str, str]:
        erreur = None
        for c in self.clients:
            if not self._disponible(c):
                continue
            c.nb_requetes += 1
            debut = time.time()
            try:
                return c.completer(systeme, utilisateur)
            except Exception as ex:   # RuntimeError attendu, mais rien ne doit casser la chaîne
                c.epuise = True
                erreur = f"{c.nom} : {ex}"
                log.warning("IA : %s indisponible (%s), fournisseur suivant", c.nom, ex)
            finally:
                c.duree += time.time() - debut
        raise RuntimeError(f"aucun modèle disponible ({erreur or 'tous les fournisseurs ont servi leur part'})")


def tester(cfg: dict) -> dict:
    """Petit appel à chaque fournisseur, séparément : dit lesquels répondent (aucune clé affichée)."""
    ia = cfg.get("ia", {})
    resultats = {}
    for f in ia.get("fournisseurs") or [{}]:
        chaine = ChaineLLM({**ia, "fournisseurs": [{**f, "max_requetes": 1}], "secours_auto": False})
        nom = f.get("nom") or "défaut"
        if not chaine.clients:
            resultats[nom] = f"ignoré (secret {f.get('cle_env', 'LLM_API_KEY')} absent)"
            continue
        debut = time.time()
        try:
            contenu, modele = chaine.completer("Réponds uniquement par le mot OK.", "Test de connexion.")
            resultats[nom] = f"OK : {modele} répond en {time.time() - debut:.0f} s ({contenu.strip()[:20]!r})"
        except Exception as ex:
            resultats[nom] = f"ÉCHEC : {ex}"
    for nom, r in resultats.items():
        log.info("Test IA, %s : %s", nom, r)
    return resultats


def priorite(a: dict, cfg: dict, infos_revues: dict | None = None) -> tuple:
    """Ordre de passage des fiches IA (le quota gratuit ne suffit pas pour tout résumer) :
    1. les articles des derniers jours d'abord (la veille du jour reste à jour) ;
    2. puis le plus pertinent : thèmes prioritaires, étiquettes, études animales en dernier ;
    3. puis le plus récent."""
    ia = cfg.get("ia", {})
    jours = ia.get("priorite_jours_recents", 3)
    recent = a.get("ajoute_le", "") >= (aujourd_hui() - dt.timedelta(days=jours)).isoformat()
    info = revues.resume((infos_revues or {}).get(a.get("revue_oa") or ""))
    return (recent, interet(a, cfg) + bonus_serieux(a, info, cfg), a.get("ajoute_le", ""), a.get("date", ""))


def resumer(cfg: dict, client=None) -> int:
    ia = cfg.get("ia", {})
    if not ia.get("actif", True):
        return 0
    client = client or ChaineLLM(ia)
    if not client.cle and not _local(client.url):
        log.warning("Aucune clé IA : fiches IA ignorées (les abstracts restent affichés).")
        sante.noter(fiches=0, attente=1, ia_erreur="pas de clé : secrets LLM_API_KEY / GEMINI_API_KEY / MISTRAL_API_KEY absents ou vides")
        return 0
    base = charger()
    attente = [a for a in base.articles if not a.get("fiche") and len(a.get("resume", "")) >= 200
               and not a.get("libre")]
    infos_revues = revues.charger()
    attente.sort(key=lambda a: priorite(a, cfg, infos_revues), reverse=True)
    taille = max(1, ia.get("articles_par_requete", 5))
    lots = [attente[i:i + taille] for i in range(0, len(attente), taille)]
    lots = lots[:ia.get("max_requetes_par_execution", 40)]
    systeme = CONSIGNES.format(langue="français", profil=ia.get("profil_lecteur", "").strip(),
                               types=", ".join(TYPES))
    faits = 0
    erreur = ""
    debut = time.time()
    duree_max = ia.get("duree_max_minutes", 25) * 60
    log.info("IA : %d articles en attente, %d lots prévus", len(attente), len(lots))
    for n, lot in enumerate(lots):
        if time.time() - debut > duree_max:
            log.info("IA : durée maximale atteinte, la suite au prochain lancement")
            break
        par_id = {f"a{i}": a for i, a in enumerate(lot)}
        texte = "\n\n".join(
            f"### id: {k}\nTitre : {a['titre']}\nRevue : {a.get('revue','')}\n"
            f"Types déclarés : {', '.join(a.get('types', [])) or 'non précisé'}\n"
            f"Abstract : {a['resume'][:4000]}" for k, a in par_id.items())
        try:
            try:
                contenu, modele = client.completer(systeme, texte)
                fiches = _extraire_json(contenu).get("fiches", [])
            except ValueError:
                # réponse vide ou mal formée (fréquent avec les modèles gratuits) : un second essai,
                # le routeur "openrouter/free" choisit souvent un autre modèle
                contenu, modele = client.completer(systeme, texte)
                fiches = _extraire_json(contenu).get("fiches", [])
        except Exception as ex:
            log.warning("  lot %d : %s", n + 1, ex)
            erreur = str(ex)
            if "aucun modèle" in str(ex):
                break
            continue
        for f in fiches:
            a = par_id.get(str(f.get("id", "")).strip())
            if a is not None:
                fiche = valider(f, modele)
                if fiche["verdict"]:
                    a["fiche"] = fiche
                    faits += 1
        sauvegarder(base)  # sauvegarde au fil de l'eau : rien n'est perdu si ça coupe
        time.sleep(ia.get("pause_secondes", 4))
    log.info("IA : %d fiches rédigées", faits)
    sante.noter(fiches=faits, attente=len(attente), ia_erreur=erreur if not faits else "")
    return faits
