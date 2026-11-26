"""Tests sans réseau : python -m unittest discover tests"""
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from veille import audio, core, libre, notifications, pipeline, resume_ia, sante, site
from veille.sources import clinicaltrials, europepmc, openalex, pubmed, rss

AUJ = core.aujourd_hui().isoformat()

PUBMED_XML = f"""<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>40000001</PMID>
<Article><Journal><JournalIssue><PubDate><Year>2026</Year><Month>Nov</Month></PubDate></JournalIssue>
<Title>Neurogastroenterology and motility</Title></Journal>
<ArticleTitle>Gut-directed hypnotherapy versus education in irritable bowel syndrome: a randomized trial.</ArticleTitle>
<Abstract><AbstractText Label="BACKGROUND">Irritable bowel syndrome (IBS) is common and burdensome for patients worldwide.</AbstractText>
<AbstractText Label="METHODS">We randomized 120 adults with IBS (Rome IV) to six sessions of group gut-directed hypnotherapy or education.</AbstractText>
<AbstractText Label="RESULTS">Responders at 12 weeks were 52% vs 27% (p=0.004). Visceral anxiety decreased more with hypnotherapy.</AbstractText></Abstract>
<AuthorList><Author><LastName>Martin</LastName><Initials>A</Initials></Author></AuthorList>
<PublicationTypeList><PublicationType>Journal Article</PublicationType><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>
<ArticleDate><Year>2026</Year><Month>11</Month><Day>10</Day></ArticleDate></Article></MedlineCitation>
<PubmedData><ArticleIdList><ArticleId IdType="doi">10.1111/nmo.99999</ArticleId><ArticleId IdType="pmc">PMC123</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>""".encode()

OPENALEX = {"results": [{
    "id": "W1", "doi": "https://doi.org/10.1111/NMO.99999",
    "display_name": "Gut-directed hypnotherapy versus education in irritable bowel syndrome: a randomized trial",
    "publication_date": "2026-11-10", "abstract_inverted_index": {"Short": [0], "abstract": [1]},
    "authorships": [], "primary_location": {"source": {"id": "https://openalex.org/S1", "display_name": "Neurogastroenterology & Motility"}},
    "open_access": {"oa_url": "https://example.org/pdf"}, "type": "article",
    "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/40000001"}, "is_retracted": False},
    {"id": "W2", "doi": None, "display_name": "Alexithymia and interoception in adults with functional dyspepsia",
     "publication_date": "2026-11-12", "abstract_inverted_index": {"Alexithymia": [0], "was": [1], "higher": [2]},
     "authorships": [{"author": {"display_name": "B. Durand"}}], "primary_location": {"source": None},
     "open_access": {}, "type": "preprint", "ids": {}, "is_retracted": False}],
    "meta": {"next_cursor": None}}

SOURCES = {"results": [{"id": "https://openalex.org/S1", "display_name": "Neurogastroenterology & Motility",
                        "type": "journal", "is_in_doaj": False, "host_organization_name": "Wiley",
                        "summary_stats": {"2yr_mean_citedness": 3.4, "h_index": 130},
                        "topics": [{"subfield": {"display_name": "Gastroenterology"}}]}]}

EUROPEPMC = {"resultList": {"result": [{
    "id": "PPR1", "source": "PPR", "doi": "10.31234/osf.io/abcd",
    "title": "Self-compassion as a mediator of visceral anxiety in IBS: a cross-sectional study",
    "authorString": "Durand B, Petit C.", "bookOrReportDetails": {"publisher": "PsyArXiv"},
    "firstPublicationDate": "2026-11-14", "abstractText": "<h4>Background</h4>We surveyed 412 adults " * 10,
    "pubTypeList": {"pubType": ["Preprint"]}}]}}

CT = {"studies": [{"protocolSection": {
    "identificationModule": {"nctId": "NCT07000001", "briefTitle": "Online CBT for IBS"},
    "descriptionModule": {"briefSummary": "A randomized trial of internet CBT for irritable bowel syndrome."},
    "statusModule": {"overallStatus": "RECRUITING", "studyFirstPostDateStruct": {"date": "2026-11-11"}},
    "designModule": {"studyType": "INTERVENTIONAL", "designInfo": {"allocation": "RANDOMIZED"},
                     "enrollmentInfo": {"count": 200}},
    "armsInterventionsModule": {"interventions": [{"name": "Internet CBT"}]},
    "conditionsModule": {"conditions": ["Irritable Bowel Syndrome"]}}}]}

RSS = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>Revue test</title>
<item><title>Hypnosis for IBS: what next?</title><link>https://onlinelibrary.wiley.com/doi/10.1111/nmo.88888?af=R</link>
<description>An editorial about irritable bowel syndrome.</description><pubDate>{dt.date.today():%a, %d %b %Y} 08:00:00 GMT</pubDate></item>
<item><title>Liver transplantation outcomes</title><link>https://x.org/1</link><description>Hepatology.</description>
<pubDate>{dt.date.today():%a, %d %b %Y} 08:00:00 GMT</pubDate></item>
<item><title>Murine model of IBS</title><link>https://x.org/2</link><description>irritable bowel syndrome in mice</description>
<pubDate>{dt.date.today():%a, %d %b %Y} 08:00:00 GMT</pubDate></item></channel></rss>""".encode()


class Reponse:
    def __init__(self, data):
        self._data = data
        self.content = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.status_code = 200

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


class FauxGitHub:
    """API des gists simulée : gist de l'appli « abc » et gist de secours des favoris."""
    def __init__(self):
        self.synchro, self.gists, self.contenu, self.panne, self.creations, self.public = None, {}, None, False, 0, None

    def copie(self):
        g = next(iter(self.gists.values()))
        return json.loads(g["scifeed-favoris-secours.json"]["content"])["favoris"]

    def get(self, url, headers=None, params=None, **kw):
        if self.panne:
            raise core.requests.ConnectionError("hors ligne")
        if url.endswith("/gists/abc"):
            return Reponse({"files": {"veille-synchro.json": {"content": json.dumps(self.synchro)}}})
        if url.endswith("/gists"):
            page = (params or {}).get("page", 1)
            return Reponse([{"id": i, "files": f} for i, f in self.gists.items()] if page == 1 else [])
        g = self.gists[url.rsplit("/", 1)[-1]]
        if self.contenu is not None:
            return Reponse({"files": {"scifeed-favoris-secours.json": {"content": self.contenu}}})
        return Reponse({"files": g})

    def patch(self, url, headers=None, json=None, **kw):
        self.gists[url.rsplit("/", 1)[-1]].update(json["files"])
        return Reponse({"id": url.rsplit("/", 1)[-1]})

    def post(self, url, headers=None, json=None, **kw):
        self.creations += 1
        self.public = json.get("public")
        self.gists[f"g{self.creations}"] = dict(json["files"])
        return Reponse({"id": f"g{self.creations}"})


def faux_get(self, url, params=None, **kw):
    if "unpaywall" in url:
        if url.endswith("inconnu"):
            r = Reponse({})
            r.status_code = 404
            raise core.requests.HTTPError("HTTP 404", response=r)
        return Reponse({"best_oa_location": {"url_for_pdf": "https://hal.science/x.pdf"}})
    if "esearch" in url:
        return Reponse({"esearchresult": {"idlist": ["40000001"]}})
    if "efetch" in url:
        return Reponse(PUBMED_XML)
    if "openalex.org/sources" in url:
        return Reponse(SOURCES)
    if "openalex" in url:
        return Reponse(OPENALEX)
    if "europepmc" in url:
        if params and params.get("query", "").startswith("DOI:"):
            return Reponse({"resultList": {"result": []}})
        return Reponse(EUROPEPMC)
    if "clinicaltrials" in url:
        return Reponse(CT)
    return Reponse(RSS)


