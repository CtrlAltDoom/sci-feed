# Feuille de route

Principe directeur : **le code est commun, le profil est personnel.** Tout ce qui est propre à une personne vit dans `config.yaml` (ce que la veille collecte et comment elle le range) ou dans le navigateur du lecteur (raccourcis, puces masquées, lus, favoris), jamais dans le code. C'est ce qui permet d'adapter l'outil à d'autres usages sans changer ce qu'il est.

Légende : ✅ fait · 🔜 prochaine étape · 💡 idée à évaluer · ❌ écarté

Deuxième principe : **résilient avant d'être riche.** Une fonction ne s'ajoute que si elle est gratuite, ne demande pas d'entretien, et qu'une panne de sa part ne bloque rien d'autre (repli silencieux, alerte de santé si besoin).

---

## Prochaines priorités (mises à jour le 19 novembre 2026)

Dans l'ordre, du plus utile au moins urgent :
1. ✅ **Ne jamais perdre un favori** : la purge des articles de plus de 180 jours garde les favoris (lus dans le gist). Si le gist est illisible ce jour-là, la purge attend le lendemain.
2. ✅ **Versions des bibliothèques Python bornées** : jamais de nouvelle version majeure installée d'elle-même.
3. ✅ **Tests du site dans un vrai navigateur** à chaque changement de code, avant publication (pas pour la veille du matin, où le code ne change pas).
4. ✅ **Repère « nouveaux depuis ma dernière visite »** (badge, raccourci, vue dédiée).
5. ✅ **Rattrapage des fiches IA** du stock initial : automatique chaque soir tant qu'il reste du retard (voir la section 2).
6. **Apprendre des « Pas intéressé »** (voir la section 3).

---

