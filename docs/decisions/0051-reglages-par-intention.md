# 0051 — Des Réglages rangés selon ce qu'on vient y faire, sans détail technique hors du mode développeur

Statut : Acceptée (2026-10-20, choix de l'utilisateur parmi trois maquettes : quatre onglets par intention ; modèles d'Ollama dits « Qwen 3.8 – 27b » ; version en ligne discrète dans les mises à jour ; après la relecture : conservation enregistrée en quittant la ligne, suppression d'un modèle nécessaire en mode développeur, ligne discrète pour le cache de uv). Étape 13b du plan. Précise 0036 (affichage des modèles du moteur), 0039 (noms des modèles de langage) et 0040 (place des mises à jour).

## Contexte
L'utilisateur, le 2026-10-20 : « l'app est pas hyper claire, notamment les paramètres aujourd'hui qui sont un peu fouillis ». L'audit (13a) relève cinq onglets rangés selon le code : « Données » mêle version, dossiers, mises à jour, journal et sauvegardes ; « Avancé » ne porte qu'un interrupteur. L'onglet des modèles du moteur montre leurs noms bruts, deux lignes « Transcription » et trois « Qui parle quand » indiscernables, le Python et le cache de uv. La liste des modèles d'Ollama est toujours dépliée, avec leurs noms bruts. La version apparaît hors mode développeur, et la conservation demande « Enregistrer ». L'utilisateur veut des pages sobres, sans détail technique hors du mode développeur, des réglages modifiés en place, et rien qui saute au chargement.

## Décision
- **Quatre onglets** : « Séances » (conservation de l'audio, préavis, bientôt supprimés, dossier d'export), « Rédaction » (le modèle de chaque rédaction), « Ce Mac » (ce que le traitement utilise, mises à jour, dossiers, mode développeur), « Historique » (journal des suppressions, copies de la base). Les anciennes adresses (`general`, `modeles`, `donnees`, `avance`) mènent au nouvel onglet. Un point sur « Ce Mac » double celui de « Réglages » quand une mise à jour attend un geste (0049).
- **Un réglage, une ligne** : ce qu'il est à gauche, sa valeur et ce qui la change à droite. La conservation et le préavis valent dès qu'on quitte la ligne, l'onglet ou la page, sans « Enregistrer » : une écriture par décision, car chacune annonce de nouveau les purges proches (notification macOS). « Bientôt supprimés » a toujours sa ligne (« Aucun »). Le dossier d'export se dit par son nom.
- **Hors mode développeur**, aucun chemin, nom brut de modèle ni version de composant :
  - modèles du moteur : ce qui sert et va bien tient en une ligne par étape, plus une ligne « Outils de calcul » (environnements et leur Python) et une ligne discrète « Fichiers gardés pour réinstaller » (le cache de uv, hors du total) : rien qui prend de la place n'est caché ; tout autre élément garde sa ligne et son action. Supprimer un modèle nécessaire au traitement se fait en mode développeur, qui montre tout comme avant (noms, chemins, Python, cache) ;
  - modèles d'Ollama : famille, version et taille lues dans leur nom (« Qwen 3.8 – 27b »), sans liste dans le code (P6). Deux qui se liraient pareil gardent la suite de leur étiquette, ou leur nom exact. La liste des installés est repliée en une ligne ;
  - la version de Coulisses reste une ligne discrète sous les mises à jour, y compris dans l'app de développement, qui dit n'en chercher aucune ;
  - les erreurs d'étape disent ce qui manque par ce à quoi il sert et renvoient à « Ce Mac ».
- **Sélecteur de modèle sans cadre** : le nom et son chevron, un fond léger au survol ; la liste flotte, accrochée au nom.
- **Squelettes** aux dimensions des listes (modèles, journal, copies, dossier) : rien ne saute au chargement.

## Conséquences
- La provenance et les détails restent accessibles en mode développeur (P7) ; rien n'est retiré du disque ni du service.
- Lire un nom d'Ollama est une heuristique : un nom inattendu reste lisible, au pire tel quel.
- Le message de `prompting/ollama.py` (« Réglages > Rédaction ») reste juste. Les autres conversations qui citent « onglet Transcription » ou « Données » doivent dire « Ce Mac ».
- Le reste de l'étape 13 se revoit par parcours complets, plus écran par écran (demande de l'utilisateur).

## Alternatives écartées
- Une seule page avec un sommaire : plus longue à parcourir pour un réglage isolé.
- Une liste de lignes qui se déplient : la plus sobre, mais déplier pousse les lignes du dessous.
- Conservation enregistrée à chaque pause des clics : une hésitation ferait une notification par valeur intermédiaire.
- Noms d'Ollama tels quels : techniques ; l'utilisateur préfère « Qwen 3.8 – 27b ».
- Version en mode développeur seulement : utile quand un ami demande laquelle il a.