class FauxLLM:
    cle = "test"
    url = "http://test"

    def completer(self, systeme, utilisateur):
        ids = [l.split(":", 1)[1].strip() for l in utilisateur.splitlines() if l.startswith("### id:")]
        fiches = [{"id": i, "verdict": "L'hypnose digestive en groupe double le taux de répondeurs.",
                   "type_etude": "essai randomisé", "population": "120 adultes SII (Rome IV)",
                   "resultats_cles": ["52 % vs 27 % de répondeurs (p = 0,004)"], "niveau_preuve": "4",
                   "qualite_methodo": "correcte", "pertinence": 5, "limites": ["monocentrique"]} for i in ids]
        return "```json\n" + json.dumps({"fiches": fiches}) + "\n```", "faux-modele"


class TestVeille(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(pipeline, "DATA", self.tmp),
                        mock.patch.object(pipeline, "FICHIER", self.tmp / "articles.json"),
                        mock.patch.object(pipeline, "ETAT", self.tmp / "etat.json"),
                        mock.patch.object(site, "ETAT", self.tmp / "etat.json"),
                        mock.patch.object(site, "SORTIE", self.tmp / "site"),
                        mock.patch.object(audio, "DOSSIER", self.tmp / "audio"),
                        mock.patch.object(notifications, "audio_du_jour_en_ligne", lambda *a: ""),
                        mock.patch.object(core.Http, "get", faux_get),
                        mock.patch("time.sleep", lambda s: None)]
        for p in self.patches:
            p.start()
        self.cfg = core.charger_config()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def test_requetes(self):
        q = pubmed.requete([["irritable bowel syndrome", "IBS"], ["anxiety"]])
        self.assertEqual(q, '("irritable bowel syndrome"[tiab] OR IBS[tiab]) AND (anxiety[tiab])')
        self.assertIn('TITLE_ABS:"IBS"', europepmc.requete([["IBS"]], dt.date(2026, 1, 1), dt.date(2026, 1, 2)))
        self.assertNotIn(",", openalex.requete([["a, b", "c"]]))

    def test_mots_cles(self):
        th = [t for t in self.cfg["themes"] if t["id"] == "psy_digestif"]
        self.assertEqual(core.themes_correspondants(
            {"titre": "Anxiety in inflammatory bowel disease", "resume": ""}, th), ["psy_digestif"])
        self.assertEqual(core.themes_correspondants({"titre": "Anxiety in teachers", "resume": ""}, th), [])
        self.assertFalse(core.contient("this", "IBS".lower()))
        self.assertTrue(core.contient("gut brain axis", "gut-brain axis"))
        # troncature
        self.assertTrue(core.contient("alexithymic patients", "alexithymi*"))
        self.assertFalse(core.contient("alexithymia", "alexithymic"))
        # étiquette limitée au titre
        etq = [e for e in self.cfg["etiquettes"] if e["id"] == "anx_dep"]
        self.assertEqual(core.themes_correspondants({"titre": "Depression in IBS", "resume": ""}, etq), ["anx_dep"])
        self.assertEqual(core.themes_correspondants({"titre": "Gut microbiota in IBS", "resume": "anxiety"}, etq), [])

    def test_chaine_complete(self):
        self.cfg["sources"]["rss"]["flux"] = self.cfg["sources"]["rss"]["flux"][:1]
        nouveaux = pipeline.collecter(self.cfg)
        base = pipeline.charger()
        # même article vu par PubMed + OpenAlex => fusionné en un seul
        hypnose = [a for a in base.articles if a.get("doi") == "10.1111/nmo.99999"]
        self.assertEqual(len(hypnose), 1)
        a = hypnose[0]
        self.assertEqual(set(a["sources"]), {"pubmed", "openalex"})
        self.assertIn("METHODS", a["resume"])
        self.assertEqual(a["pmcid"], "PMC123")
        self.assertIn("sii", a["themes"])
        self.assertIn("hypnose", a["themes"])
        self.assertFalse(a["preprint"])
        titres = " ".join(x["titre"] for x in base.articles)
        self.assertNotIn("Liver", titres)          # hors thème
        self.assertIn("Murine", titres)            # étude animale gardée (signalée par étiquette)
        self.assertIn("Hypnosis for IBS", titres)  # RSS retenu
        pp = [x for x in base.articles if x.get("doi") == "10.31234/osf.io/abcd"][0]
        self.assertTrue(pp["preprint"])
        essai = [x for x in base.articles if x.get("nct")][0]
        self.assertTrue(essai["fiche"]["verdict"].startswith("Nouvel essai"))
        # 2e passage : rien de nouveau
        self.assertEqual(pipeline.collecter(self.cfg), 0)
        self.assertGreater(nouveaux, 3)

        faites = resume_ia.resumer(self.cfg, client=FauxLLM())
        self.assertGreaterEqual(faites, 2)
        f = [x for x in pipeline.charger().articles if x.get("doi") == "10.1111/nmo.99999"][0]["fiche"]
        self.assertEqual(f["niveau_preuve"], 4)
        self.assertEqual(f["type_etude"], "essai randomisé")

        site.construire(self.cfg)
        sortie = self.tmp / "site"
        self.assertTrue((sortie / "data.json").exists())
        donnees = json.loads((sortie / "data.json").read_text(encoding="utf-8"))
        par_titre = {x["titre"]: x for x in donnees["articles"]}
        self.assertIn("animal", par_titre["Murine model of IBS"]["etiquettes"])
        self.assertNotIn("animal", next(x for t, x in par_titre.items() if t.startswith("Gut-directed"))["etiquettes"])
        self.assertTrue(any(e["id"] == "animal" and e["famille"] == "animal" for e in donnees["meta"]["etiquettes"]))
        # les étiquettes ne sont pas écrites dans la base
        self.assertNotIn("etiquettes", pipeline.charger().articles[0])
        # revue : rattachée via OpenAlex, notoriété calculée
        hyp = next(x for t, x in par_titre.items() if t.startswith("Gut-directed"))
        info = donnees["meta"]["revues"][hyp["rv"]]     # rangée une fois par revue, pas dans chaque article
        self.assertEqual(info["niveau"], 3)
        self.assertEqual(info["domaine"], "Gastro-entérologie")
        # data.json allégé : pas d'abstract complet ni de champ vide ; l'abstract est dans details/
        self.assertNotIn("resume", hyp)
        self.assertNotIn("revue_info", hyp)
        self.assertFalse(any(v in (None, False, "", [], {}) for x in donnees["articles"] for v in x.values()))
        paquet = json.loads((sortie / "details" / f"{hyp['d']}.json").read_text(encoding="utf-8"))
        self.assertIn("METHODS", paquet[hyp["id"]]["resume"])
        self.assertEqual(paquet[hyp["id"]]["auteurs"], ["Martin A"])
        # intérêt : SII + hypnose (2 + 2 + étiquettes) devant l'étude animale
        self.assertGreater(hyp["interet"], par_titre["Murine model of IBS"]["interet"])
        self.assertIn("jours_par_point", donnees["meta"])
        self.assertEqual(hyp["etude"]["type"], "essai randomisé")
        # précisions de méthode lues dans l'abstract
        et = site.type_etude({"titre": "A double-blind, placebo-controlled multicentre pilot trial",
                              "resume": "", "types": ["Randomized Controlled Trial"]})
        self.assertEqual(et["type"], "essai randomisé")
        self.assertEqual(et["details"], ["double aveugle", "contre placebo", "multicentrique", "pilote"])
        self.assertIn("<rss", (sortie / "feed-sii.xml").read_text(encoding="utf-8"))
        site.construire(self.cfg, inline=True)
        self.assertIn("window.VEILLE_DATA", (sortie / "index.html").read_text(encoding="utf-8"))

        # notifications ntfy : sélection, textes courts IA, envoi, mémoire des envois
        class FauxCourt:
            cle, url = "test", "http://test"
            def completer(self, systeme, utilisateur):
                ids = [l.split(":", 1)[1].strip() for l in utilisateur.splitlines() if l.startswith("### id:")]
                return json.dumps({"items": [{"id": i, "titre_court": "Hypnose digestive en groupe : efficace",
                                              "conclusion_simple": "Option crédible en soins courants, à confirmer."}
                                             for i in ids]}), "faux"
        envois = []
        self.cfg["notifications"]["hebdo"] = {"actif": False}     # testé à part (dépend du jour)
        with mock.patch.dict("os.environ", {"NTFY_TOPIC": "canal-test", "GITHUB_REPOSITORY": "moi/sci-feed"}), \
             mock.patch.object(notifications.requests, "post", lambda url, json=None, **kw: envois.append(json) or Reponse({})):
            n = notifications.notifier(self.cfg, forcer=True, client=FauxCourt())
            self.assertGreaterEqual(n, 2)
            self.assertTrue(all(m["topic"] == "canal-test" for m in envois))
            self.assertNotIn("Murine", " ".join(m["title"] for m in envois))         # études animales exclues
            dernier = envois[-1]                                                        # le plus pertinent, en haut
            self.assertEqual(dernier["actions"][0]["url"], "https://moi.github.io/sci-feed/")
            self.assertIn("Option crédible", " ".join(m["message"] for m in envois))
            # deuxième passage : rien de nouveau, rien n'est renvoyé
            self.assertEqual(notifications.notifier(self.cfg, forcer=True, client=FauxCourt()), 0)

    # ---- notifications fiables malgré les retards de GitHub
    def _a_l_heure(self, h, m=0, jour=None):
        from zoneinfo import ZoneInfo
        jour = jour or dt.datetime.now(ZoneInfo("Europe/Paris")).date()
        return dt.datetime.combine(jour, dt.time(h, m), tzinfo=ZoneInfo("Europe/Paris"))

    def _noter_collecte(self, quand: dt.datetime | None):
        etat = {"derniere_collecte": quand.astimezone(dt.timezone.utc).isoformat(timespec="minutes")} if quand else {}
        (self.tmp / "etat.json").write_text(json.dumps(etat), encoding="utf-8")

    def _notifier_a(self, maintenant):
        a = core.nouvel_article(titre="Hypnose digestive dans le SII", themes=["sii"], resume="Abstract " * 40,
                                url="https://exemple.org/1")
        a["id"], a["ajoute_le"] = "test:notif", AUJ
        a["fiche"] = {"titre_court": "Hypnose et SII", "conclusion_simple": "Piste à confirmer."}
        pipeline.sauvegarder(core.Base([a]))
        self.cfg["notifications"]["hebdo"] = {"actif": False}
        envois = []
        with mock.patch.dict("os.environ", {"NTFY_TOPIC": "canal-test", "SYNC_GIST_ID": ""}), \
             mock.patch.object(notifications.requests, "post", lambda url, json=None, **kw: envois.append(json) or Reponse({})):
            n = notifications.notifier(self.cfg, maintenant=maintenant)
        return n, envois

    def test_notifications_attendent_la_collecte(self):
        matin = self._a_l_heure(8)
        self._noter_collecte(None)                       # (a) 8 h, pas de collecte du jour : on attend
        self.assertEqual(self._notifier_a(matin), (0, []))
        self._noter_collecte(matin - dt.timedelta(days=1))
        self.assertEqual(self._notifier_a(matin), (0, []))
        self._noter_collecte(matin - dt.timedelta(hours=2))   # (b) collecte faite ce matin : envoi
        n, envois = self._notifier_a(matin)
        self.assertEqual(n, 1)
        self.assertEqual(len(envois), 1)

    def test_notifications_apres_midi_et_soir(self):
        self._noter_collecte(self._a_l_heure(8) - dt.timedelta(days=1))
        n, envois = self._notifier_a(self._a_l_heure(13))   # (c) 13 h : on envoie avec ce qu'on a
        self.assertEqual((n, len(envois)), (1, 1))
        (self.tmp / "notifications.json").unlink()
        self.assertEqual(self._notifier_a(self._a_l_heure(21, 30)), (0, []))   # (d) 21 h 30 : trop tard

    def test_planning_nuit_et_6h(self):
        """Collecte de la nuit (0 h 30 UTC) = jour même à Paris ; rien avant 6 h, envoi à 6 h 05."""
        nuit = dt.datetime(2026, 11, 22, 0, 30, tzinfo=dt.timezone.utc)     # 1 h 30 à Paris
        self._noter_collecte(nuit)
        self.assertTrue(pipeline.collecte_du_jour_faite(self.cfg, self._a_l_heure(5, 40, nuit.date())))
        self.assertEqual(self.cfg["notifications"]["heure_min"], "06:00")
        self.assertEqual(self._notifier_a(self._a_l_heure(5, 40)), (0, []))   # 5 h 40 : trop tôt
        self._noter_collecte(self._a_l_heure(1, 30))                          # collecte faite cette nuit
        n, envois = self._notifier_a(self._a_l_heure(6, 5))
        self.assertEqual((n, len(envois)), (1, 1))
        self.assertEqual(self._notifier_a(self._a_l_heure(6, 25)), (0, []))   # une seule fois par jour

    def test_collecte_du_jour_faite(self):
        from zoneinfo import ZoneInfo
        paris = ZoneInfo("Europe/Paris")
        self._noter_collecte(None)
        self.assertFalse(pipeline.collecte_du_jour_faite(self.cfg))
        (self.tmp / "etat.json").write_text(json.dumps({"derniere_collecte": "n'importe quoi"}), encoding="utf-8")
        self.assertFalse(pipeline.collecte_du_jour_faite(self.cfg))
        (self.tmp / "etat.json").write_text(json.dumps({"derniere_collecte": "2026-11-20T23:30+00:00"}), encoding="utf-8")
        # 23 h 30 UTC le 20 = 0 h 30 le 21 à Paris : c'est la collecte du 21
        self.assertTrue(pipeline.collecte_du_jour_faite(self.cfg, dt.datetime(2026, 11, 21, 8, 0, tzinfo=paris)))
        self.assertFalse(pipeline.collecte_du_jour_faite(self.cfg, dt.datetime(2026, 11, 20, 23, 0, tzinfo=paris)))
        (self.tmp / "etat.json").write_text(json.dumps({"derniere_collecte": "2026-11-20T22:30+00:00"}), encoding="utf-8")
        self.assertFalse(pipeline.collecte_du_jour_faite(self.cfg, dt.datetime(2026, 11, 21, 8, 0, tzinfo=paris)))
        self.assertTrue(pipeline.collecte_du_jour_faite(self.cfg, dt.datetime(2026, 11, 20, 23, 45, tzinfo=paris)))
        # heure d'été : 21 h 30 UTC le 15 juin = 23 h 30 à Paris, encore le 15
        (self.tmp / "etat.json").write_text(json.dumps({"derniere_collecte": "2026-06-15T21:30+00:00"}), encoding="utf-8")
        self.assertTrue(pipeline.collecte_du_jour_faite(self.cfg, dt.datetime(2026, 6, 15, 23, 50, tzinfo=paris)))

    def test_site_allege(self):
        """Articles récents dans data.json, anciens dans archive.json, abstracts par paquets."""
        vieux = (core.aujourd_hui() - dt.timedelta(days=45)).isoformat()
        articles = []
        for i in range(5):
            a = core.nouvel_article(titre=f"Article {i}", themes=["sii"], resume="Abstract " * 80,
                                    auteurs=["A B"], url=f"https://exemple.org/{i}")
            a["id"], a["ajoute_le"] = f"test:{i}", AUJ if i < 3 else vieux
            articles.append(a)
        articles[0]["fiche"] = {"verdict": "Fiche déjà rédigée"}
        cfg = dict(self.cfg, site={"jours_recents": 30, "details_par_fichier": 2})
        site.construire(cfg, articles=articles)
        sortie = self.tmp / "site"
        recents = json.loads((sortie / "data.json").read_text(encoding="utf-8"))
        archive = json.loads((sortie / "archive.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(a["id"] for a in recents["articles"]), ["test:0", "test:1", "test:2"])
        self.assertEqual(sorted(a["id"] for a in archive["articles"]), ["test:3", "test:4"])
        self.assertEqual(recents["meta"]["archive"], {"fichier": "archive.json", "articles": 2})
        par_id = {a["id"]: a for a in recents["articles"] + archive["articles"]}
        self.assertNotIn("extrait", par_id["test:0"])                    # fiche IA : pas besoin d'extrait
        self.assertTrue(par_id["test:1"]["extrait"].endswith("…"))       # sans fiche : extrait pour la liste
        self.assertLessEqual(len(par_id["test:1"]["extrait"]), site.LONGUEUR_EXTRAIT + 1)
        # paquets de 2 au plus, par jour d'ajout ; chaque article sait où est son abstract
        fichiers = sorted(p.stem for p in (sortie / "details").glob("*.json"))
        self.assertEqual(fichiers, sorted([f"{AUJ}-0", f"{AUJ}-1", f"{vieux}-0"]))
        for a in par_id.values():
            paquet = json.loads((sortie / "details" / f"{a['d']}.json").read_text(encoding="utf-8"))
            self.assertTrue(paquet[a["id"]]["resume"].startswith("Abstract"))
        # sans articles anciens : pas d'archive
        site.construire(cfg, articles=articles[:3])
        self.assertFalse((sortie / "archive.json").exists())
        self.assertNotIn("archive", json.loads((sortie / "data.json").read_text(encoding="utf-8"))["meta"])
        # aperçu autonome (une seule page) : tout reste dedans, abstracts compris
        site.construire(cfg, inline=True, articles=articles)
        page = (sortie / "index.html").read_text(encoding="utf-8")
        self.assertIn("Abstract Abstract", page)
        self.assertFalse((sortie / "data.json").exists())

    def test_deja_vus_dans_l_appli(self):
        synchro = {"lus": {"a1": 1}, "favoris": {"a2": 1}, "masques": {"a3": 1, "a4": 0}, "horo": {}}
        gist = {"files": {"veille-synchro.json": {"content": json.dumps(synchro)}}}
        appels = []
        def faux(url, headers=None, **kw):
            appels.append(url)
            return Reponse(gist)
        with mock.patch.dict("os.environ", {"SYNC_GIST_ID": "https://gist.github.com/moi/abc123"}), \
             mock.patch.object(notifications.requests, "get", faux):
            self.assertEqual(notifications.deja_vus_dans_l_appli(), {"a1", "a2", "a3"})
        self.assertEqual(appels, ["https://api.github.com/gists/abc123"])
        # sans secret, ou si GitHub ne répond pas : rien n'est exclu
        with mock.patch.dict("os.environ", {"SYNC_GIST_ID": ""}):
            self.assertEqual(notifications.deja_vus_dans_l_appli(), set())
        def panne(*a, **k):
            raise core.requests.ConnectionError("hors ligne")
        with mock.patch.dict("os.environ", {"SYNC_GIST_ID": "abc"}), mock.patch.object(notifications.requests, "get", panne):
            self.assertEqual(notifications.deja_vus_dans_l_appli(), set())

    def test_purge_garde_les_favoris(self):
        vieux, limite = "2026-01-01", "2026-06-01"
        base = core.Base([dict(core.nouvel_article(titre=f"Article {i}", url=f"https://exemple.org/{i}"),
                               id=f"a{i}", ajoute_le=vieux if i < 3 else AUJ) for i in range(4)])
        synchro = {"favoris": {"a1": 1, "a2": 0}, "lus": {"a0": 1}}
        gist = {"files": {"veille-synchro.json": {"content": json.dumps(synchro)}}}
        ids = lambda b: sorted(a["id"] for a in b.articles)
        # sans synchronisation : purge comme avant
        with mock.patch.dict("os.environ", {"SYNC_GIST_ID": ""}):
            self.assertEqual(ids(pipeline.purger(base, limite)), ["a3"])
        # avec : l'ancien favori est gardé (un favori retiré, ou un simple « lu », ne l'est pas)
        with mock.patch.dict("os.environ", {"SYNC_GIST_ID": "abc"}), \
             mock.patch.object(notifications.requests, "get", lambda *a, **k: Reponse(gist)):
            self.assertEqual(ids(pipeline.purger(base, limite)), ["a1", "a3"])
        # gist illisible ce jour-là : on n'efface rien
        def panne(*a, **k):
            raise core.requests.ConnectionError("hors ligne")
        with mock.patch.dict("os.environ", {"SYNC_GIST_ID": "abc"}), mock.patch.object(notifications.requests, "get", panne):
            self.assertEqual(ids(pipeline.purger(base, limite)), ["a0", "a1", "a2", "a3"])

    def test_copie_des_favoris(self):
        """Les favoris survivent même si le gist de l'appli est vidé, son secret supprimé, ou la
        base abîmée : copie de secours dans un gist secret à part (rien dans le dépôt)."""
        vieux, limite = "2026-01-01", "2026-06-01"
        def base_neuve():
            return core.Base([dict(core.nouvel_article(titre=f"Article {i}", url=f"https://exemple.org/{i}"),
                                   id=f"a{i}", ajoute_le=vieux if i < 3 else AUJ) for i in range(4)])
        ids = lambda b: sorted(a["id"] for a in b.articles)
        gh = FauxGitHub()
        def purge(synchro, base=None, limite=limite, jeton="j"):
            gh.synchro = synchro
            env = {"SYNC_GIST_ID": "abc" if synchro is not None else "", "GIST_TOKEN": jeton}
            with mock.patch.dict("os.environ", env), mock.patch.object(core.requests, "get", gh.get), \
                 mock.patch.object(core.requests, "patch", gh.patch), mock.patch.object(core.requests, "post", gh.post):
                return ids(pipeline.purger(base or base_neuve(), limite))
        # 1. a1 favori dans l'appli -> gist de secours créé (secret), avec l'article complet
        self.assertEqual(purge({"favoris": {"a1": 1}, "horo": {"favoris|a1": 5}}), ["a1", "a3"])
        self.assertEqual(list(gh.copie()), ["a1"])
        self.assertEqual(gh.copie()["a1"]["article"]["titre"], "Article 1")
        self.assertFalse(gh.public)
        self.assertFalse((self.tmp / "favoris.json").exists())          # rien dans le dépôt
        # 2. le secret SYNC_GIST_ID a disparu : la copie suffit à garder a1
        self.assertEqual(purge(None), ["a1", "a3"])
        # 3. l'appli a été vidée par accident (plus aucun favori, ou fichier absent) : rien effacé
        for synchro in ({"favoris": {}, "horo": {"favoris|a1": 9}}, {}):
            self.assertEqual(purge(synchro), ["a0", "a1", "a2", "a3"])
        self.assertEqual(list(gh.copie()), ["a1"])
        # 4. a1 a disparu de la base (fichier abîmé, mauvaise fusion…) : il est remis depuis la copie
        self.assertEqual(purge(None, core.Base([a for a in base_neuve().articles if a["id"] != "a1"])), ["a1", "a3"])
        # 5. copie de secours illisible (abîmée, ou GitHub en panne) : on n'efface rien du tout
        gh.contenu = "{abîmé"
        self.assertEqual(purge(None), ["a0", "a1", "a2", "a3"])
        gh.contenu, gh.panne = None, True
        self.assertEqual(purge(None), ["a0", "a1", "a2", "a3"])
        gh.panne = False
        # 6. retrait explicite et daté dans l'appli (a2 reste favori) : a1 sort de la copie
        self.assertEqual(purge({"favoris": {"a2": 1}, "horo": {"favoris|a1": 9, "favoris|a2": 9}}), ["a2", "a3"])
        self.assertEqual(list(gh.copie()), ["a2"])
        self.assertEqual(gh.creations, 1)                                # le même gist est réutilisé
        # 7. état de l'appli au contenu inattendu (liste) : la collecte ne plante pas, rien n'est effacé
        self.assertEqual(purge(["n'importe quoi"]), ["a0", "a1", "a2", "a3"])
        # 8. rien d'ancien à purger : la copie est quand même tenue à jour (nouveau favori a3)
        purge({"favoris": {"a2": 1, "a3": 1}}, core.Base([a for a in base_neuve().articles if a["id"] != "a0"]), "2000-01-01")
        self.assertEqual(sorted(gh.copie()), ["a2", "a3"])
        # 9. sans GIST_TOKEN : pas de copie, les favoris de l'appli protègent quand même
        self.assertEqual(purge({"favoris": {"a1": 1}}, jeton=""), ["a1", "a3"])

    def test_favori_retracte(self):
        from veille import retractions
        base = core.Base([dict(core.nouvel_article(titre=f"Article {i}", url=f"https://exemple.org/{i}"),
                               id=f"a{i}", doi=f"10.1/x{i}") for i in range(3)])
        synchro = {"favoris": {"a0": 1, "a1": 1}}
        gist = {"files": {"veille-synchro.json": {"content": json.dumps(synchro)}}}
        demandes = []
        class FauxHttp:
            def get(self, url, params=None, **kw):
                demandes.append(params["filter"])
                return Reponse({"results": [{"doi": "https://doi.org/10.1/X1", "is_retracted": True},
                                            {"doi": "https://doi.org/10.1/x0", "is_retracted": False}]})
        envois = []
        with mock.patch.dict("os.environ", {"SYNC_GIST_ID": "abc", "NTFY_TOPIC": "canal-test"}), \
             mock.patch.object(notifications.requests, "get", lambda *a, **k: Reponse(gist)), \
             mock.patch.object(sante.requests, "post", lambda url, json=None, **kw: envois.append(json) or Reponse({})):
            nouveaux = retractions.verifier(self.cfg, FauxHttp(), base)
            self.assertEqual([a["id"] for a in nouveaux], ["a1"])
            self.assertTrue(retractions.alerter(self.cfg, nouveaux))
            # le lendemain : déjà marqué, plus vérifié ni signalé
            self.assertEqual(retractions.verifier(self.cfg, FauxHttp(), base), [])
        self.assertEqual(demandes, ["doi:10.1/x0|10.1/x1", "doi:10.1/x0"])      # a2 n'est pas un favori
        self.assertIn("rétracté", envois[0]["title"])
        self.assertIn("Article 1", envois[0]["message"])
        # sans synchronisation : rien n'est demandé
        with mock.patch.dict("os.environ", {"SYNC_GIST_ID": ""}):
            self.assertEqual(retractions.verifier(self.cfg, FauxHttp(), base), [])
        self.assertEqual(len(demandes), 2)

    def test_resume_semaine(self):
        base = core.Base()
        for i in range(14):
            a = core.nouvel_article(titre=f"Hypnosis for IBS number {i}", themes=["sii", "hypnose"] if i % 2 else ["sii"],
                                    url=f"https://exemple.org/{i}")
            a["id"], a["ajoute_le"] = f"a{i}", (core.aujourd_hui() - dt.timedelta(days=i)).isoformat()
            a["fiche"] = {"titre_court": f"Titre court {i}", "verdict": "Verdict.", "pertinence": 5 if i == 9 else 3}
            base.ajouter(a)
        dimanche = dt.datetime(2026, 11, 22, 7, 0)
        envois, etat = [], {}
        with mock.patch.dict("os.environ", {"NTFY_TOPIC": "canal-test", "SYNC_GIST_ID": ""}), \
             mock.patch.object(sante.requests, "post", lambda url, json=None, **kw: envois.append(json) or Reponse({})):
            self.assertEqual(notifications.resume_semaine(self.cfg, base, etat, dimanche - dt.timedelta(days=1)), 0)  # samedi
            self.assertEqual(notifications.resume_semaine(self.cfg, base, etat, dimanche), 1)
            self.assertEqual(notifications.resume_semaine(self.cfg, base, etat, dimanche), 0)  # une seule fois
        self.assertEqual(len(envois), 1)
        m = envois[0]["message"]
        self.assertEqual(envois[0]["title"], "SciFeed : les 8 articles de la semaine")  # 7 derniers jours (0 à 7)
        self.assertTrue(m.startswith("1. Titre court"))
        self.assertNotIn("Titre court 9", m)                     # trop ancien, même très pertinent
        self.assertEqual(envois[0]["priority"], 3)

    def test_taille_du_depot(self):
        reponse = {"size": 700 * 1024}
        with mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "moi/sci-feed"}), \
             mock.patch.object(sante.requests, "get", lambda *a, **k: Reponse(reponse)):
            self.assertIn("depot", sante.depot_trop_gros(self.cfg))
            reponse["size"] = 30 * 1024
            self.assertEqual(sante.depot_trop_gros(self.cfg), {})
        def panne(*a, **k):
            raise core.requests.ConnectionError("hors ligne")
        with mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "moi/sci-feed"}), mock.patch.object(sante.requests, "get", panne):
            self.assertEqual(sante.depot_trop_gros(self.cfg), {})

    def test_texte_libre_unpaywall(self):
        cfg = dict(self.cfg, contact_email="test@example.org")
        a1 = core.nouvel_article(titre="Un article fermé assez long pour le test", doi="10.1/ferme")
        a2 = core.nouvel_article(titre="Un article déjà libre assez long pour le test", doi="10.1/libre",
                                 url_libre="https://pmc/1")
        a3 = core.nouvel_article(titre="Un article inconnu d'Unpaywall pour le test", doi="10.1/inconnu")
        base = core.Base([a1, a2, a3])
        self.assertEqual(libre.completer(cfg, core.Http(), base), 1)
        self.assertEqual(a1["url_libre"], "https://hal.science/x.pdf")
        self.assertEqual(a2["url_libre"], "https://pmc/1")          # inchangé, pas interrogé
        self.assertEqual(a3["libre_verifie"], AUJ)                   # 404 : noté comme vérifié
        self.assertEqual(libre.completer(cfg, core.Http(), base), 0) # pas revérifié le jour même
        self.assertEqual(libre.completer(self.cfg, core.Http(), base), 0)  # sans e-mail : ignoré

    def test_sante(self):
        def passage(**k):
            p = {"sources": {"pubmed": {"essais": 5, "echecs": 0, "recus": 30}}, "nouveaux": 12,
                 "fiches": 10, "attente": 50, "ia_erreur": ""}
            p.update(k)
            return p
        panne_pubmed = {"pubmed": {"essais": 5, "echecs": 5, "recus": 0}}
        self.assertEqual(sante.problemes([passage(), passage()], self.cfg), {})
        # une seule journée en échec : pas encore d'alerte
        self.assertEqual(sante.problemes([passage(), passage(sources=panne_pubmed)], self.cfg), {})
        p = sante.problemes([passage(sources=panne_pubmed), passage(sources=panne_pubmed)], self.cfg)
        self.assertIn("source:pubmed", p)
        p = sante.problemes([passage(fiches=0, ia_erreur="429")] * 2, self.cfg)
        self.assertIn("429", p["ia"])
        self.assertNotIn("ia", sante.problemes([passage(fiches=0, attente=0)] * 2, self.cfg))
        self.assertIn("collecte", sante.problemes([passage(nouveaux=0)] * 3, self.cfg))

        envois = []
        with mock.patch.dict("os.environ", {"NTFY_TOPIC": "canal-test"}), \
             mock.patch.object(sante.requests, "post", lambda url, json=None, **kw: envois.append(json) or Reponse({})):
            self.assertEqual(sante.alerter(self.cfg, {"ia": "Fiches IA : 0"}), "alerte")
            self.assertEqual(sante.alerter(self.cfg, {"ia": "Fiches IA : 0"}), "")      # déjà signalé
            self.assertEqual(sante.alerter(self.cfg, {}), "retabli")
            self.assertEqual(sante.alerter(self.cfg, {}), "")
        self.assertEqual([e["title"][0] for e in envois], ["⚠", "✅"])

        # relevé d'un vrai passage, puis retard de collecte
        sante.RELEVE = sante.Releve()
        try:
            sante.noter_source("pubmed", recus=3)
            sante.noter_source("pubmed", echec=True)
            sante.noter(nouveaux=3, fiches=1, attente=4)
            sante.RELEVE.enregistrer()
        finally:
            sante.RELEVE = None
        dernier = sante.charger()["passages"][-1]
        self.assertEqual(dernier["sources"]["pubmed"], {"essais": 2, "echecs": 1, "recus": 3})
        vieux = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=50)).isoformat(timespec="minutes")
        (self.tmp / "etat.json").write_text(json.dumps({"derniere_collecte": vieux}), encoding="utf-8")
        self.assertIn("retard", sante.collecte_en_retard(self.cfg))

    def test_modeles_de_secours(self):
        client = resume_ia.ClientLLM({"modeles": ["vieux/modele:free"], "base_url": "https://openrouter.ai/api/v1"})
        client.cle = "test"
        class R:
            def __init__(self, code, data=None):
                self.status_code, self._d = code, data or {}
            def json(self):
                return self._d
            def raise_for_status(self):
                if self.status_code >= 400:
                    raise core.requests.HTTPError(f"HTTP {self.status_code}", response=self)
        def post(url, json=None, **kw):
            if json["model"] == "vieux/modele:free":
                return R(404)
            return R(200, {"choices": [{"message": {"content": "ok"}}], "model": json["model"]})
        liste = {"data": [{"id": "nouveau/a:free", "context_length": 128000},
                          {"id": "payant/b", "context_length": 200000},
                          {"id": "petit/c:free", "context_length": 8000}]}
        with mock.patch.object(resume_ia.requests, "post", post), \
             mock.patch.object(resume_ia.requests, "get", lambda url, **kw: R(200, liste)):
            self.assertEqual(client.completer("s", "u"), ("ok", "nouveau/a:free"))
        self.assertIn("vieux/modele:free", client.morts)

    def test_chaine_de_fournisseurs(self):
        ia = {"secours_auto": False, "fournisseurs": [
            {"nom": "A", "base_url": "https://a.test/v1", "cle_env": "CLE_A", "modeles": ["a1"]},
            {"nom": "B", "base_url": "https://b.test/v1", "cle_env": "CLE_B", "modeles": ["b1"], "max_requetes": 2},
            {"nom": "C", "base_url": "https://c.test/v1", "cle_env": "CLE_C", "modeles": ["c1"]},
            {"nom": "Sans clé", "base_url": "https://d.test/v1", "cle_env": "CLE_ABSENTE", "modeles": ["d1"]}]}
        class R:
            def __init__(self, code, data=None):
                self.status_code, self._d = code, data or {}
            def json(self):
                return self._d
            def raise_for_status(self):
                if self.status_code >= 400:
                    raise core.requests.HTTPError(f"HTTP {self.status_code}", response=self)
        appels = []
        def post(url, json=None, headers=None, **kw):
            appels.append(json["model"])
            if json["model"] == "a1":
                return R(429)                         # quota atteint : B doit prendre le relais
            if json["model"] == "c1":
                raise core.requests.ConnectionError("panne")
            return R(200, {"choices": [{"message": {"content": "ok"}}], "model": json["model"]})
        env = {"CLE_A": "a", "CLE_B": "b", "CLE_C": "c"}
        with mock.patch.dict(os.environ, env), mock.patch.object(resume_ia.requests, "post", post), \
             mock.patch.object(resume_ia.time, "sleep", lambda s: None):
            chaine = resume_ia.ChaineLLM(ia)
            self.assertEqual([c.nom for c in chaine.clients], ["A", "B", "C"])   # sans clé : ignoré
            self.assertEqual(chaine.completer("s", "u"), ("ok", "b1"))
            self.assertEqual(chaine.completer("s", "u"), ("ok", "b1"))
            self.assertEqual(appels.count("a1"), 3)    # 3 essais sur le 429, puis A épuisé : plus réessayé
            with self.assertRaisesRegex(RuntimeError, "aucun modèle"):   # B a servi sa part, C en panne
                chaine.completer("s", "u")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resume_ia.ChaineLLM(ia).cle, "")   # aucune clé : fiches ignorées sans erreur
            self.assertEqual(resume_ia.ChaineLLM({"modeles": ["m"]}).clients, [])

    def test_fiche_valeurs_vides_de_l_ia(self):
        """« null », « N/A », « Non  précisé »… renvoyés par l'IA deviennent None (plus de « 👥 null »)."""
        for vide in ["null", " NULL ", "None", "N/A", "na", "Non  précisé", "non rapporté", "Non applicable",
                     "inconnu", "Unknown", "not reported", "-", "", None]:
            f = resume_ia.valider({"population": vide, "intervention": vide, "conclusion": vide,
                                   "titre_court": vide, "conclusion_simple": vide, "verdict": vide,
                                   "limites": [vide, "Petit effectif"]}, "m")
            for champ in ("population", "intervention", "conclusion", "titre_court", "conclusion_simple"):
                self.assertIsNone(f[champ], f"{champ} = {vide!r}")
            self.assertEqual(f["verdict"], "")
            self.assertEqual(f["limites"], ["Petit effectif"])
        f = resume_ia.valider({"population": " 120 adultes SII ", "intervention": "Non-inférieur"}, "m")
        self.assertEqual(f["population"], "120 adultes SII")
        self.assertEqual(f["intervention"], "Non-inférieur")


