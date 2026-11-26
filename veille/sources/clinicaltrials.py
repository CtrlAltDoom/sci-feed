"""ClinicalTrials.gov (API v2) : nouveaux essais enregistrés. Fiche construite sans IA."""
from __future__ import annotations

from ..core import nouvel_article, log, aujourd_hui

API = "https://clinicaltrials.gov/api/v2/studies"
STATUTS = {"RECRUITING": "recrutement en cours", "NOT_YET_RECRUITING": "pas encore en recrutement",
           "ACTIVE_NOT_RECRUITING": "en cours (recrutement terminé)", "COMPLETED": "terminé",
           "ENROLLING_BY_INVITATION": "sur invitation", "TERMINATED": "arrêté",
           "WITHDRAWN": "retiré", "SUSPENDED": "suspendu"}
ALLOCATION = {"RANDOMIZED": "randomisé", "NON_RANDOMIZED": "non randomisé", "NA": ""}


def requete(groupes):
    return " AND ".join("(" + " OR ".join(f'"{t.rstrip("*")}"' for t in g) + ")" for g in groupes)


def collecter(cfg, http, theme, depuis, jusqu_a):
    params = {"query.term": requete(theme["_groupes"]),
              "filter.advanced": f"AREA[StudyFirstPostDate]RANGE[{depuis.isoformat()},MAX]",
              "pageSize": 100, "format": "json"}
    etudes = []
    maxi = cfg["collecte"].get("max_par_requete", 150)
    while len(etudes) < maxi:
        data = http.get(API, params=params).json()
        etudes += data.get("studies", [])
        if not data.get("nextPageToken"):
            break
        params["pageToken"] = data["nextPageToken"]
    articles = analyser(etudes[:maxi])
    log.info("  ClinicalTrials [%s] : %d", theme["id"], len(articles))
    return articles


def analyser(etudes: list[dict]) -> list[dict]:
    sortie = []
    for e in etudes:
        p = e.get("protocolSection", {})
        ident = p.get("identificationModule", {})
        statut = p.get("statusModule", {})
        design = p.get("designModule", {})
        nct = ident.get("nctId", "")
        n = (design.get("enrollmentInfo") or {}).get("count")
        alloc = ALLOCATION.get((design.get("designInfo") or {}).get("allocation", ""), "")
        typ = {"INTERVENTIONAL": "essai interventionnel", "OBSERVATIONAL": "étude observationnelle"}.get(
            design.get("studyType", ""), "étude")
        interventions = [i.get("name", "") for i in
                         (p.get("armsInterventionsModule") or {}).get("interventions", [])]
        conditions = (p.get("conditionsModule") or {}).get("conditions", [])
        promoteur = ((p.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name", "")
        st = STATUTS.get(statut.get("overallStatus", ""), statut.get("overallStatus", "").lower())
        fiche = {
            "verdict": f"Nouvel essai enregistré ({st}) — pas encore de résultats.",
            "type_etude": " ".join(x for x in (typ, alloc) if x),
            "population": (f"{n} participants prévus" if n else None),
            "intervention": ", ".join(interventions[:4]) or None,
            "resultats_cles": [f"Conditions : {', '.join(conditions[:4])}" if conditions else "",
                               f"Promoteur : {promoteur}" if promoteur else ""],
            "conclusion": None, "limites": [], "niveau_preuve": None,
            "qualite_methodo": "non évaluable", "pertinence": None, "pertinence_raison": "",
            "mots_cles_fr": [], "modele": "registre", "date": aujourd_hui().isoformat(),
        }
        fiche["resultats_cles"] = [x for x in fiche["resultats_cles"] if x]
        sortie.append(nouvel_article(
            titre=ident.get("officialTitle") or ident.get("briefTitle", ""),
            resume=(p.get("descriptionModule") or {}).get("briefSummary", ""),
            revue="ClinicalTrials.gov", nct=nct,
            date=(statut.get("studyFirstPostDateStruct") or {}).get("date", ""),
            url=f"https://clinicaltrials.gov/study/{nct}",
            types=["Essai enregistré"], essai_registre=True, sources=["clinicaltrials"],
            auteurs=[promoteur] if promoteur else [], fiche=fiche,
            mots_cles=conditions + (p.get("conditionsModule") or {}).get("keywords", []),
        ))
    return sortie
