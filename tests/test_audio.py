"""MP3 des fiches (veille/audio.py) : sans réseau (voix simulée), plus un essai réel facultatif."""
import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from veille import audio, core, notifications, pipeline, site

J = lambda n: (core.aujourd_hui() - dt.timedelta(days=n)).isoformat()
FICHE = {"titre_court": "Hypnose digestive en groupe", "verdict": "Double le taux de répondeurs",
         "population": "120 adultes SII", "intervention": "6 séances", "resultats_cles": ["52 % vs 27 %"],
         "conclusion": "Efficace à 12 semaines", "limites": ["un seul centre", "pas d'aveugle"],
         "pertinence_raison": "Ton approche de groupe", "pertinence": 5}


def art(i, ajout=0, fiche=FICHE, **kw):
    a = core.nouvel_article(titre=f"Article number {i}: a randomized trial", themes=["sii"], revue="Revue",
                            resume="Background. " * 30, url=f"https://exemple.org/{i}")
    a.update(id=f"demo:{i}", ajoute_le=J(ajout), fiche=dict(fiche) if fiche else None, **kw)
    return a


class FausseVoix:
    def __init__(self, panne=False):
        self.appels, self.panne = [], panne

    def __call__(self, texte, voix):
        self.appels.append((voix, texte))
        if self.panne:
            raise OSError("hors ligne")
        return b"\xff\xfb" + texte.encode("utf-8") * 20 + b"\0" * 1200


