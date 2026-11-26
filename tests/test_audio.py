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


class _Bac(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = core.charger_config()
        self.cfg["audio"] = {"actif": True, "jours_conserves": 7, "max_par_jour": 25, "pertinence_min": 4}
        self.patches = [mock.patch.object(audio, "DOSSIER", self.tmp / "audio"),
                        mock.patch.object(pipeline, "DATA", self.tmp),
                        mock.patch.object(pipeline, "FICHIER", self.tmp / "articles.json"),
                        mock.patch.object(pipeline, "ETAT", self.tmp / "etat.json"),
                        mock.patch.object(site, "SORTIE", self.tmp / "site"),
                        mock.patch.object(site, "ETAT", self.tmp / "etat.json"),
                        mock.patch.dict("os.environ", {"SYNC_GIST_ID": ""})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)


class TestAudio(_Bac):
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


class FauxScript:
    cle, url = "test", "http://test"

    def __init__(self, reponse=None, panne=False):
        self.reponse, self.panne, self.recu = reponse, panne, None

    def completer(self, systeme, utilisateur):
        self.recu = (systeme, utilisateur)
        if self.panne:
            raise RuntimeError("quota")
        return json.dumps({"script": self.reponse}), "faux-modele"


class Reponse:
    def __init__(self, code=200):
        self.status_code = code

    def raise_for_status(self):
        pass


class TestAudioDuJour(_Bac):
    def base(self):
        arts = [art(i, fiche=dict(FICHE, titre_court=f"Étude {i}", conclusion_simple=f"Piste {i} à confirmer.",
                                  pertinence=6 - i)) for i in range(1, 8)]
        return core.Base(arts)

    def test_selection_partagee_avec_la_notification(self):
        base = self.base()
        jour = audio.jour_local(self.cfg)
        with mock.patch.object(audio, "synthetiser", FausseVoix()):
            v = audio.generer_jour(self.cfg, base, client=FauxScript(panne=True), jour=jour)
        self.assertEqual(len(v["ids"]), self.cfg["notifications"]["nombre"])
        sel = json.loads((self.tmp / "selection-du-jour.json").read_text(encoding="utf-8"))
        self.assertEqual((sel["jour"], sel["ids"]), (jour.isoformat(), v["ids"]))
        # le matin : la notification reprend exactement ces articles, même si le classement a changé
        for a in base.articles:
            if a["id"] not in v["ids"]:
                a["fiche"]["pertinence"] = 5
        choix = notifications.selection_de_la_nuit(self.cfg, base, set(), jour)
        self.assertEqual([a["id"] for a, _, _ in choix], v["ids"])
        # déjà envoyé : retiré ; sélection d'un autre jour : ignorée (choix habituel)
        choix = notifications.selection_de_la_nuit(self.cfg, base, {v["ids"][0]}, jour)
        self.assertEqual([a["id"] for a, _, _ in choix], v["ids"][1:])
        self.assertIsNone(notifications.selection_de_la_nuit(self.cfg, base, set(), jour + dt.timedelta(days=1)))

    def test_notification_avec_action_ecouter(self):
        base = self.base()
        pipeline.sauvegarder(base)
        jour = audio.jour_local(self.cfg)
        with mock.patch.object(audio, "synthetiser", FausseVoix()):
            v = audio.generer_jour(self.cfg, base, client=FauxScript(panne=True), jour=jour)
        self.cfg["notifications"]["hebdo"] = {"actif": False}
        from zoneinfo import ZoneInfo
        maintenant = dt.datetime.combine(jour, dt.time(8), tzinfo=ZoneInfo("Europe/Paris"))
        for en_ligne, attendu in ((200, True), (404, False)):
            (self.tmp / "notifications.json").unlink(missing_ok=True)
            envois, tetes = [], []
            with mock.patch.dict("os.environ", {"NTFY_TOPIC": "canal", "GITHUB_REPOSITORY": "moi/sci-feed"}), \
                    mock.patch.object(notifications.requests, "post", lambda url, json=None, **kw: envois.append(json) or Reponse()), \
                    mock.patch.object(notifications.requests, "head", lambda url, **kw: tetes.append(url) or Reponse(en_ligne)), \
                    mock.patch("time.sleep", lambda s: None):
                notifications.notifier(self.cfg, forcer=True, client=FauxScript(panne=True), maintenant=maintenant)
            self.assertEqual(sorted(m["title"] for m in envois), sorted(v["titres"]))      # les mêmes que l'audio
            self.assertEqual(tetes[0], f"https://moi.github.io/sci-feed/audio/jour-{jour.isoformat()}.mp3")
            labels = [x["label"] for x in envois[0].get("actions", [])]
            self.assertEqual("🎧 Écouter" in labels, attendu)
            self.assertIn("Ouvrir SciFeed", labels)

    def test_script_de_secours_et_script_ia(self):
        base = self.base()
        jour = dt.date(2026, 11, 22)
        s = audio.script_secours(base.articles[:2], jour)
        self.assertTrue(s.startswith("Bonjour, voici la veille SciFeed du dimanche 22 novembre. 2 articles"))
        self.assertIn("Premier article : Étude 1. Double le taux de répondeurs. Piste 1 à confirmer.", s)
        self.assertIn("Deuxième article : Étude 2.", s)
        self.assertNotIn("Piste 3", s)
        # IA : reçoit les fiches, le texte rendu est nettoyé du markdown
        texte = "**Bonjour**, voici la veille. " + "Une phrase simple sur l'étude. " * 60
        ia = FauxScript(texte)
        script, origine = audio.script_ia(self.cfg, base.articles[:2], jour, ia)
        self.assertEqual(script[:30], "Bonjour, voici la veille. Une ")
        self.assertEqual(origine, "écrit par faux-modele")
        self.assertIn("dimanche 22 novembre", ia.recu[0])
        self.assertIn("Population : 120 adultes SII", ia.recu[1])
        # échecs : pas de texte, et la raison (journal « texte de secours (raison) »)
        script, origine = audio.script_ia(self.cfg, base.articles[:2], jour, FauxScript("Trop court."))
        self.assertIsNone(script)
        self.assertIn("trop courte (2 mots, 80 au moins)", origine)
        script, origine = audio.script_ia(self.cfg, base.articles[:2], jour, FauxScript(panne=True))
        self.assertEqual((script, origine), (None, "IA en échec : quota"))
        sans_cle = FauxScript(texte)
        sans_cle.cle, sans_cle.url = "", "https://exemple.org"
        self.assertEqual(audio.script_ia(self.cfg, base.articles[:2], jour, sans_cle), (None, "aucune clé d'IA disponible"))
        with mock.patch.object(audio, "synthetiser", FausseVoix()), self.assertLogs("veille", "INFO") as logs:
            v = audio.generer_jour(self.cfg, base, client=FauxScript(panne=True), jour=jour - dt.timedelta(days=3))
        self.assertTrue(any("texte de secours (IA en échec : quota)" in l for l in logs.output))
        self.assertTrue(v["texte"].startswith("secours, IA en échec"))
        # MP3 du jour : script de l'IA quand elle répond, une seule voix ; refait seulement si les articles changent
        voix = FausseVoix()
        with mock.patch.object(audio, "synthetiser", voix):
            v = audio.generer_jour(self.cfg, base, client=FauxScript(texte), jour=jour)
            self.assertEqual(len(voix.appels), 1)
            self.assertEqual(voix.appels[0][0], "fr-FR-DeniseNeural")
            self.assertTrue(voix.appels[0][1].startswith("Bonjour, voici la veille."))
            audio.generer_jour(self.cfg, base, client=FauxScript(texte), jour=jour)
            self.assertEqual(len(voix.appels), 1)
        self.assertEqual(v["texte"], "IA, écrit par faux-modele")
        self.assertTrue((self.tmp / "audio" / f"jour-{jour.isoformat()}.mp3").exists())
        self.assertGreater(v["duree"], 0)
        # panne de la voix : avertissement, pas d'exception
        with mock.patch.object(audio, "synthetiser", FausseVoix(panne=True)), self.assertLogs("veille", "WARNING"):
            self.assertIsNone(audio.generer_jour(self.cfg, base, client=FauxScript(texte), jour=jour + dt.timedelta(days=1)))

    def test_collecte_en_retard_audio_aligne_sur_les_envois(self):
        """Notifications déjà parties aujourd'hui (collecte en retard) : l'audio parle des articles envoyés."""
        base = self.base()
        pipeline.sauvegarder(base)
        jour = audio.jour_local(self.cfg)
        from zoneinfo import ZoneInfo
        maintenant = dt.datetime.combine(jour, dt.time(15), tzinfo=ZoneInfo("Europe/Paris"))
        self.cfg["notifications"]["hebdo"] = {"actif": False}
        self.cfg["notifications"]["nombre"] = 3
        with mock.patch.dict("os.environ", {"NTFY_TOPIC": "canal"}), \
                mock.patch.object(notifications.requests, "post", lambda url, json=None, **kw: Reponse()), \
                mock.patch.object(notifications, "audio_du_jour_en_ligne", lambda *a: ""), \
                mock.patch("time.sleep", lambda s: None):
            notifications.notifier(self.cfg, forcer=True, client=FauxScript(panne=True), maintenant=maintenant)
        etat = json.loads((self.tmp / "notifications.json").read_text(encoding="utf-8"))
        envoyes = etat["envoi_du_jour"]["ids"]
        self.assertEqual((etat["envoi_du_jour"]["jour"], len(envoyes)), (jour.isoformat(), 3))   # liste enregistrée
        # la collecte arrive ensuite et choisit d'autres articles (les envoyés sont exclus)
        self.cfg["notifications"]["nombre"] = 5
        choisis = [a["id"] for a in audio.preparer_selection(self.cfg, base)]
        self.assertFalse(set(choisis) & set(envoyes))
        with mock.patch.object(audio, "synthetiser", FausseVoix()), self.assertLogs("veille", "INFO") as logs:
            v = audio.generer_jour(self.cfg, base, client=FauxScript(panne=True), jour=jour)
        self.assertEqual(v["ids"], envoyes)                                   # les articles réellement envoyés
        self.assertEqual(v["source"], "notifications déjà envoyées aujourd'hui")
        self.assertTrue(any("3 articles (notifications déjà envoyées aujourd'hui)" in l for l in logs.output))
        # ancien format (avant envoi_du_jour) : les articles marqués envoyés ce jour-là
        del etat["envoi_du_jour"]
        (self.tmp / "notifications.json").write_text(json.dumps(etat), encoding="utf-8")
        self.assertEqual(sorted(audio.envoyes_du_jour(jour)), sorted(envoyes))
        # pas d'envoi aujourd'hui : sélection de la nuit
        etat["dernier_envoi"] = (jour - dt.timedelta(days=1)).isoformat()
        (self.tmp / "notifications.json").write_text(json.dumps(etat), encoding="utf-8")
        self.assertEqual([a["id"] for a in audio.articles_du_jour(self.cfg, base, jour)[0]], choisis)

    def test_commandes_et_workflow(self):
        """« tout » ne fait plus de MP3 (seulement le choix du jour) ; l'audio est une étape à part du workflow."""
        import sys
        from veille import __main__ as cli, resume_ia, sante
        appels = []
        with mock.patch.object(audio, "generer", lambda cfg: appels.append("fiches")), \
                mock.patch.object(audio, "generer_jour", lambda cfg: appels.append("jour")), \
                mock.patch.object(audio, "preparer_selection", lambda cfg: appels.append("selection")), \
                mock.patch.object(pipeline, "collecter", lambda cfg: None), \
                mock.patch.object(resume_ia, "resumer", lambda cfg: None), \
                mock.patch.object(sante, "verifier", lambda *a, **k: None), \
                mock.patch.object(sante.Releve, "enregistrer", lambda self: None), \
                mock.patch.object(site, "construire", lambda *a, **k: appels.append("site")), \
                mock.patch("veille.__main__.charger_config", lambda *a: self.cfg):
            for args in (["tout"], ["audio"], ["audio", "--jour"]):
                with mock.patch.object(sys, "argv", ["veille"] + args):
                    cli.main()
                appels.append("|")
        self.assertEqual(appels, ["selection", "site", "|", "fiches", "|", "fiches", "jour", "|"])
        import yaml
        wf = yaml.safe_load((core.RACINE / ".github" / "workflows" / "veille.yml").read_text(encoding="utf-8"))
        etapes = wf["jobs"]["veille"]["steps"]
        noms = [e.get("name") or e.get("uses") for e in etapes]
        i = {n: noms.index(n) for n in ("Collecte, fiches IA et site", "Sauvegarder la base d'articles",
                                        "Audio (MP3 des fiches, audio du jour)", "Site avec l'audio",
                                        "Garder les MP3 pour demain", "actions/upload-pages-artifact@v5")}
        self.assertEqual(sorted(i.values()), list(i.values()))              # dans cet ordre
        self.assertNotIn("veille audio", etapes[i["Collecte, fiches IA et site"]]["run"])
        a = etapes[i["Audio (MP3 des fiches, audio du jour)"]]
        self.assertEqual((a["timeout-minutes"], a["continue-on-error"]), (15, True))
        self.assertIn("python -m veille audio --jour", a["run"])
        self.assertTrue(etapes[i["Garder les MP3 pour demain"]]["if"].startswith("always()"))
        self.assertIn("65", wf["jobs"]["veille"]["timeout-minutes"])

    def test_podcast_et_site(self):
        base = self.base()
        voix = FausseVoix()
        jour = audio.jour_local(self.cfg)
        with mock.patch.object(audio, "synthetiser", voix):
            audio.generer_jour(self.cfg, base, client=FauxScript(panne=True), jour=jour - dt.timedelta(days=1))
            audio.generer_jour(self.cfg, base, client=FauxScript(panne=True), jour=jour)
        with mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "moi/sci-feed"}):
            site.construire(self.cfg, articles=base.articles)
        flux = (self.tmp / "site" / "podcast.xml").read_text(encoding="utf-8")
        import xml.etree.ElementTree as ET
        items = ET.fromstring(flux).findall("./channel/item")
        self.assertEqual(len(items), 2)
        self.assertIn(f"veille du {audio.date_parlee(jour, avec_jour=False)}", items[0].find("title").text)
        enc = items[0].find("enclosure")
        self.assertEqual(enc.get("url"), f"https://moi.github.io/sci-feed/audio/jour-{jour.isoformat()}.mp3")
        self.assertEqual(enc.get("type"), "audio/mpeg")
        self.assertGreater(int(enc.get("length")), 0)
        self.assertRegex(items[0].find("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration").text, r"^\d\d:\d\d:\d\d$")
        meta = json.loads((self.tmp / "site" / "data.json").read_text(encoding="utf-8"))["meta"]
        self.assertEqual(meta["audio_jour"]["fichier"], f"audio/jour-{jour.isoformat()}.mp3")
        self.assertEqual(meta["podcast"], "podcast.xml")
        self.assertTrue((self.tmp / "site" / meta["audio_jour"]["fichier"]).exists())


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
