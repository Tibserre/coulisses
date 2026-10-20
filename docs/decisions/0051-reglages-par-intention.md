# 0051 — Des Réglages rangés selon ce qu'on vient y faire, sans détail technique hors du mode développeur

Statut : Acceptée (2026-10-20, choix de l'utilisateur parmi trois maquettes : quatre onglets par intention ; modèles d'Ollama dits « Qwen 3.8 – 27b » ; version en ligne discrète dans les mises à jour ; après la relecture : conservation enregistrée en quittant la ligne, suppression d'un modèle nécessaire en mode développeur, cache de uv en mode développeur seulement (choix de l'utilisateur, 2026-10-20, après une première version où il avait sa ligne discrète) ; après son essai dans « Coulisses (dév) » : onglets Séances, Rédaction, Transcription, Avancé, l'historique avec les séances, les copies de la base en mode développeur, « Mettre à jour » dans la colonne). Étape 13b du plan. Précise 0034 (journal du service), 0036 (affichage des modèles du moteur), 0039 (noms des modèles de langage) et 0040 (place des mises à jour).

## Contexte
L'utilisateur, le 2026-10-20 : « l'app est pas hyper claire, notamment les paramètres aujourd'hui qui sont un peu fouillis ». L'audit (13a) relève cinq onglets rangés selon le code : « Données » mêle version, dossiers, mises à jour, journal et sauvegardes ; « Avancé » ne porte qu'un interrupteur. L'onglet des modèles du moteur montre leurs noms bruts, deux lignes « Transcription » et trois « Qui parle quand » indiscernables, le Python et le cache de uv. La liste des modèles d'Ollama est toujours dépliée, avec leurs noms bruts. La version apparaît hors mode développeur, et la conservation demande « Enregistrer ». L'utilisateur veut des pages sobres, sans détail technique hors du mode développeur, des réglages modifiés en place, et rien qui saute au chargement.

## Décision
- **Quatre onglets** : « Séances » (conservation de l'audio, préavis, bientôt supprimés, déjà supprimés, dossier d'export), « Rédaction » (le modèle de chaque rédaction), « Transcription » (ce que le traitement utilise), « Avancé » (mises à jour, dossiers, journal technique, mode développeur). Les anciennes adresses (`general`, `modeles`, `donnees`) mènent au nouvel onglet. Un point sur « Transcription » double celui de « Réglages » quand une mise à jour attend un geste (0049).
- **Ce qui a été supprimé** se lit à côté de ce qui va l'être : une ligne « Déjà supprimés » avec leur nombre, qui ouvre la liste en panneau flottant, les cinq dernières puis le reste sur demande. Les copies de la base ne se montrent qu'en mode développeur (dans Avancé). L'utilisateur a aussi décidé de n'en garder que les trois dernières : cette règle, et ce qu'elle change dans l'ADR 0018, sont écrits par l'ADR 0052.
- **« Mettre à jour »**, en bas de la colonne, n'apparaît que quand l'app du Dock dit qu'une nouvelle version attend un clic ; un clic ouvre la fenêtre de Sparkle, d'où elle s'installe. Contrat avec l'app du Dock (Distribution, 44b3438) :
  - la coquille de la page, toujours montée, annonce le rappel (`rappel-mises-a-jour`, vrai) une fois à son montage, et le retire (faux) en se démontant ; l'annonce est à refaire après chaque rechargement ;
  - seulement alors, une version trouvée par la recherche automatique n'ouvre plus la fenêtre de Sparkle : `updates.ready` passe à vrai et l'évènement `coulisses:mises-a-jour` est envoyé ; sans annonce, Sparkle ouvre sa fenêtre comme avant ;
  - colonne masquée, un point sur son bouton dit qu'une version attend : jamais une version annoncée et vue nulle part. Pendant un enregistrement, ni bouton ni point (0040) ; ils reviennent ensuite. Un clic pendant un traitement est refusé par l'app, en français ;
  - `ready` repasse à faux une fois la fenêtre de Sparkle vue (installée, ignorée, « plus tard »).
  Le réglage (recherche automatique, recherche immédiate, version) est dans Avancé.
