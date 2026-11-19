"""Tests du site dans un vrai navigateur (Chromium, via Playwright).

Lancés par GitHub à chaque changement de code, avant la publication. En local, ils sont sautés
si Playwright n'est pas installé :  pip install playwright  puis  python -m playwright install chromium
"""
import datetime as dt
import functools
import http.server
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from veille import core, site

try:
    from playwright.sync_api import sync_playwright
except ImportError:          # pragma: no cover
    sync_playwright = None

J = lambda n: (core.aujourd_hui() - dt.timedelta(days=n)).isoformat()


def exemples():
    """Quelques articles fictifs : récents et anciens, avec ou sans fiche IA."""
    def art(i, titre, themes, ajout, resume, fiche=None):
        a = core.nouvel_article(titre=titre, themes=themes, revue="Revue fictive", date=ajout, resume=resume,
                                auteurs=["Martin A", "Durand B"], url=f"https://exemple.org/{i}")
        a["id"], a["ajoute_le"], a["fiche"] = f"demo:{i}", ajout, fiche
        return a
    fiche = {"verdict": "L'hypnose digestive en groupe double le taux de répondeurs.", "type_etude": "essai randomisé",
             "population": "120 adultes SII", "resultats_cles": ["52 % vs 27 %"], "niveau_preuve": 4, "pertinence": 5}
    return [
        art(1, "Gut-directed hypnotherapy in IBS: a randomized trial", ["sii", "hypnose"], J(0),
            "Background. We randomized adults with IBS. The word zygomorphique appears only here.", fiche),
        art(2, "Alexithymia and interoception in functional dyspepsia", ["alexithymie"], J(1),
            "Cross-sectional study of interoceptive accuracy. " * 12),
        art(3, "Exposure therapy for ARFID: an older pilot study", ["arfid_toc"], J(60),
            "Pilot study of exposure-based therapy in avoidant restrictive food intake disorder."),
    ]


class Silencieux(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@unittest.skipIf(sync_playwright is None, "Playwright non installé (tests du site sautés)")
class TestSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cfg = core.charger_config()
        cfg["site"] = {"jours_recents": 30, "details_par_fichier": 100}
        with mock.patch.object(site, "SORTIE", cls.tmp / "site"), mock.patch.object(site, "ETAT", cls.tmp / "etat.json"):
            site.construire(cfg, articles=exemples())
        gestion = functools.partial(Silencieux, directory=str(cls.tmp / "site"))
        cls.serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), gestion)
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.serveur.server_address[1]}/"
        cls.pw = sync_playwright().start()
        chemin = os.environ.get("PW_CHROMIUM")          # navigateur déjà installé ailleurs (facultatif)
        cls.navigateur = cls.pw.chromium.launch(**({"executable_path": chemin} if chemin else {}))

    @classmethod
    def tearDownClass(cls):
        cls.navigateur.close()
        cls.pw.stop()
        cls.serveur.shutdown()
        cls.serveur.server_close()
        shutil.rmtree(cls.tmp)

    def setUp(self):
        self.ctx = self.navigateur.new_context(viewport={"width": 400, "height": 850})
        self.page = self.ctx.new_page()
        self.erreurs = []
        self.page.on("pageerror", lambda e: self.erreurs.append(str(e)))
        self.page.goto(self.url)
        # premier affichage, puis archive (articles anciens) chargée juste après
        self.page.wait_for_function("document.querySelectorAll('.carte').length === 3")

    def tearDown(self):
        self.ctx.close()
        self.assertEqual(self.erreurs, [])

    def compteur(self):
        return self.page.text_content("#compteur")

    def test_liste_et_details(self):
        p = self.page
        self.assertIn("3 articles", self.compteur())
        self.assertIn("double le taux", p.text_content("body"))                 # fiche IA affichée
        self.assertIn("Cross-sectional", p.text_content(".extrait"))            # extrait sans fiche
        carte = p.locator(".carte", has_text="Gut-directed")
        carte.locator("summary").click()                                         # abstract chargé à la demande
        carte.locator(".abstract").wait_for()
        self.assertIn("zygomorphique", carte.locator(".abstract").text_content())
        self.assertIn("Martin A", carte.locator("details").text_content())
        self.assertIn("↺ Non lu", carte.locator('button[data-act="lu"]').text_content())   # ouvert = lu

    def test_recherche_dans_les_abstracts(self):
        p = self.page
        p.fill("#recherche", "zygomorphique")                                    # mot présent seulement dans un abstract
        p.wait_for_function("document.getElementById('compteur').textContent.startsWith('1 article ')")
        self.assertIn("Gut-directed", p.text_content("#liste"))
        p.fill("#recherche", "")
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")

    def test_filtres_et_favoris(self):
        p = self.page
        p.click('#themes .chip[data-id="arfid_toc"]')
        p.wait_for_function("document.querySelectorAll('.carte').length === 1")
        self.assertIn("ARFID", p.text_content("#liste"))                         # article ancien (archive) filtrable
        p.locator('.carte button[data-act="fav"]').click()
        p.click('#themes .chip[data-genre=""]')
        p.click("#btn-favoris")
        p.wait_for_function("document.querySelectorAll('.carte').length === 1")
        self.assertIn("ARFID", p.text_content("#liste"))
        self.assertEqual(p.text_content("#nb-favoris").strip(), "1")

    def test_hors_connexion(self):
        p = self.page
        p.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller !== null")
        p.reload()                                                                 # 2e visite : tout passe par le cache
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        p.wait_for_function("caches.match('data.json').then(Boolean)", polling=200)
        self.ctx.set_offline(True)
        p.reload()
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        carte = p.locator(".carte", has_text="Alexithymia")                       # abstract jamais ouvert : message clair
        carte.locator("summary").click()
        carte.locator(".charge-details", has_text="indisponible").wait_for()


if __name__ == "__main__":
    unittest.main()
