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

from veille import audio, core, site

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
        cfg["audio"] = {"actif": True}
        mp3 = cls.tmp / "audio"                         # un MP3 (factice) pour l'article ARFID seulement
        mp3.mkdir()
        (mp3 / "arfid.mp3").write_bytes(b"ID3" + b"\0" * 2000)
        jour = audio.jour_local(cfg).isoformat()         # et un audio du jour (factice)
        (mp3 / f"jour-{jour}.mp3").write_bytes(b"ID3" + b"\0" * 2000)
        (mp3 / "audio.json").write_text(json.dumps({
            "demo:3": {"fichier": "arfid.mp3", "jour": J(0), "empreinte": "x"},
            f"jour:{jour}": {"fichier": f"jour-{jour}.mp3", "jour": jour, "empreinte": "y", "octets": 2003,
                             "duree": 240, "titres": ["Hypnose et SII", "Alexithymie"]}}))
        with mock.patch.object(site, "SORTIE", cls.tmp / "site"), mock.patch.object(site, "ETAT", cls.tmp / "etat.json"), \
                mock.patch.object(audio, "DOSSIER", mp3):
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
        self.assertTrue(p.locator("#recherche").is_hidden())                    # en-tête condensé : barre repliée
        p.click("#btn-recherche")
        p.fill("#recherche", "zygomorphique")                                    # mot présent seulement dans un abstract
        p.wait_for_function("document.getElementById('compteur').textContent.startsWith('1 article ')")
        self.assertIn("Gut-directed", p.text_content("#liste"))
        p.fill("#recherche", "")
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        p.fill("#recherche", "zygomorphique")
        p.wait_for_function("document.getElementById('compteur').textContent.startsWith('1 article ')")
        p.click("#btn-recherche")                                                # replier la barre efface la recherche
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        self.assertTrue(p.locator("#recherche").is_hidden())

    def test_filtres_et_favoris(self):
        p = self.page
        self.assertTrue(p.locator("#themes").is_hidden())                       # puces et menus repliés
        p.click("#btn-filtres")
        p.click('#themes .chip[data-id="arfid_toc"]')
        p.wait_for_function("document.querySelectorAll('.carte').length === 1")
        self.assertIn("ARFID", p.text_content("#liste"))                         # article ancien (archive) filtrable
        p.locator('.carte button[data-act="fav"]').click()
        self.assertEqual(p.text_content("#nb-filtres"), "1")                    # filtre actif visible même replié
        p.click('#themes .chip[data-genre=""]')
        self.assertEqual(p.text_content("#nb-filtres"), "")
        p.click("#btn-filtres")
        self.assertTrue(p.locator("#themes").is_hidden())
        p.click("#btn-favoris")
        p.wait_for_function("document.querySelectorAll('.carte').length === 1")
        self.assertIn("ARFID", p.text_content("#liste"))
        self.assertEqual(p.text_content("#nb-favoris").strip(), "1")

    def test_ecouter(self):
        """Bouton « Écouter » : voix du navigateur simulée (lecture, pause, reprise, stop, abstract en anglais)."""
        p = self.page
        p.add_init_script("""
            window.__dit = [];
            const s = { _u: null, getVoices: () => [{ name: 'Google français', lang: 'fr-FR' }, { name: 'Google US English', lang: 'en-US' }],
              speak(u) { window.__dit.push([u.lang, u.text]); this._u = u;
                         setTimeout(() => { if (this._u === u) { this._u = null; u.onend && u.onend(); } }, 40); },
              cancel() { const u = this._u; this._u = null; if (u && u.onerror) u.onerror({ error: 'interrupted' }); } };
            Object.defineProperty(window, 'speechSynthesis', { value: s });
            window.SpeechSynthesisUtterance = function (t) { this.text = t; };""")
        p.reload()
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        carte = p.locator(".carte", has_text="Gut-directed")
        bouton, stop = carte.locator('button[data-act="ecouter"]'), carte.locator('button[data-act="stop"]')
        self.assertTrue(stop.is_hidden())
        bouton.click()
        self.assertIn("Pause", bouton.text_content())
        self.assertTrue(stop.is_visible())
        bouton.click()                                                            # pause
        self.assertIn("Reprendre", bouton.text_content())
        n = p.evaluate("__dit.length")
        p.wait_for_timeout(150)
        self.assertEqual(p.evaluate("__dit.length"), n)                           # silence pendant la pause
        bouton.click()                                                            # reprise jusqu'au bout
        p.wait_for_function("""() => document.querySelector('.carte[data-id="demo:1"] button[data-act="ecouter"]')
                                        .textContent.includes('Écouter')""")
        dit = " ".join(t for _, t in p.evaluate("__dit"))
        self.assertIn("double le taux", dit)
        self.assertIn("52 % vs 27 %", dit)
        self.assertTrue(stop.is_hidden())
        # sans fiche : l'abstract est chargé puis lu par une voix anglaise
        p.evaluate("__dit.length = 0")
        autre = p.locator(".carte", has_text="Alexithymia")
        autre.locator('button[data-act="ecouter"]').click()
        p.wait_for_function("__dit.some(([l, t]) => l === 'en-US' && t.includes('interoceptive'))")
        autre.locator('button[data-act="stop"]').click()
        self.assertIn("Écouter", autre.locator('button[data-act="ecouter"]').text_content())

    def test_ecouter_mp3(self):
        """Fiche avec MP3 : un seul élément <audio> (lecture simulée), pas la voix du téléphone ; Stop l'arrête."""
        p = self.page
        p.add_init_script("""
            window.__dit = []; window.__joue = [];
            Object.defineProperty(window, 'speechSynthesis', { value: { getVoices: () => [], speak(u) { __dit.push(u.text); }, cancel() {} } });
            window.SpeechSynthesisUtterance = function (t) { this.text = t; };
            const P = HTMLMediaElement.prototype;
            Object.defineProperty(P, 'paused', { get() { return !this.__lit; } });
            P.play = function () { window.__lecteur = this; this.__lit = true; __joue.push(this.getAttribute('src')); this.dispatchEvent(new Event('play')); return Promise.resolve(); };
            P.pause = function () { if (!this.__lit) return; this.__lit = false; this.dispatchEvent(new Event('pause')); };
            P.load = function () {};""")
        p.reload()
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        self.assertEqual(json.loads((self.tmp / "site" / "audio" / "audio.json").read_text())["demo:3"]["fichier"], "arfid.mp3")
        carte = p.locator(".carte", has_text="ARFID")
        bouton, stop = carte.locator('button[data-act="ecouter"]'), carte.locator('button[data-act="stop"]')
        self.assertIn("🎧 Écouter", bouton.text_content())
        self.assertIn("🔊 Écouter", p.locator(".carte", has_text="Gut-directed").locator('button[data-act="ecouter"]').text_content())
        bouton.click()
        self.assertIn("Pause", bouton.text_content())
        self.assertEqual(p.evaluate("__joue"), ["audio/arfid.mp3"])
        self.assertEqual(p.evaluate("__dit"), [])                                 # pas de synthèse vocale
        self.assertEqual(p.evaluate("navigator.mediaSession.metadata && navigator.mediaSession.metadata.artist"), "SciFeed")
        bouton.click()                                                            # pause, puis reprise
        self.assertIn("Reprendre", bouton.text_content())
        bouton.click()
        self.assertIn("Pause", bouton.text_content())
        stop.click()
        self.assertIn("🎧 Écouter", bouton.text_content())
        self.assertTrue(stop.is_hidden())
        self.assertEqual(p.evaluate("navigator.mediaSession.playbackState"), "none")
        self.assertEqual(p.evaluate("__lecteur.paused"), True)
        # pause depuis l'écran de verrouillage (le lecteur se met en pause tout seul), puis MP3 fini
        bouton.click()
        p.evaluate("__lecteur.pause()")
        self.assertIn("Reprendre", bouton.text_content())
        bouton.click()
        p.evaluate("__lecteur.__lit = false; __lecteur.dispatchEvent(new Event('ended'))")
        self.assertIn("🎧 Écouter", bouton.text_content())
        self.assertTrue(stop.is_hidden())
        self.assertEqual(p.evaluate("__joue.length"), 4)

    def test_audio_du_jour(self):
        """Bouton « Audio du jour » en haut de la liste : même lecteur (Pause / Reprendre / Stop), flux podcast listé."""
        p = self.page
        p.add_init_script("""
            window.__joue = [];
            const P = HTMLMediaElement.prototype;
            Object.defineProperty(P, 'paused', { get() { return !this.__lit; } });
            P.play = function () { this.__lit = true; __joue.push(this.getAttribute('src')); this.dispatchEvent(new Event('play')); return Promise.resolve(); };
            P.pause = function () { if (!this.__lit) return; this.__lit = false; this.dispatchEvent(new Event('pause')); };
            P.load = function () {};""")
        p.reload()
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        bouton, stop = p.locator("#audio-jour"), p.locator("#audio-jour-stop")
        self.assertTrue(bouton.is_visible())
        self.assertIn("2 articles · 4 min", p.text_content("#audio-jour-info"))
        self.assertTrue(stop.is_hidden())
        bouton.click()
        self.assertIn("Pause", bouton.text_content())
        self.assertTrue(stop.is_visible())
        self.assertRegex(p.evaluate("__joue[0]"), r"^audio/jour-\d{4}-\d\d-\d\d\.mp3$")
        self.assertIn("veille du", p.evaluate("navigator.mediaSession.metadata.title"))
        bouton.click()
        self.assertIn("Reprendre", bouton.text_content())
        # une fiche avec MP3 prend la main : le bouton du jour revient à l'état de repos
        p.locator(".carte", has_text="ARFID").locator('button[data-act="ecouter"]').click()
        self.assertIn("Audio du jour", bouton.text_content())
        self.assertEqual(p.evaluate("__joue[__joue.length - 1]"), "audio/arfid.mp3")
        bouton.click()
        stop.click()
        self.assertIn("🎧 Audio du jour", bouton.text_content())
        self.assertTrue(stop.is_hidden())
        self.assertIn("podcast.xml", p.inner_html("#liste-flux"))
        self.assertIn("<enclosure", (self.tmp / "site" / "podcast.xml").read_text(encoding="utf-8"))

    def test_nouveaux_et_chercher_une_version(self):
        p = self.page
        # première visite : rien n'est « nouveau » (tout le serait)
        self.assertEqual(p.locator(".badge.nouveau").count(), 0)
        self.assertTrue(p.locator("#voir-nouveaux").is_hidden())
        # visite précédente il y a deux jours, vue jusqu'aux articles d'hier
        p.evaluate("""j => { const e = JSON.parse(localStorage.getItem('veille-etat-v1'));
                             e.visite = { jour: j, avant: '', debut: 0 };
                             localStorage.setItem('veille-etat-v1', JSON.stringify(e)); }""", J(1))
        p.reload()
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        self.assertEqual(p.locator(".badge.nouveau").count(), 1)
        self.assertIn("Gut-directed", p.locator(".carte", has=p.locator(".badge.nouveau")).text_content())
        self.assertEqual(p.text_content("#voir-nouveaux"), "1 nouveau depuis ta dernière visite")
        p.click("#voir-nouveaux")
        p.wait_for_function("document.querySelectorAll('.carte').length === 1")
        p.click("#voir-nouveaux")                                                # « Tout afficher »
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        # rouverte peu après : les mêmes restent « nouveaux » le temps de les lire
        p.reload()
        p.wait_for_function("document.querySelectorAll('.carte').length === 3")
        self.assertEqual(p.locator(".badge.nouveau").count(), 1)
        # lien Google Scholar, sur le titre de l'article
        lien = p.locator(".carte", has_text="Alexithymia").locator("a", has_text="Chercher une version")
        self.assertIn("scholar.google.com/scholar?q=Alexithymia%20and%20interoception", lien.get_attribute("href"))

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
