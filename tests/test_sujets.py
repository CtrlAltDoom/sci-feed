"""Sujets de recherche ajoutés dans l'appli : pris en compte par la collecte (sans réseau)."""
import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_hors_ligne as th     # faux réseau partagé (PubMed, OpenAlex, Europe PMC…)
from veille import audio, core, notifications, pipeline, site, sujets
from veille.sources import clinicaltrials, europepmc, openalex, pubmed


def etat(**s):
    return {"sujets": {k: json.dumps(v) if isinstance(v, dict) else v for k, v in s.items()}}


class TestSujets(unittest.TestCase):
    def test_lecture_et_garde_fous(self):
        e = etat(m_visceral={"nom": "Anxiété viscérale", "mots": ["visceral anxiety", "GI-specific anxiety", "ab", "*"]},
                 m_vide={"nom": "Vide", "mots": []}, m_casse="pas du json", sii={"nom": "pirate", "mots": ["x y z"]},
                 m_supprime="")
        t = sujets.depuis_etat(e)
        self.assertEqual([x["id"] for x in t], ["m_visceral"])
        self.assertEqual(t[0]["_groupes"], [["visceral anxiety", "GI-specific anxiety"]])   # mots trop courts écartés
        self.assertTrue(t[0]["perso"])
        self.assertEqual(sujets.depuis_etat(None), [])
        self.assertEqual(sujets.depuis_etat({"sujets": "n'importe quoi"}), [])
        beaucoup = etat(**{f"m_s{i:02d}": {"nom": f"S{i}", "mots": ["anxiety"]} for i in range(20)})
        self.assertEqual(len(sujets.depuis_etat(beaucoup)), sujets.MAX_SUJETS)
        # un sujet de l'appli n'écrase jamais un thème de config.yaml
        cfg = {"themes": [{"id": "m_visceral", "nom": "déjà là"}]}
        self.assertEqual(len(sujets.ajouter_aux_themes(cfg, e)), 1)

    def test_troncature_dans_les_requetes(self):
        self.assertIn("fibromyalg*[tiab]", pubmed.requete([["fibromyalg*"]]))
        q = europepmc.requete([["fibromyalg*", "central sensitiz*"]], dt.date(2026, 1, 1), dt.date(2026, 1, 2))
        self.assertIn("TITLE_ABS:fibromyalg*", q)
        self.assertIn('TITLE_ABS:"central sensitiz"', q)
        self.assertNotIn("*", openalex.requete([["fibromyalg*"]]))
        self.assertNotIn("*", clinicaltrials.requete([["fibromyalg*"]]))
        th_ = sujets.depuis_etat(etat(m_f={"nom": "Fibro", "mots": ["fibromyalg*"], "titre": True}))
        self.assertEqual(core.themes_correspondants({"titre": "Fibromyalgia and sleep", "resume": ""}, th_), ["m_f"])
        self.assertEqual(core.themes_correspondants({"titre": "Sleep", "resume": "fibromyalgia"}, th_), [])


class TestCollecteAvecSujets(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(pipeline, "DATA", self.tmp),
                        mock.patch.object(pipeline, "FICHIER", self.tmp / "articles.json"),
                        mock.patch.object(pipeline, "ETAT", self.tmp / "etat.json"),
                        mock.patch.object(site, "ETAT", self.tmp / "etat.json"),
                        mock.patch.object(audio, "DOSSIER", self.tmp / "audio"),
                        mock.patch.object(core.Http, "get", th.faux_get),
                        mock.patch("time.sleep", lambda s: None)]
        for p in self.patches:
            p.start()
        self.cfg = core.charger_config()
        self.cfg["sources"]["rss"]["actif"] = False

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def collecter(self, gist, etat_appli):
        requetes = []
        vrai = core.Http.get
        def espion(http, url, params=None, **kw):
            if "esearch" in url:
                requetes.append(params["term"])
            return vrai(http, url, params, **kw)
        with mock.patch.dict("os.environ", {"SYNC_GIST_ID": gist}), \
             mock.patch.object(notifications, "etat_appli", lambda: etat_appli), \
             mock.patch.object(core.Http, "get", espion):
            pipeline.collecter(self.cfg)
        return requetes, pipeline.charger()

    def test_sujet_de_l_appli_cherche_et_etiquete(self):
        e = etat(m_visceral={"nom": "Anxiété viscérale", "mots": ["visceral anxiety"]})
        requetes, base = self.collecter("abc", e)
        self.assertIn('("visceral anxiety"[tiab])', requetes)                 # PubMed interrogé pour le sujet
        hypnose = [a for a in base.articles if a.get("doi") == "10.1111/nmo.99999"][0]
        self.assertIn("m_visceral", hypnose["themes"])                       # « Visceral anxiety decreased… »

    def test_sans_gist_rien_de_plus(self):
        e = etat(m_visceral={"nom": "Anxiété viscérale", "mots": ["visceral anxiety"]})
        requetes, base = self.collecter("", e)
        self.assertNotIn('("visceral anxiety"[tiab])', requetes)
        self.assertFalse(any("m_visceral" in a["themes"] for a in base.articles))

    def test_gist_illisible_collecte_normale(self):
        requetes, base = self.collecter("abc", None)
        self.assertEqual(len(requetes), len(self.cfg["themes"]))
        self.assertTrue(base.articles)


if __name__ == "__main__":
    unittest.main()
