# Feuille de route

Principe directeur : **le code est commun, le profil est personnel.** Tout ce qui est propre à une personne vit dans `config.yaml` (ce que la veille collecte et comment elle le range) ou dans le navigateur du lecteur (raccourcis, puces masquées, lus, favoris), jamais dans le code. C'est ce qui permet d'adapter l'outil à d'autres usages sans changer ce qu'il est.

Légende : ✅ fait · 🔜 prochaine étape · 💡 idée à évaluer

---

## 1. Fiabilité et maintenance
- ✅ Actions GitHub à jour (Node.js 24)
- ✅ Alerte dans l'appli si la veille n'a pas été mise à jour depuis 48 h
- ✅ Dédoublonnage des articles sans identifiant et au titre court (l'adresse sert de clé)
- 🔜 Tests de la partie site (filtres, étiquettes, personnalisation), pas seulement de la collecte
- 🔜 Alléger `data.json` (environ 4 Mo et en hausse) : articles récents d'abord, le reste à la demande
- 💡 Résumé hebdomadaire de santé de la veille : sources en échec, nombre de fiches, file d'attente IA

## 2. Fiches IA
- ✅ Ordre de passage : articles du jour d'abord, puis les plus pertinents (thèmes prioritaires, étiquettes), études animales en dernier
- 🔜 Rattrapage du stock initial (environ 1 200 articles) : patienter environ 3 semaines, ou acheter une fois 10 $ de crédits OpenRouter (1 000 requêtes/jour au lieu de 50)
- 💡 Laisser l'IA proposer des étiquettes, en complément des mots-clés

## 3. Étiquettes et tri
- ✅ 11 étiquettes colorées, tirées du dictionnaire de requêtes « Veille SII & psychologie »
- ✅ Études animales gardées et signalées en rouge, avec des règles pour éviter les fausses alertes (revues)
- ✅ Puces sur 2 lignes défilantes, panneau « Tout afficher » rangé par famille, noms courts
- ✅ Flux RSS par étiquette
- ✅ Contraste des couleurs vérifié (WCAG AA, modes clair et sombre)
- 🔜 Apprendre des « Pas intéressé » : repérer les mots fréquents des articles masqués et proposer des exclusions ou des étiquettes plus strictes
- 💡 Repérer les études animales avec l'indexation PubMed (MeSH « Animals » sans « Humans »)

## 4. Personnalisation (par appareil, jamais imposée)
- ✅ Raccourcis personnels des puces (« Anx »), puces masquées, retour aux valeurs par défaut
- ✅ Export / import des lus, favoris, masqués et réglages (fusion, rien n'est effacé)
- ✅ Synchronisation automatique téléphone ↔ PC par gist GitHub secret (voir la section 7)
- 💡 Ordre des puces au choix ; vue de démarrage au choix

## 5. Lecture et usage
- ✅ Appli installable (Android, iPhone, PC) avec icône, consultable hors connexion
- 🔜 Repère « nouveaux depuis ma dernière visite »
- 💡 Notes personnelles sur un article, reprises dans l'export Zotero
- 💡 Lien vers le texte intégral gratuit plus souvent trouvé (Unpaywall)
- 💡 Lier un preprint à sa version publiée
- 💡 Alerte si un favori est rétracté

## 6. Partage de l'outil
- ✅ E-mail de contact hors du dépôt public (secret `CONTACT_EMAIL`)
- ✅ README : étiquettes, priorité IA, personnalisation, installation de l'appli
- 🔜 Guide « créer sa propre veille en 15 minutes » pour un collègue (copie du dépôt, `config.yaml`, secrets)
- 💡 Modèle de `config.yaml` vierge et commenté, à côté de celui-ci

---

## 7. Synchroniser le téléphone et le PC, sans coût

**Besoin :** retrouver ses lus, favoris, masqués et raccourcis sur tous ses appareils, gratuitement, sans serveur à maintenir, et de façon que chaque utilisateur d'une copie de l'outil ait sa propre synchronisation.

**Options étudiées :**

| Option | Coût | Mise en place | Verdict |
|---|---|---|---|
| Export / import d'un fichier | 0 € | Aucune | ✅ Fait : solution de secours, mais manuelle |
| **Gist GitHub secret** | 0 € | Un jeton une fois par appareil | ✅ **Fait** |
| Fichier dans le dépôt | 0 € | Simple | ❌ Le dépôt est public : l'historique de lecture le serait aussi |
| Firebase, Supabase… | 0 € (quotas) | Compte, projet, règles de sécurité | ❌ Trop lourd pour le besoin |
| Google Drive (dossier d'appli) | 0 € | Création d'un « client OAuth » Google | ❌ Configuration pénible, à refaire par chaque utilisateur |
| Lien ou QR code | 0 € | Aucune | ❌ Trop de données (des milliers d'articles lus) |

**Solution retenue et en place : un gist GitHub secret** (Personnaliser → Synchronisation entre appareils).
- Chaque utilisateur a déjà un compte GitHub, puisque sa veille y tourne. Un gist est un petit fichier hébergé gratuitement par GitHub. « Secret » veut dire non listé : il est invisible tant qu'on n'a pas son adresse.
- **Mise en place, une fois par appareil :** créer sur GitHub un jeton limité aux gists (Settings → Developer settings → Tokens, permission « Gists » seulement), puis le coller dans Personnaliser → Synchronisation. Ce jeton ne donne accès à rien d'autre : ni au dépôt, ni au compte.
- **Fonctionnement :** à l'ouverture de l'appli, et quelques secondes après chaque changement, l'appli lit le gist, fusionne, puis réécrit. Hors connexion, elle continue normalement et synchronise au retour du réseau.
- **Fusion sans perte :** chaque article lu, favori ou masqué garde la date de son dernier changement. Retirer un favori sur le téléphone le retire donc aussi sur le PC, ce que l'export/import actuel ne sait pas faire (il ne fait qu'ajouter).
- **Volume :** quelques dizaines de Ko, très loin des limites de GitHub.
- **Ce qui reste sur l'appareil :** le jeton (stocké dans le navigateur de l'appareil, jamais publié). Le contenu du gist ne contient que des identifiants d'articles et des réglages d'affichage, rien de personnel.
- **Travail estimé :** environ une demi-journée, essentiellement l'écran de réglage et la fusion par dates.

---

## 8. Accès institutionnels (AP-HP, Elsevier, PsycINFO…)

**Deux besoins à distinguer :**
- **Trouver les articles.** C'est déjà largement couvert : PubMed, Europe PMC et OpenAlex indexent aussi les revues Elsevier, Wiley, etc. (titres, abstracts). Les bases payantes ajouteraient surtout **PsycINFO** (psychologie, beaucoup de revues absentes de PubMed) et, dans une moindre mesure, Embase ou Scopus.
- **Lire le texte intégral.** C'est là que l'abonnement de l'AP-HP sert vraiment.

**À écarter : mettre ses identifiants AP-HP dans GitHub pour que le robot aille chercher les articles.** Les licences des éditeurs interdisent le téléchargement automatisé et le partage d'identifiants. On risque la suspension de l'accès, voire de celui de l'établissement. Et le site étant public, les contenus sous licence s'y retrouveraient.

**Pistes gratuites et conformes :**
- ✅ **Lien « Texte intégral via mon établissement ».** Un réglage par appareil, dans Personnaliser : on y colle le préfixe du proxy de sa bibliothèque (du type `https://proxy.exemple.fr/login?url=`). Chaque fiche affiche alors un lien qui ouvre l'article à travers ce proxy. On s'identifie soi-même, dans son navigateur, comme d'habitude. Rien ne passe par GitHub, rien n'est publié, et chaque utilisateur met le préfixe de son propre établissement. Travail estimé : environ une heure.
- 💡 **Alertes PsycINFO (ou Embase) en flux RSS.** Si l'AP-HP donne accès à PsycINFO via une plateforme comme Ovid, EBSCO ou APA PsycNet, on peut y enregistrer une recherche et demander une alerte RSS. L'adresse de ce flux s'ajoute dans `config.yaml` comme une revue, sans aucun code. Point à vérifier avant : le site étant public, il faut peut-être n'en garder que les titres et les liens, sans les abstracts (licence).
- 💡 **Plus de textes intégraux gratuits et légaux** via Unpaywall (voir la section 5), qui réduit le besoin d'abonnement.

**Ce que l'on sait de l'AP-HP (novembre 2026) :** accès distant par **OpenAthens** ; portail **EBSCO Discovery Service** (EDS) ; bases annoncées : Cochrane Library, Embase, ProQuest, Drugdex, Thériaque ; environ 10 000 revues (Elsevier Freedom Collection, Springer-Nature, Wiley, Ovid…). Abonnements PsycINFO, PsycArticles ou Cairn non confirmés.
- 🔜 Renseigner le bon domaine OpenAthens AP-HP dans Personnaliser (`aphp.fr` est une supposition à vérifier avec le lien « Tester »).
- 💡 Alertes RSS d'une recherche enregistrée dans EDS (EBSCO propose des alertes par flux RSS), à ajouter dans `config.yaml` si PsycINFO ou Embase y sont interrogeables.

**À vérifier auprès de la bibliothèque AP-HP :**
- l'adresse de son proxy, s'il y en a un (accès distant aux ressources électroniques) ;
- les plateformes par lesquelles elle donne accès aux bases (Ovid, EBSCO, ScienceDirect…) ;
- si ces plateformes proposent des alertes RSS.
