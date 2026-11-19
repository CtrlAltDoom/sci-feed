"""Tests sans réseau : python -m unittest discover tests"""
import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from veille import core, pipeline, resume_ia, site
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
    "authorships": [], "primary_location": {"source": {"display_name": "Neurogastroenterology & Motility"}},
    "open_access": {"oa_url": "https://example.org/pdf"}, "type": "article",
    "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/40000001"}, "is_retracted": False},
    {"id": "W2", "doi": None, "display_name": "Alexithymia and interoception in adults with functional dyspepsia",
     "publication_date": "2026-11-12", "abstract_inverted_index": {"Alexithymia": [0], "was": [1], "higher": [2]},
     "authorships": [{"author": {"display_name": "B. Durand"}}], "primary_location": {"source": None},
     "open_access": {}, "type": "preprint", "ids": {}, "is_retracted": False}],
    "meta": {"next_cursor": None}}

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


def faux_get(self, url, params=None, **kw):
    if "esearch" in url:
        return Reponse({"esearchresult": {"idlist": ["40000001"]}})
    if "efetch" in url:
        return Reponse(PUBMED_XML)
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
        self.assertNotIn("Murine", titres)         # exclu
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
        self.assertIn("<rss", (sortie / "feed-sii.xml").read_text(encoding="utf-8"))
        site.construire(self.cfg, inline=True)
        self.assertIn("window.VEILLE_DATA", (sortie / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