- **Le journal technique du service** s'ouvre depuis Avancé, aussi hors mode développeur (demande de l'utilisateur ; précise 0034).
- **Un réglage, une ligne** : ce qu'il est à gauche, sa valeur et ce qui la change à droite. La conservation et le préavis valent dès qu'on quitte la ligne, l'onglet ou la page, sans « Enregistrer » : une écriture par décision, car chacune annonce de nouveau les purges proches (notification macOS). « Bientôt supprimés » a toujours sa ligne (« Aucun »). Le dossier d'export se dit par son nom.
- **Hors mode développeur**, aucun chemin, nom brut de modèle ni version de composant :
  - modèles du moteur : ce qui sert et va bien tient en une ligne par étape, plus une ligne « Outils de calcul » (environnements et leur Python) ; rien qui prend de la place n'est caché, avec une exception voulue par l'utilisateur : le cache de uv, ni compté dans le total ni montré hors mode développeur. Ses fichiers sont en partie partagés avec les outils de calcul (clones APFS), mais il peut aussi garder des paquets d'anciens environnements : cette place ne se voit alors qu'en mode développeur ; un modèle que le traitement n'utilise pas ne se montre pas s'il n'est pas sur le disque (demande de l'utilisateur : « on montre que le nouveau ») : télécharger un facultatif se fait alors en mode développeur, en recul sur 0036 ; un modèle remplacé et installé se dit sous son étape avec « Supprimer l'ancien », ou « Remplacer… » quand le nouveau manque, qui ouvre la fenêtre de 0049 sur ce remplacement, même déjà repoussé ; un facultatif installé garde sa ligne ; tout autre élément garde sa ligne et son action. Supprimer un modèle nécessaire au traitement se fait en mode développeur, qui montre tout comme avant (noms, chemins, Python, cache) ;
  - modèles d'Ollama : famille, version et taille lues dans leur nom (« Qwen 3.8 – 27b »), sans liste dans le code (P6). Deux qui se liraient pareil gardent la suite de leur étiquette, ou leur nom exact. La liste des installés est repliée en une ligne ;
  - la version de Coulisses reste une ligne discrète sous les mises à jour, y compris dans l'app de développement, qui dit n'en chercher aucune ;
  - les erreurs d'étape disent ce qui manque par ce à quoi il sert et renvoient à « Transcription ».
- **Sélecteur de modèle sans cadre** : le nom et son chevron, un fond léger au survol ; la liste flotte, accrochée au nom.
- **Squelettes** aux dimensions des listes (modèles, journal, copies, dossier) : rien ne saute au chargement.

## Conséquences
- La provenance et les détails restent accessibles en mode développeur (P7) ; rien n'est retiré du disque ni du service.
- Lire un nom d'Ollama est une heuristique : un nom inattendu reste lisible, au pire tel quel.
- Le message de `prompting/ollama.py` (« Réglages > Rédaction ») reste juste. Les autres conversations qui citent l'onglet « Données » doivent dire « Avancé » ; « Transcription » ne change pas de nom.
- « Mettre à jour » se vérifie sur une pré-version : recherche automatique, bouton sans fenêtre ; clic, fenêtre de Sparkle ; « Plus tard », bouton retiré ; clic pendant un enregistrement, refus.
- Le reste de l'étape 13 se revoit par parcours complets, plus écran par écran (demande de l'utilisateur).

## Alternatives écartées
- Une seule page avec un sommaire : plus longue à parcourir pour un réglage isolé.
- Une liste de lignes qui se déplient : la plus sobre, mais déplier pousse les lignes du dessous.
- Un onglet « Ce Mac » qui réunit modèles, mises à jour, dossiers et mode développeur, et un onglet « Historique » : essayés dans l'app de dév, jugés peu clairs par l'utilisateur.
- L'historique en mode développeur seulement : ce qui a été supprimé doit rester lisible.
- Conservation enregistrée à chaque pause des clics : une hésitation ferait une notification par valeur intermédiaire.
- Noms d'Ollama tels quels : techniques ; l'utilisateur préfère « Qwen 3.8 – 27b ».
- Version en mode développeur seulement : utile quand un ami demande laquelle il a.