class TestAudio(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = core.charger_config()
        self.cfg["audio"] = {"actif": True, "jours_conserves": 7, "max_par_jour": 25, "pertinence_min": 4}
        self.patches = [mock.patch.object(audio, "DOSSIER", self.tmp / "audio"),
                        mock.patch.object(pipeline, "DATA", self.tmp),
                        mock.patch.object(site, "SORTIE", self.tmp / "site"),
                        mock.patch.object(site, "ETAT", self.tmp / "etat.json"),
                        mock.patch.dict("os.environ", {"SYNC_GIST_ID": ""})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def test_texte_comme_l_appli(self):
        m = audio.morceaux(art(1))
        self.assertEqual(len(m), 1)                          # tout en français : un seul appel à la voix
        lang, t = m[0]
        self.assertEqual(lang, "fr")
        for attendu in ["Hypnose digestive en groupe.", "Double le taux de répondeurs.", "Population : 120 adultes SII.",
                        "Intervention : 6 séances.", "52 % vs 27 %.", "Conclusion des auteurs : Efficace à 12 semaines.",
                        "Limites : un seul centre. pas d'aveugle.", "Pour toi : Ton approche de groupe."]:
            self.assertIn(attendu, t)
        self.assertLess(t.index("Hypnose"), t.index("Population"))
        sans_titre = audio.morceaux(art(2, fiche=dict(FICHE, titre_court="")))
        self.assertEqual(sans_titre[0], ("en", "Article number 2: a randomized trial."))   # titre original en anglais
        self.assertEqual(sans_titre[1][0], "fr")

    def test_selection(self):
        base = core.Base([
            art(1, pertinence=None),                                          # pertinence 5 : retenu
            art(2, fiche=dict(FICHE, pertinence=2)),                          # peu pertinent, rien d'autre : écarté
            art(3, fiche=dict(FICHE, pertinence=2)),                          # peu pertinent mais favori
            art(4, fiche=dict(FICHE, pertinence=2)),                          # peu pertinent mais déjà notifié
            art(5, ajout=10),                                                 # trop ancien
            art(6, fiche=None),                                               # sans fiche
            art(7, retracte=True),                                            # rétracté
        ])
        (self.tmp / "notifications.json").write_text(json.dumps({"envoyes": {"demo:4": J(0)}}))
        with mock.patch.object(notifications, "selectionner", return_value=[]):
            ids = [a["id"] for a in audio.selectionner(self.cfg, base, {"demo:3"})]
        self.assertEqual(ids, ["demo:4", "demo:3", "demo:1"])               # notifiés, favoris, puis pertinents
        # ceux que la notification de demain choisira sont aussi retenus
        ids = [a["id"] for a in audio.selectionner(self.cfg, base, set())]
        self.assertIn("demo:1", ids)
        self.assertNotIn("demo:6", ids)

    def test_generation_empreinte_et_site(self):
        base = core.Base([art(1), art(2)])
        voix = FausseVoix()
        with mock.patch.object(audio, "synthetiser", voix):
            r = audio.generer(self.cfg, base, set())
            self.assertEqual((r["nouveaux"], r["gardes"]), (2, 0))
            n = len(voix.appels)
            r = audio.generer(self.cfg, base, set())                         # rien n'a changé : rien n'est refait
            self.assertEqual((r["nouveaux"], r["gardes"]), (0, 2))
            self.assertEqual(len(voix.appels), n)
            base.articles[0]["fiche"]["verdict"] = "Nouveau verdict"       # fiche corrigée : MP3 refait
            r = audio.generer(self.cfg, base, set())
            self.assertEqual((r["nouveaux"], r["gardes"]), (1, 1))
        self.assertTrue(all(v == "fr-FR-DeniseNeural" for v, _ in voix.appels))
        manifeste = json.loads((self.tmp / "audio" / "audio.json").read_text(encoding="utf-8"))
        self.assertEqual(manifeste["demo:1"]["fichier"], audio.nom_fichier("demo:1"))
        self.assertNotIn(":", manifeste["demo:1"]["fichier"])
        # le site recopie les MP3 et indique le chemin dans data.json
        site.construire(self.cfg, articles=base.articles + [art(9, fiche=None)])
        data = json.loads((self.tmp / "site" / "data.json").read_text(encoding="utf-8"))
        par_id = {a["id"]: a for a in data["articles"]}
        self.assertEqual(par_id["demo:1"]["audio"], "audio/" + audio.nom_fichier("demo:1"))
        self.assertNotIn("audio", par_id["demo:9"])
        self.assertTrue((self.tmp / "site" / par_id["demo:1"]["audio"]).exists())

    def test_purge(self):
        dossier = self.tmp / "audio"
        dossier.mkdir()
        for nom in ("vieux.mp3", "recent.mp3", "orphelin.mp3"):
            (dossier / nom).write_bytes(b"x")
        manifeste = {"a": {"fichier": "vieux.mp3", "jour": J(8)}, "b": {"fichier": "recent.mp3", "jour": J(7)},
                     "c": {"fichier": "disparu.mp3", "jour": J(0)}}
        effaces = audio.purger(manifeste, audio.reglages(self.cfg))
        self.assertEqual(effaces, 2)
        self.assertEqual(list(manifeste), ["b"])
        self.assertEqual(sorted(f.name for f in dossier.iterdir()), ["recent.mp3"])

    def test_panne_de_la_voix_sans_echec(self):
        base = core.Base([art(i) for i in range(1, 6)])
        voix = FausseVoix(panne=True)
        with mock.patch.object(audio, "synthetiser", voix), self.assertLogs("veille", "WARNING") as logs:
            r = audio.generer(self.cfg, base, set())
        self.assertEqual((r["nouveaux"], r["echecs"]), (0, 3))               # on s'arrête après 3 échecs de suite
        self.assertTrue(any("indisponible" in l for l in logs.output))
        with mock.patch.object(audio, "selectionner", side_effect=RuntimeError("bug")), \
                self.assertLogs("veille", "WARNING"):
            audio.generer(self.cfg, base, set())                             # jamais d'exception

    def test_plafond_par_jour(self):
        self.cfg["audio"]["max_par_jour"] = 2
        base = core.Base([art(i) for i in range(1, 6)])
        with mock.patch.object(audio, "synthetiser", FausseVoix()):
            self.assertEqual(audio.generer(self.cfg, base, set())["nouveaux"], 2)
            self.assertEqual(audio.generer(self.cfg, base, set())["nouveaux"], 2)   # la suite le lendemain

    def test_inactif(self):
        self.cfg["audio"]["actif"] = False
        with mock.patch.object(audio, "synthetiser", FausseVoix()) as v:
            self.assertEqual(audio.generer(self.cfg, core.Base([art(1)]), set())["nouveaux"], 0)
        self.assertFalse((self.tmp / "audio").exists())


class TestVoixReelle(unittest.TestCase):
    """Vrai appel à edge-tts (réseau) : sauté hors ligne ou si edge-tts n'est pas installé."""

    def test_vrai_mp3_court(self):
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            self.skipTest("edge-tts non installé")
        try:
            donnees = audio.synthetiser("Bonjour, ceci est un essai.", "fr-FR-DeniseNeural")
        except Exception as ex:
            self.skipTest(f"service de voix injoignable ({ex})")
        self.assertGreater(len(donnees), 2000)
        self.assertTrue(donnees[:3] == b"ID3" or donnees[0] == 0xFF)          # en-tête MP3


if __name__ == "__main__":
    unittest.main()
