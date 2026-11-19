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
- **Ordre des fiches IA** : `ia.themes_prioritaires` et `ia.priorite_jours_recents`. Les articles du jour passent d'abord, puis les plus pertinents, les études animales en dernier.
- **E-mail de contact** (demandé poliment par PubMed et OpenAlex) : mettez-le dans le secret `CONTACT_EMAIL` plutôt que dans `config.yaml`, pour qu'il ne soit pas public.

**Dans l'appli elle-même** (Filtres → Personnaliser), chaque lecteur peut, pour lui seul : donner un raccourci à chaque puce (« Anx »), masquer les puces qu'il n'utilise pas, et exporter/importer ses lus, favoris et réglages pour passer d'un appareil à l'autre.
- **Revues** : ajoutez une ligne `nom` + `url` dans `sources.rss.flux`. Pour trouver l'URL, cherchez l'icône RSS sur le site de la revue.
- **Flux non filtrés** (blogs, actualités) : utilisez `sources.rss.flux_libres`.
- **Profil du lecteur** : `ia.profil_lecteur` sert à noter la pertinence pour vous.

Une modification de `config.yaml` régénère la page tout de suite. Les nouveaux thèmes sont collectés au passage suivant, ou immédiatement si vous relancez à la main avec **Run workflow**.

## Changer de fournisseur IA

Le code accepte n'importe quelle API « compatible OpenAI ». Il suffit de modifier `ia.base_url` et `ia.modeles`, puis de mettre la clé correspondante dans le secret `LLM_API_KEY`.

| Fournisseur | `base_url` | Remarque |
|---|---|---|
| OpenRouter (défaut) | `https://openrouter.ai/api/v1` | Modèles `:free` ou `openrouter/free`. 50 requêtes/jour, ou 1 000/jour après un achat unique de 10 $ de crédits. |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | Clé gratuite sur aistudio.google.com. Indiquez le nom de modèle affiché dans AI Studio. |
| Groq | `https://api.groq.com/openai/v1` | Offre gratuite avec des quotas quotidiens. |
| Ollama (local) | `http://localhost:11434/v1` | Uniquement si vous lancez l'outil sur votre propre PC. |

Plusieurs abstracts sont envoyés par requête (`articles_par_requete: 5`). Avec 50 requêtes par jour, on obtient jusqu'à environ 200 à 250 fiches quotidiennes. Les articles en surplus sont traités au passage suivant.

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
  site.py              ← page web + flux RSS
web/                   ← interface (HTML/CSS/JS, sans dépendance)
data/articles.json     ← la base, versionnée par GitHub (historique gratuit)
.github/workflows/     ← l'automatisation quotidienne
```

Pour ajouter une source, créez `veille/sources/ma_source.py` avec une fonction `collecter(cfg, http, theme, depuis, jusqu_a)` qui renvoie des articles, puis déclarez-la dans `SOURCES_API` (fichier `pipeline.py`).

## Bon à savoir
- **Dépôt public** : vos mots-clés et la liste des articles sont visibles. Vos lus et favoris restent dans votre navigateur et ne sont jamais publiés.
- **Pas d'abstract** : certains flux RSS n'en fournissent pas. L'outil essaie alors de le récupérer via Europe PMC. À défaut, l'article est affiché sans fiche.
- **Partager l'outil** : chacun peut copier ce dépôt (**Fork** ou **Use this template**), y mettre ses propres thèmes et sa propre clé, et tout reste gratuit pour tout le monde.

Licence MIT.