class ReponseIA:
    """Réponse simulée de l'API compatible OpenAI (Gemini, OpenRouter…)."""
    def __init__(self, code, data=None, texte="", en_tetes=None):
        self.status_code, self._d, self.text, self.headers = code, data or {}, texte, en_tetes or {}

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise core.requests.HTTPError(f"HTTP {self.status_code}", response=self)


def reponse_fiches(corps):
    """Réponse 200 avec une fiche valide pour chaque article du message."""
    ids = [l.split(":", 1)[1].strip() for l in corps["messages"][1]["content"].splitlines()
           if l.startswith("### id:")]
    fiches = [{"id": i, "verdict": "Effet modeste de l'hypnose digestive.", "type_etude": "cohorte",
               "titre_court": "Hypnose et SII", "conclusion_simple": "Piste prometteuse, à confirmer."}
              for i in ids]
    return ReponseIA(200, {"choices": [{"message": {"content": json.dumps({"fiches": fiches})}}],
                           "model": corps["model"]})


QUOTA_JOUR = ('[{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [{"violations": '
              '[{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}]')


class TestRattrapageIA(unittest.TestCase):
    """Rattrapage des fiches IA dans les quotas gratuits (Gemini) : client IA simulé, sans réseau."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pauses = []
        self.patches = [mock.patch.object(pipeline, "DATA", self.tmp),
                        mock.patch.object(pipeline, "FICHIER", self.tmp / "articles.json"),
                        mock.patch.object(pipeline, "ETAT", self.tmp / "etat.json"),
                        mock.patch.object(resume_ia.time, "sleep",
                                          lambda s: self.pauses.append(round(s)) if s else None),
                        mock.patch.dict(os.environ, {"CLE_G": "g"})]
        for p in self.patches:
            p.start()
        self.cfg = core.charger_config()
        self.cfg["ia"].update(pause_secondes=0, articles_par_requete=5, duree_max_minutes=240,
                              max_requetes_par_execution=600)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def base(self, n):
        arts = [{"id": f"x{i}", "titre": f"Gut-directed hypnotherapy in IBS, study {i}",
                 "resume": "Irritable bowel syndrome patients were followed. " * 6,
                 "ajoute_le": AUJ, "date": AUJ, "themes": ["sii"]} for i in range(n)]
        pipeline.sauvegarder(pipeline.Base(arts))

    def sans_fiche(self):
        return [a for a in pipeline.charger().articles if not a.get("fiche")]

    def chaine(self, modeles, rpm=None):
        f = {"nom": "Gemini", "base_url": "https://g.test/v1", "cle_env": "CLE_G", "modeles": modeles}
        if rpm:
            f["requetes_par_minute"] = rpm
        return resume_ia.ChaineLLM({**self.cfg["ia"], "secours_auto": False, "fournisseurs": [f]})

    def test_reste_rattrapage(self):
        """Rattrapage automatique du soir : reste=N tant qu'il y a du retard, 0 si auto: false."""
        self.base(7)
        arts = pipeline.charger().articles
        arts[0]["fiche"] = {"verdict": "ok"}          # déjà faite
        arts[1]["resume"] = "trop court"               # abstract trop court : pas éligible
        arts[2]["libre"] = True                        # accès libre : pas éligible
        pipeline.sauvegarder(pipeline.Base(arts))
        self.cfg["ia"]["rattrapage"] = {"auto": True}
        self.assertEqual(resume_ia.reste_rattrapage(self.cfg), 4)
        self.assertEqual(len(resume_ia.en_attente(pipeline.charger())), 4)   # même critère que resumer
        self.cfg["ia"]["rattrapage"]["auto"] = False
        self.assertEqual(resume_ia.reste_rattrapage(self.cfg), 0)
        self.cfg["ia"]["rattrapage"] = {"auto": True}
        self.cfg["ia"]["actif"] = False
        self.assertEqual(resume_ia.reste_rattrapage(self.cfg), 0)
        # la ligne lue par le workflow
        self.cfg["ia"]["actif"] = True
        with mock.patch.object(sys, "argv", ["veille", "reste_rattrapage"]), \
                mock.patch("veille.__main__.charger_config", lambda *a: self.cfg), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as sortie:
            from veille import __main__ as cli
            cli.main()
        self.assertEqual(sortie.getvalue().strip(), "reste=4")
        self.assertTrue(core.charger_config()["ia"]["rattrapage"]["auto"])   # config.yaml : auto: true

    def test_rattrapage_remplit_les_fiches(self):
        self.base(12)
        with mock.patch.object(resume_ia.requests, "post", lambda url, json=None, **kw: reponse_fiches(json)):
            self.assertEqual(resume_ia.resumer(self.cfg, client=self.chaine(["g1"])), 12)
        self.assertEqual(self.sans_fiche(), [])
        f = pipeline.charger().articles[0]["fiche"]
        self.assertEqual((f["modele"], f["titre_court"]), ("g1", "Hypnose et SII"))
        # nombre de requêtes limité (--lots) : le reste attend le prochain lancement
        self.base(12)
        self.cfg["ia"]["max_requetes_par_execution"] = 2
        with mock.patch.object(resume_ia.requests, "post", lambda url, json=None, **kw: reponse_fiches(json)):
            self.assertEqual(resume_ia.resumer(self.cfg, client=self.chaine(["g1"])), 10)
        self.assertEqual(len(self.sans_fiche()), 2)

    def test_arret_au_quota_du_jour(self):
        self.base(20)
        appels = {"g1": 0, "g2": 0}
        def post(url, json=None, **kw):
            appels[json["model"]] += 1
            if appels[json["model"]] > 1:                  # chaque modèle : 1 requête par jour
                return ReponseIA(429, texte=QUOTA_JOUR)
            return reponse_fiches(json)
        with mock.patch.object(resume_ia.requests, "post", post):
            faites = resume_ia.resumer(self.cfg, client=self.chaine(["g1", "g2"]))
        self.assertEqual(faites, 10)                       # pas d'exception : arrêt propre
        self.assertEqual(len(self.sans_fiche()), 10)       # fiches faites bien enregistrées
        self.assertEqual(appels, {"g1": 2, "g2": 2})       # quota du jour : pas de nouvel essai
        self.assertEqual(self.pauses, [])                  # ni d'attente inutile

    def test_rythme_par_minute(self):
        self.base(10)
        with mock.patch.object(resume_ia.requests, "post", lambda url, json=None, **kw: reponse_fiches(json)):
            self.assertEqual(resume_ia.resumer(self.cfg, client=self.chaine(["g1"], rpm=5)), 10)
        self.assertEqual(len(self.pauses), 1)              # 2 requêtes : 1 attente entre les deux
        self.assertAlmostEqual(self.pauses[0], 12, delta=1)

    def test_429_reessaye_puis_reussi(self):
        self.base(5)
        reponses = [ReponseIA(429, texte="Resource exhausted"),
                    ReponseIA(429, texte='{"retryDelay": "40s"}')]
        def post(url, json=None, **kw):
            return reponses.pop(0) if reponses else reponse_fiches(json)
        with mock.patch.object(resume_ia.requests, "post", post):
            self.assertEqual(resume_ia.resumer(self.cfg, client=self.chaine(["g1"])), 5)
        self.assertEqual(self.pauses, [15, 41])            # attente croissante, ou celle demandée
        self.assertEqual(resume_ia._attente_429(ReponseIA(429, en_tetes={"Retry-After": "500"}), "", 0), 90)

    def test_429_persistant_article_laisse_pour_plus_tard(self):
        self.base(5)
        appels = []
        def post(url, json=None, **kw):
            appels.append(json["model"])
            return ReponseIA(429, texte="Resource exhausted")
        with mock.patch.object(resume_ia.requests, "post", post):
            self.assertEqual(resume_ia.resumer(self.cfg, client=self.chaine(["g1"])), 0)
        self.assertEqual(len(appels), 3)                   # 3 essais puis abandon, sans planter
        self.assertEqual(self.pauses, [15, 30])
        self.assertEqual(len(self.sans_fiche()), 5)        # repris au prochain lancement

    def test_panne_5xx_ou_delai_reessayes_puis_reussis(self):
        self.base(5)
        incidents = [ReponseIA(503), core.requests.Timeout("délai dépassé"), ReponseIA(502)]
        def post(url, json=None, **kw):
            if incidents:
                x = incidents.pop(0)
                if isinstance(x, Exception):
                    raise x
                return x
            return reponse_fiches(json)
        with mock.patch.object(resume_ia.requests, "post", post):
            # 503 puis délai dépassé sur g1 (3 essais : 15 s, 30 s), puis 502 sur g1 → modèle suivant
            self.assertEqual(resume_ia.resumer(self.cfg, client=self.chaine(["g1", "g2"])), 5)
        self.assertEqual(self.pauses, [15, 30])
        self.assertEqual(self.sans_fiche(), [])

    def test_panne_persistante_n_est_pas_un_quota(self):
        self.base(10)
        appels = []
        def post(url, json=None, **kw):
            appels.append(json["model"])
            return ReponseIA(503, texte="Service Unavailable")
        chaine = self.chaine(["g1", "g2"])
        with mock.patch.object(resume_ia.requests, "post", post), \
             self.assertLogs(core.log, level="INFO") as journal:
            self.assertEqual(resume_ia.resumer(self.cfg, client=chaine), 0)
        self.assertEqual(appels, ["g1"] * 3 + ["g2"] * 3)  # 3 essais par modèle, attente croissante
        self.assertEqual(self.pauses, [15, 30, 15, 30])
        self.assertEqual(chaine.clients[0].morts, set())   # une panne n'écarte pas le modèle pour de bon
        texte = "\n".join(journal.output)
        self.assertIn("service IA indisponible", texte)
        self.assertNotIn("quotas du jour", texte)
        self.assertEqual(len(self.sans_fiche()), 10)       # repris au prochain lancement

    def test_message_quota_du_jour(self):
        self.base(5)
        with mock.patch.object(resume_ia.requests, "post", lambda url, **kw: ReponseIA(429, texte=QUOTA_JOUR)), \
             self.assertLogs(core.log, level="INFO") as journal:
            self.assertEqual(resume_ia.resumer(self.cfg, client=self.chaine(["g1", "g2"])), 0)
        texte = "\n".join(journal.output)
        self.assertIn("quotas du jour atteints", texte)
        self.assertNotIn("service IA indisponible", texte)

    def test_json_strict_avec_repli(self):
        self.base(10)
        corps_recus = []
        def post(url, json=None, **kw):
            corps_recus.append(dict(json))
            if json["model"] == "g1" and "response_format" in json:
                return ReponseIA(400, texte="response_format non pris en charge")
            return reponse_fiches(json)
        chaine = self.chaine(["g1"])
        with mock.patch.object(resume_ia.requests, "post", post):
            self.assertEqual(resume_ia.resumer(self.cfg, client=chaine), 10)
        self.assertEqual(corps_recus[0]["response_format"], {"type": "json_object"})   # demandé d'abord
        self.assertNotIn("response_format", corps_recus[1])                            # repli silencieux
        self.assertEqual(len(corps_recus), 3)              # 2e lot : plus redemandé, modèle gardé
        self.assertEqual(chaine.clients[0].morts, set())
        # désactivable dans config.yaml
        c = resume_ia.ClientLLM({"modeles": ["m"], "json_strict": False})
        self.assertNotIn("response_format", c._corps("m", "s", "u"))

    def test_rattrapage_laisse_les_petits_quotas(self):
        import copy
        cfg = resume_ia.reglages_rattrapage(copy.deepcopy(core.charger_config()))
        google = next(f for f in cfg["ia"]["fournisseurs"] if f["nom"] == "Google AI Studio")
        self.assertEqual(google["modeles"], ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"])
        self.assertIn("gemini-4-hydrogen", next(f for f in core.charger_config()["ia"]["fournisseurs"]
                                                if f["nom"] == "Google AI Studio")["modeles"])
        # fournisseur dont tous les modèles sont réservés : sauté
        cfg = {"ia": {"rattrapage": {"modeles_reserves": ["x"]},
                      "fournisseurs": [{"nom": "A", "modeles": ["x"]}, {"nom": "B", "modeles": ["y"]}]}}
        self.assertEqual([f["nom"] for f in resume_ia.reglages_rattrapage(cfg)["ia"]["fournisseurs"]], ["B"])

    def test_duree_limitee_du_rattrapage(self):
        cfg = resume_ia.reglages_rattrapage(self.cfg)
        self.assertEqual((cfg["ia"]["duree_max_minutes"], cfg["ia"]["max_requetes_par_execution"]), (40, 600))
        self.base(25)
        horloge = [1000.0]
        def post(url, json=None, **kw):
            horloge[0] += 15 * 60                          # chaque lot prend 15 min
            return reponse_fiches(json)
        with mock.patch.object(resume_ia.requests, "post", post), \
             mock.patch.object(resume_ia.time, "time", lambda: horloge[0]):
            faites = resume_ia.resumer(cfg, client=self.chaine(["g1"]))
        self.assertEqual(faites, 15)                       # lots à 0, 15 et 30 min ; à 45 min : on s'arrête
        self.assertEqual(len(self.sans_fiche()), 10)       # ce qui est fait est enregistré


if __name__ == "__main__":
    unittest.main()
