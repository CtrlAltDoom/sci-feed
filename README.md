# Veille scientifique

Agrégateur de publications scientifiques, gratuit et open source, avec une **fiche de lecture IA** sous chaque titre : le verdict en une phrase, le type d'étude, l'effectif, les résultats clés, le niveau de preuve, la qualité méthodologique et la pertinence pour votre pratique.

- **Sources** : PubMed, Europe PMC (dont les preprints medRxiv, bioRxiv et PsyArXiv), OpenAlex, ClinicalTrials.gov, ainsi que tous les flux RSS de revues ou de blogs que vous ajoutez.
- **Fonctionnement automatique** : chaque matin, GitHub collecte les nouveautés, rédige les fiches et publie votre page. Votre ordinateur n'a pas besoin d'être allumé.
- **Lecture** : une page web pensée pour le téléphone, avec des filtres (thème, type d'étude, niveau de preuve), la gestion des lus, des favoris et des articles masqués, ainsi qu'un export Zotero.
- **Flux RSS en sortie** : un flux global (`feed.xml`), un flux par thème et un par étiquette, utilisables dans Feedly, Inoreader, etc.
- **Coût** : 0 €. Tout passe par des services gratuits.

> ⚠️ Les fiches sont générées par IA à partir des seuls abstracts. Elles servent à trier, pas à remplacer la lecture de l'article.

---

## Installation (environ 15 minutes, depuis un ordinateur)

### 1. Créer le dépôt GitHub
1. Créez un compte sur <https://github.com> si vous n'en avez pas.
2. Cliquez sur **New repository** et nommez-le par exemple `veille`. Choisissez **Public**, condition pour que la page web soit gratuite.
3. Sur la page du dépôt, cliquez sur **uploading an existing file** et glissez-y **tout le contenu** du dossier décompressé, y compris le dossier caché `.github`.
   *Sur Mac, appuyez sur Cmd + Maj + . dans le Finder pour afficher les fichiers cachés.*
   Cliquez ensuite sur **Commit changes**.

### 2. Obtenir une clé IA gratuite (OpenRouter)
1. Créez un compte sur <https://openrouter.ai>, puis allez dans **Keys** et cliquez sur **Create key**. Copiez la clé.
2. Dans votre dépôt GitHub, allez dans **Settings → Secrets and variables → Actions → New repository secret**.
   - Name : `LLM_API_KEY`
   - Secret : collez la clé.

### 3. Activer la page web
Dans **Settings → Pages**, réglez **Source** sur **GitHub Actions**.

### 4. Premier lancement
Allez dans l'onglet **Actions**, cliquez sur **Veille quotidienne**, puis sur **Run workflow**. Comptez 5 à 15 minutes.
Votre page sera ensuite à l'adresse `https://VOTRE-PSEUDO.github.io/veille/`.
Sur le téléphone, ouvrez-la puis choisissez **Installer l'application** (ou **Ajouter à l'écran d'accueil**) : elle s'ouvre alors comme une appli, avec son icône, et reste consultable hors connexion.

Ensuite, tout se met à jour seul chaque matin.

---

## Personnaliser

Tout se règle dans **`config.yaml`**. Sur GitHub, ouvrez le fichier, cliquez sur le crayon, modifiez, puis faites **Commit**.

- **Thèmes** : chaque thème est une liste de groupes de mots-clés.
  `[[A, B], [C, D]]` signifie : (A ou B) **et** (C ou D), recherché dans le titre et l'abstract.
- **`designs_forts_seulement: true`** : ne garde que les essais randomisés, les méta-analyses et les revues systématiques. Utile pour les sujets très larges comme « anxiété ».
- **`exclure`** : mots qui écartent un article s'ils figurent dans le titre (par exemple « in vitro »).
- **Étiquettes** (`etiquettes`) : filtres de tri colorés, calculés sur les articles déjà collectés. Elles ne lancent aucune recherche et ne coûtent rien. Même syntaxe que les thèmes, avec en plus :
  - `"mot*"` : troncature (`alexithymi*` trouve alexithymia, alexithymic…) ;
  - `titre_seulement: true` : ne cherche que dans le titre (pour les mots présents dans presque tous les abstracts, comme anxiété) ;
  - `titre: [[...]]` : mots qui suffisent s'ils sont dans le titre ; `sauf: [...]` : mots qui annulent l'étiquette (voir l'exemple « Étude animale ») ;
  - `famille` : la couleur (`sujet` bleu, `approche` vert, `mecanisme` violet, `animal` rouge) ; `court` : le nom affiché sur la puce.
- **Intérêt** (`interet`) : vos priorités (points par thème, par étiquette, malus études animales, sérieux de la revue). Sert au tri « Pour moi » de la liste, qui combine récence et intérêt (`jours_par_point`), et à l'ordre de passage des fiches IA (articles du jour d'abord).
- **Revues** : type, domaine et notoriété de chaque revue viennent d'OpenAlex (citations sur 2 ans, h-index, volume annuel, DOAJ), gardés dans `data/revues.json`. C'est un repère sur la revue, pas un jugement sur l'article, et aucune IA n'intervient.
- **E-mail de contact** (demandé poliment par PubMed et OpenAlex) : mettez-le dans le secret `CONTACT_EMAIL` plutôt que dans `config.yaml`, pour qu'il ne soit pas public.

**Dans l'appli elle-même** (Filtres → Personnaliser), chaque lecteur peut, pour lui seul : donner un raccourci à chaque puce (« Anx »), masquer les puces qu'il n'utilise pas, et exporter/importer ses lus, favoris et réglages pour passer d'un appareil à l'autre.
- **Revues** : ajoutez une ligne `nom` + `url` dans `sources.rss.flux`. Pour trouver l'URL, cherchez l'icône RSS sur le site de la revue.
- **Flux non filtrés** (blogs, actualités) : utilisez `sources.rss.flux_libres`.
- **Profil du lecteur** : `ia.profil_lecteur` sert à noter la pertinence pour vous.

Une modification de `config.yaml` régénère la page tout de suite. Les nouveaux thèmes sont collectés au passage suivant, ou immédiatement si vous relancez à la main avec **Run workflow**.

## Notifications du matin (facultatif)

Chaque matin, les articles récents les plus pertinents pour vous arrivent sur le téléphone, avec un titre court et une conclusion en une phrase rédigés par l'IA. Gratuit, via l'appli **ntfy** (Android, iOS).

1. Choisissez un nom de canal difficile à deviner, par exemple `scifeed-` suivi d'une quinzaine de lettres et chiffres au hasard.
2. Ajoutez-le en secret GitHub sous le nom `NTFY_TOPIC`. Il reste ainsi hors du dépôt public.
3. Dans l'appli ntfy, appuyez sur **+** et abonnez-vous à ce même nom.
4. Pour tester tout de suite : **Actions → Notifications du matin → Run workflow**, en cochant « Envoyer maintenant ».

Réglages dans la section `notifications` de `config.yaml` : nombre, format (une notification par article ou un seul résumé), plage horaire, priorité, thèmes inclus ou exclus, niveau minimal de revue ou de preuve.

**Planning (heure de Paris)** : la collecte tourne la nuit, avec un créneau toutes les heures à partir de 1 h 23 en hiver (2 h 23 en été) jusqu'à 11 h 23 (12 h 23 en été) : le premier qui tourne la fait, les suivants s'arrêtent aussitôt, car GitHub part parfois avec des heures de retard (constaté jusqu'à 9 h). Les notifications partent une seule fois par jour, jamais avant 6 h : un essai toutes les 20 min de 6 h à 8 h 40 en hiver (9 h 40 en été), et aussi dès la fin de la collecte si elle finit après 6 h. Jusqu'à midi, elles attendent la collecte du jour ; en cas de problème, un filet horaire les envoie l'après-midi avec ce qu'il y a, jusqu'à 21 h au plus tard (`heure_min`, `attendre_collecte_jusqua`, `heure_max`).

**Réveil externe** (facultatif, plus ponctuel que GitHub) : sur [cron-job.org](https://cron-job.org) (gratuit), une tâche quotidienne vers 3 h qui envoie un `POST` à `https://api.github.com/repos/<vous>/<dépôt>/actions/workflows/veille.yml/dispatches`, avec l'en-tête `Authorization: Bearer <jeton GitHub à droits « Actions : écriture »>` et le corps `{"ref":"main","inputs":{"si_pas_fait":"true"}}`. Si la collecte du jour est déjà faite, rien ne se passe.

**Ne pas être notifié de ce qu'on a déjà vu** (facultatif) : si la synchronisation entre appareils est activée dans l'appli, ajoutez le secret `SYNC_GIST_ID` avec l'identifiant de votre gist (la fin de son adresse `gist.github.com/…/IDENTIFIANT`). Les articles lus, favoris ou masqués dans l'appli ne sont alors plus notifiés.

**Résumé de la semaine** : le dimanche matin, une notification de plus (sans bandeau) liste les 10 articles les plus marquants des 7 derniers jours. Réglages dans `notifications.hebdo`.

**Favoris jamais effacés** : la base efface les articles de plus de `conserver_jours` (180 jours), sauf vos favoris (secret `SYNC_GIST_ID`). Au moindre doute (gist injoignable, appli sans aucun favori), rien n'est effacé ce jour-là. Copie de secours facultative : créez un jeton GitHub (classique) avec le seul droit « gist » et mettez-le dans le secret `GIST_TOKEN`. Chaque nuit, vos favoris, avec leur fiche complète, sont alors recopiés dans un gist secret à part (« scifeed-favoris-secours.json », créé automatiquement), jamais dans le dépôt public. Un favori disparu de la base y est remis depuis cette copie.

**Favoris rétractés** : chaque jour, vos favoris sont revérifiés (OpenAlex, qui reprend la base Retraction Watch). Si l'un d'eux est rétracté, il est marqué « RÉTRACTÉ » dans l'appli et une notification vous prévient. Nécessite le secret `SYNC_GIST_ID`.

**Alertes de santé** : sur le même canal, une notification « ⚠️ SciFeed » prévient si une source est en panne plusieurs jours de suite, si l'IA ne rédige plus de fiches, si plus aucun article n'arrive, si la tâche quotidienne n'a pas tourné ou a échoué. Une notification « ✅ » suit quand tout est réparé. Réglages dans la section `sante`.

## Textes intégraux gratuits

Le lien « Texte libre » vient d'OpenAlex, de PubMed Central et d'Europe PMC, complétés chaque jour par **Unpaywall** (versions légales en accès ouvert : archives ouvertes, versions auteur, revues ouvertes). Unpaywall demande l'e-mail de contact (secret `CONTACT_EMAIL`). Les articles récents sans version libre sont revérifiés tous les 30 jours, car la version libre arrive souvent après la publication.

## Changer de fournisseur IA

Le code accepte n'importe quelle API « compatible OpenAI ». Il suffit de modifier `ia.base_url` et `ia.modeles`, puis de mettre la clé correspondante dans le secret `LLM_API_KEY`.

| Fournisseur | `base_url` | Remarque |
|---|---|---|
| OpenRouter (défaut) | `https://openrouter.ai/api/v1` | Modèles `:free` ou `openrouter/free`. 50 requêtes/jour, ou 1 000/jour après un achat unique de 10 $ de crédits. |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | Clé gratuite sur aistudio.google.com. Indiquez le nom de modèle affiché dans AI Studio. |
| Groq | `https://api.groq.com/openai/v1` | Offre gratuite avec des quotas quotidiens. |
| Ollama (local) | `http://localhost:11434/v1` | Uniquement si vous lancez l'outil sur votre propre PC. |

Plusieurs abstracts sont envoyés par requête (`articles_par_requete: 5`). Avec 50 requêtes par jour, on obtient jusqu'à environ 200 à 250 fiches quotidiennes. Les articles en surplus sont traités au passage suivant.

**Rattrapage automatique** : chaque soir à 20 h 17 (21 h 17 en été), tant qu'il reste des articles sans fiche, une tâche rédige des fiches pendant 40 min (sans collecte ni notification), puis s'arrête d'elle-même quand il n'y a plus de retard. Elle laisse à la collecte de la nuit les modèles Gemini à petit quota (`ia.rattrapage.modeles_reserves`), dont le quota ne se renouvelle qu'à 9 h ; si GitHub la lance après minuit, elle ne fait rien. Pour la couper : `ia.rattrapage.auto: false` dans `config.yaml`.

**Clés facultatives**, à ajouter aussi en secrets : `NCBI_API_KEY` (compte NCBI gratuit, rend PubMed plus rapide) et `OPENALEX_API_KEY`.

## Lancer en local (facultatif)

```bash
pip install -r requirements.txt
export LLM_API_KEY=...         # facultatif
python -m veille tout          # collecte + fiches + site (dossier site/)
python -m unittest discover tests   # tests hors-ligne
python -m tests.apercu         # aperçu de l'interface avec des exemples fictifs
```

## Architecture

```
config.yaml            ← tout le paramétrage
veille/
  sources/             ← un fichier par source (pubmed, europepmc, openalex, clinicaltrials, rss)
  core.py              ← mots-clés, dédoublonnage (DOI / PMID / titre), modèle d'article
  pipeline.py          ← collecte, fusion, enrichissement des abstracts manquants
  resume_ia.py         ← fiches de lecture IA (API compatible OpenAI, plusieurs modèles de secours)
  site.py              ← page web + flux RSS (data.json léger, archive.json, details/ : voir ci-dessous)
web/                   ← interface (HTML/CSS/JS, sans dépendance)
data/articles.json     ← la base, versionnée par GitHub (historique gratuit)
.github/workflows/     ← l'automatisation quotidienne
```

**Fichiers du site** (pour une ouverture rapide sur téléphone) : `data.json` ne contient que les articles des 30 derniers jours, sans abstracts ni champs vides. `archive.json` (les plus anciens) se charge juste après l'affichage. Les abstracts et les auteurs sont rangés par paquets dans `details/` et se chargent à l'ouverture de « Détails », pour une recherche ou pour l'export Zotero. Réglages dans la section `site` de `config.yaml`.

**Tests** : `python -m unittest discover tests`. Les tests du site (`tests/test_site.py`) ouvrent l'appli dans un vrai navigateur ; ils sont sautés si Playwright n'est pas installé (`pip install playwright` puis `python -m playwright install chromium`). GitHub les lance à chaque changement de code et ne publie rien s'ils échouent.

Pour ajouter une source, créez `veille/sources/ma_source.py` avec une fonction `collecter(cfg, http, theme, depuis, jusqu_a)` qui renvoie des articles, puis déclarez-la dans `SOURCES_API` (fichier `pipeline.py`).

## Bon à savoir
- **Dépôt public** : vos mots-clés et la liste des articles sont visibles. Vos lus et favoris restent dans votre navigateur et ne sont jamais publiés.
- **Pas d'abstract** : certains flux RSS n'en fournissent pas. L'outil essaie alors de le récupérer via Europe PMC. À défaut, l'article est affiché sans fiche.
- **Partager l'outil** : chacun peut copier ce dépôt (**Fork** ou **Use this template**), y mettre ses propres thèmes et sa propre clé, et tout reste gratuit pour tout le monde.

Licence MIT.
