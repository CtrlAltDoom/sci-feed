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
- 🔜 Synchronisation automatique téléphone ↔ PC (voir la section 7)
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
| **Gist GitHub secret** | 0 € | Un jeton une fois par appareil | 🔜 **Recommandé** |
| Fichier dans le dépôt | 0 € | Simple | ❌ Le dépôt est public : l'historique de lecture le serait aussi |
| Firebase, Supabase… | 0 € (quotas) | Compte, projet, règles de sécurité | ❌ Trop lourd pour le besoin |
| Google Drive (dossier d'appli) | 0 € | Création d'un « client OAuth » Google | ❌ Configuration pénible, à refaire par chaque utilisateur |
| Lien ou QR code | 0 € | Aucune | ❌ Trop de données (des milliers d'articles lus) |

**Solution retenue : un gist GitHub secret.**
- Chaque utilisateur a déjà un compte GitHub, puisque sa veille y tourne. Un gist est un petit fichier hébergé gratuitement par GitHub. « Secret » veut dire non listé : il est invisible tant qu'on n'a pas son adresse.
- **Mise en place, une fois par appareil :** créer sur GitHub un jeton limité aux gists (Settings → Developer settings → Tokens, permission « Gists » seulement), puis le coller dans Personnaliser → Synchronisation. Ce jeton ne donne accès à rien d'autre : ni au dépôt, ni au compte.
- **Fonctionnement :** à l'ouverture de l'appli, et quelques secondes après chaque changement, l'appli lit le gist, fusionne, puis réécrit. Hors connexion, elle continue normalement et synchronise au retour du réseau.
- **Fusion sans perte :** chaque article lu, favori ou masqué garde la date de son dernier changement. Retirer un favori sur le téléphone le retire donc aussi sur le PC, ce que l'export/import actuel ne sait pas faire (il ne fait qu'ajouter).
- **Volume :** quelques dizaines de Ko, très loin des limites de GitHub.
- **Ce qui reste sur l'appareil :** le jeton (stocké dans le navigateur de l'appareil, jamais publié). Le contenu du gist ne contient que des identifiants d'articles et des réglages d'affichage, rien de personnel.
- **Travail estimé :** environ une demi-journée, essentiellement l'écran de réglage et la fusion par dates.
