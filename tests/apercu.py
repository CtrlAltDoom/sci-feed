"""Génère site/index.html autonome avec des EXEMPLES FICTIFS, pour voir l'interface sans réseau."""
import datetime as dt
from veille import core, site

j = core.aujourd_hui()
J = lambda n: (j - dt.timedelta(days=n)).isoformat()
def art(i, titre, themes, ajout, fiche=None, **kw):
    a = core.nouvel_article(titre=titre, themes=themes, revue="Revue fictive (exemple)", date=ajout,
                            resume="Abstract fictif servant uniquement à illustrer l'interface. " * 6,
                            auteurs=["Exemple A", "Exemple B"], url="https://pubmed.ncbi.nlm.nih.gov/", **kw)
    a["id"], a["ajoute_le"], a["fiche"] = f"demo:{i}", ajout, fiche
    return a
F = lambda **k: dict({"intervention": None, "conclusion": None, "limites": [], "pertinence_raison": "",
                      "mots_cles_fr": [], "modele": "exemple", "date": J(0)}, **k)
articles = [
 art(1, "[Exemple fictif] Group gut-directed hypnotherapy versus education in IBS: a randomized trial", ["sii", "hypnose"], J(0),
     F(verdict="L'hypnose digestive en groupe double le taux de répondeurs à 12 semaines.", type_etude="essai randomisé",
       population="120 adultes SII (Rome IV)", resultats_cles=["Répondeurs : 52 % vs 27 % (p = 0,004)", "Baisse plus nette de l'anxiété viscérale", "Effet maintenu à 6 mois"],
       niveau_preuve=4, qualite_methodo="correcte", pertinence=5, intervention="6 séances de groupe vs éducation thérapeutique",
       conclusion="Option efficace et peu coûteuse en soins courants.", limites=["monocentrique", "pas d'aveugle des patients"],
       pertinence_raison="Directement transposable aux groupes d'hypnose SII")),
 art(2, "[Exemple fictif] Alexithymia and interoceptive accuracy in functional dyspepsia: a cross-sectional study", ["alexithymie", "sii"], J(0),
     F(verdict="L'alexithymie est associée à une moins bonne précision intéroceptive et à plus de symptômes.", type_etude="transversale",
       population="230 adultes dyspepsie fonctionnelle vs 90 témoins", resultats_cles=["TAS-20 plus élevé (d = 0,6)", "Lien partiel via l'anxiété"],
       niveau_preuve=2, qualite_methodo="correcte", pertinence=4)),
 art(3, "[Exemple fictif] Self-compassion and visceral anxiety in IBS", ["sii", "psy_digestif"], J(1),
     F(verdict="L'autocompassion modère le lien entre anxiété viscérale et sévérité du SII.", type_etude="transversale",
       population="412 adultes SII (en ligne)", resultats_cles=["Effet de modération significatif (β = −0,18)"],
       niveau_preuve=2, qualite_methodo="faible", pertinence=4), preprint=True),
 art(4, "[Exemple fictif] Psychological therapies for depression in adults: an umbrella review", ["psychotherapies"], J(1),
     F(verdict="Les TCC restent le traitement psychologique le mieux étayé, avec des effets modérés.", type_etude="méta-analyse",
       population="62 méta-analyses, > 90 000 participants", resultats_cles=["g = 0,55 vs listes d'attente", "Effet plus faible vs soins habituels"],
       niveau_preuve=5, qualite_methodo="élevée", pertinence=3)),
 art(5, "[Exemple fictif] Internet-delivered CBT for irritable bowel syndrome (essai enregistré)", ["sii"], J(2),
     F(verdict="Nouvel essai enregistré (recrutement en cours) — pas encore de résultats.", type_etude="essai interventionnel randomisé",
       population="200 participants prévus", resultats_cles=["Promoteur : exemple"], niveau_preuve=None, qualite_methodo="non évaluable", pertinence=None),
     essai_registre=True, nct="NCT00000000"),
 art(6, "[Exemple fictif] Exposure-based therapy for ARFID: a pilot study", ["arfid_toc"], J(2)),
]
cfg = core.charger_config()
cfg["titre"] = "Aperçu — exemples fictifs"
site.construire(cfg, inline=True, articles=articles)