## 1. Fiabilité et maintenance
- ✅ Actions GitHub à jour (Node.js 24)
- ✅ Alerte dans l'appli si la veille n'a pas été mise à jour depuis 48 h
- ✅ Dédoublonnage des articles sans identifiant et au titre court (l'adresse sert de clé)
- ✅ Alertes de santé sur ntfy : source en panne plusieurs jours, IA muette, collecte vide, tâche quotidienne arrêtée ou en échec (puis « ✅ » quand c'est réparé)
- ✅ Modèles IA de secours trouvés automatiquement si le modèle gratuit configuré disparaît
- ✅ `data.json` allégé (4,3 Mo → 1,4 Mo) : articles des 30 derniers jours sans abstracts, archive chargée juste après, abstracts à l'ouverture de « Détails » ou pour une recherche
- ✅ Tests de la partie site dans un vrai navigateur (liste, détails, recherche dans les abstracts, filtres, favoris, hors connexion), lancés à chaque changement de code ; s'ils échouent, rien n'est publié et une alerte part
- ✅ Tâches planifiées protégées de la mise en veille de GitHub (dépôt « inactif » 60 jours) : la collecte enregistre la base chaque jour, et une alerte part si elle ne tourne plus depuis 36 h
- ✅ Un article mis en favori n'est jamais effacé de la base (lecture du gist ; purge reportée si le gist est illisible)
- ✅ Bornes de versions dans `requirements.txt` (une mise à jour majeure d'une bibliothèque ne peut plus casser la collecte d'elle-même)
- ✅ Taille du dépôt surveillée : alerte de santé au-delà de 500 Mo (`sante.depot_max_mo`). Ce jour-là, découper `data/articles.json` par mois

## 2. Fiches IA
- ✅ Ordre de passage : articles du jour d'abord, puis les plus pertinents (thèmes prioritaires, étiquettes), études animales en dernier
- ✅ Rattrapage du stock initial : chaque après-midi à 14 h 17 (15 h 17 en été), 40 min de fiches seulement (sans collecte ni notification), tant qu'il reste des articles sans fiche ; s'arrête tout seul (`ia.rattrapage.auto: false` pour le couper)
- 💡 Laisser l'IA proposer des étiquettes, en complément des mots-clés

## 3. Étiquettes et tri
- ✅ Tri « Pour moi » par défaut : récence et intérêt dans un même score (mots-clés plafonnés, pertinence IA, sérieux de la revue)
- ✅ Type, domaine et notoriété des revues (OpenAlex), filtre « Revue établie / de référence », repérage des méga-revues
- 💡 Signaler l'indexation MEDLINE (PubMed) comme repère de sérieux supplémentaire
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
- ✅ Notifications du matin via ntfy : les 5 articles les plus pertinents, titre court et conclusion simple rédigés par l'IA, en priorité haute (bandeau)
- ✅ Notifications fiables malgré les retards de GitHub : collecte la nuit, toutes les heures à partir de 1 h 23 en hiver (2 h 23 en été ; les suivants s'arrêtent si elle est faite), notifications dès 6 h, essais toutes les 20 min jusqu'à 8 h 40 en hiver (9 h 40 en été), enchaînées dès la fin de la collecte, puis filet toutes les heures ; attente de la collecte jusqu'à midi, envoi accepté jusqu'à 21 h ; le rattrapage du soir laisse les modèles Gemini à petit quota à la collecte de la nuit
- 💡 Réveil externe par cron-job.org (workflow lancé avec `si_pas_fait`) si les créneaux GitHub ne suffisent pas
- ✅ Pas de notification pour ce qui est déjà lu, favori ou masqué dans l'appli (secret `SYNC_GIST_ID`)
- ✅ Résumé de la semaine le dimanche (les 10 articles marquants des 7 derniers jours, en une notification, sans IA ni bandeau)
- 💡 Notifications de l'appli elle-même (Web Push), sans appli tierce
- ✅ Appli installable (Android, iPhone, PC) avec icône, consultable hors connexion
- ✅ Repère « nouveaux depuis ma dernière visite » : badge « Nouveau », raccourci « N nouveaux depuis ta dernière visite », vue dédiée dans les filtres. Propre à chaque appareil ; une visite qui suit de moins de 3 h garde les mêmes « nouveaux »
- 💡 Notes personnelles sur un article, reprises dans l'export Zotero
- ✅ Lien vers le texte intégral gratuit plus souvent trouvé (Unpaywall, revérifié tous les 30 jours)
- ✅ Lien « Chercher une version » vers Google Scholar (recherche par titre), affiché quand aucun texte libre n'est connu : aucun appel automatique, rien à entretenir
- 💡 Lier un preprint à sa version publiée
- ✅ Alerte si un favori est rétracté (revérifié chaque jour via OpenAlex / Retraction Watch, notification ntfy et badge « RÉTRACTÉ »)

## 6. Partage de l'outil
- ✅ E-mail de contact hors du dépôt public (secret `CONTACT_EMAIL`)
- ✅ README : étiquettes, priorité IA, personnalisation, installation de l'appli
- 🔜 Guide « créer sa propre veille en 15 minutes » pour un collègue (copie du dépôt, `config.yaml`, secrets)
- 💡 Modèle de `config.yaml` vierge et commenté, à côté de celui-ci

## 6 bis. Appli Android

- ✅ L'appli s'installe déjà depuis le navigateur (Android, iPhone, PC), avec icône et hors connexion.
- 💡 Fichier APK (via PWABuilder ou Bubblewrap, gratuits) : surtout utile pour la publier sur un magasin d'applis ou la donner à quelqu'un sans passer par le navigateur. Pour un usage personnel, la version installée depuis le navigateur fait déjà la même chose ; à ne faire que si ce besoin apparaît.
- 💡 Notifications de l'appli elle-même (Web Push) à la place de ntfy : à évaluer seulement si ntfy pose problème.

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
- ✅ **Plus de textes intégraux gratuits et légaux** via Unpaywall (voir la section 5), qui réduit le besoin d'abonnement.

**Ce que l'on sait de l'AP-HP (novembre 2026) :** accès distant par **OpenAthens** ; portail **EBSCO Discovery Service** (EDS) ; bases annoncées : Cochrane Library, Embase, ProQuest, Drugdex, Thériaque ; environ 10 000 revues (Elsevier Freedom Collection, Springer-Nature, Wiley, Ovid…). Abonnements PsycINFO, PsycArticles ou Cairn non confirmés.
- 🔜 Renseigner le bon domaine OpenAthens AP-HP dans Personnaliser (`aphp.fr` est une supposition à vérifier avec le lien « Tester »).
- 💡 Alertes RSS d'une recherche enregistrée dans EDS (EBSCO propose des alertes par flux RSS), à ajouter dans `config.yaml` si PsycINFO ou Embase y sont interrogeables.

**À vérifier auprès de la bibliothèque AP-HP :**
- l'adresse de son proxy, s'il y en a un (accès distant aux ressources électroniques) ;
- les plateformes par lesquelles elle donne accès aux bases (Ovid, EBSCO, ScienceDirect…) ;
- si ces plateformes proposent des alertes RSS.

---

## 9. Textes intégraux : quelles sources ?

**Déjà en place (gratuit, légal, stable) :** OpenAlex (meilleure version en accès libre), PubMed Central, Europe PMC, Unpaywall. Ensemble, ils couvrent l'essentiel de ce qui est légalement disponible : archives ouvertes, versions auteur, revues en accès libre.

| Piste | Coût | Risque de casse | Verdict |
|---|---|---|---|
| Lien « Chercher une version » vers Google Scholar | 0 € | Nul (simple lien, rien d'automatique) | ✅ Fait |
| Semantic Scholar (`openAccessPdf`) | 0 € (sans clé, quota limité) | Faible, avec repli silencieux | ❌ Mesuré le 19/11/2026 : **0 PDF sur 50** articles sans version libre. Rien à gagner |
| CORE (archives ouvertes du monde entier) | 0 € (clé gratuite) | Une clé de plus à gérer | ❌ Mesuré le 19/11/2026 : **0 PDF sur 50**, et 12 refus sans clé. Rien à gagner |
| Version preprint d'un article publié (PsyArXiv, medRxiv) | 0 € | Faible | 💡 Déjà prévu (« lier un preprint à sa version publiée ») |
| **Sci-Hub** | 0 € | **Élevé** | ❌ **Écarté** |

**Pourquoi pas Sci-Hub :**
- **Juridique :** le site diffuse des articles sans l'accord des éditeurs. Il est bloqué en France par décision de justice. Un lien automatique dans un dépôt public pourrait entraîner une demande de retrait du dépôt par GitHub, et donc l'arrêt de toute la veille.
- **Stabilité :** les adresses changent souvent, des miroirs disparaissent ou deviennent douteux (publicités, faux sites). Il faudrait les surveiller en permanence, l'inverse de ce qu'on cherche.
- **Utilité :** Sci-Hub n'ajoute presque plus d'articles depuis 2021 ; pour une veille sur les nouveautés, il manquerait justement les articles récents.
- **Partage de l'outil :** un collègue qui copie le dépôt hériterait de ce lien sans l'avoir choisi.

Pour un article introuvable légalement : le lien institutionnel (section 8), puis l'e-mail à l'auteur correspondant, qui envoie presque toujours son PDF.

