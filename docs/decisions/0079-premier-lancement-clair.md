# 0079 — Un premier lancement clair : un onboarding en étapes, « ce qui manque » en tuiles, les résumés facultatifs

Statut : Proposée (2026-11-10, Interface ; onboarding en étapes demandé par l'utilisateur sur maquettes, le même jour ; d'après la revue UX du premier usage ; points 1 à 3 retenus par l'utilisateur pour la v0.39.0, relayés par Pilotage). Précise 0036, 0049, 0051, 0072, 0078 (le lien discret vers Ollama devient la page des résumés) et 0080 (« Tout télécharger » devient « Voir ce qui manque »). S'appuie sur 0080 du Service (une séance attend tout ce qui manque à la chaîne) et 0078 (rédaction facultative), et sur 0077 de Distribution (autorisation du son de l'ordinateur : `coulissesApp.systemAudio`, message `demander-son-ordinateur`, branche `feat/son-ordinateur-autorisation`), toutes à fusionner avant cette branche.

## Contexte
La revue UX d'une installation neuve (dossier de notes de Pilotage, `interface-revue-ux-premier-usage.md`) relève trois blocages pour quelqu'un qui découvre Coulisses :
- La bienvenue ne parle que des modèles d'écoute. Les résumés demandent Ollama, et rien ne le dit. Le Résumé dit « Lancez l'application Ollama » même quand il n'est pas installé.
- Après « Plus tard », le « Télécharger (3,7 Go) » d'une séance ne prend que les modèles de sa langue. Il manque encore la reconnaissance des voix et les outils de calcul, et le traitement échoue ensuite.
- Réglages › Transcription, à neuf, se contredit : « Le français est inclus », puis « Ajouter · 3,7 Go » sur le français. Il affiche aussi sept lignes « Pas installé », dont certaines en double.

L'utilisateur : « il faut que l'usage de celle ci soit facile et claire », « sans surcharger de texte », et Ollama « doit être facultatif ».

## Décision
- **Un onboarding en étapes (précise 0049).** Au premier lancement, la fenêtre de la mise à jour qui attend laisse la place à six étapes, une idée par étape, plus visuelles que textuelles (choisies sur maquettes, « Premier lancement », le 2026-11-10) :
  1. Bienvenue : deux phrases, « Commencer » ou « Plus tard ».
  2. « Ce qu'il faut pour écouter » : une tuile par chose à télécharger, dite par ce à quoi elle sert, avec sa taille ; pas de total.
  3. « Dans quelles langues ? » : une tuile par langue ; le français est inclus ; seul l'ajout de ce qui est coché est compté.
  4. « Prêt à télécharger » : le seul total, une barre de ce qu'il compte, puis « Télécharger », qui vaut confirmation (P1), ou « Plus tard ».
  5. « Téléchargement en cours » : une barre par élément ; « Autoriser » le son de l'ordinateur, dans l'app du Dock (0077 de Distribution).
  6. Les résumés, facultatifs : avec ou sans Ollama, « Installer Ollama » mène à Réglages › Rédaction. Étape omise si Ollama a déjà un modèle.

  « Plus tard » ou la fermeture : l'onboarding revient au lancement suivant, tant que rien n'est encore sur ce Mac ; ensuite, ce qui manque passe par la fenêtre des mises à jour (0049) et « Voir ce qui manque ». À l'étape 5, un téléchargement se suit et s'arrête (0049) : « Arrêter » par ligne, « Reprendre » pour une ligne arrêtée ou en échec ; un départ partiel refusé y est suivi, le refus dit. Une taille que le moteur n'annonce pas (outils de calcul) se dit « selon ce Mac », et le total « au moins ».
- **Une fenêtre garde sa taille** du début à la fin de son parcours (demande de l'utilisateur) : l'onboarding et « Ce qui manque » ont la hauteur de leur étape la plus haute, les boutons en bas ; une tuile a la même hauteur qu'elle propose ou qu'elle suive.
- **Ce qui manque, partout la même fenêtre.** Une séance qui attend et Réglages › Transcription ouvrent la même fenêtre (« Voir ce qui manque ») : une tuile par élément manquant, « Télécharger · taille » (la décision explicite, P1), puis le suivi. Il n'y a plus de bouton « Tout télécharger » dans Réglages : les langues s'y ajoutent une à une. Un modèle abîmé, qu'aucun téléchargement ne reprend, est dit sous le bouton de la page, avec le chemin vers Réglages. Une taille que le moteur n'annonce pas se dit « selon ce Mac », le total « plus de ». Un refus se dit là où l'on a cliqué.
- **Lignes de modèles (précise 0036 et 0051).** Quand tout est là et va bien, hors mode développeur, le traitement tient en une ligne (« prêt · transcription, voix et outils de calcul, taille ») : les langues, au-dessus, disent leurs propres modèles. Sinon, hors mode développeur, les lignes que la fenêtre « Voir ce qui manque » couvre ne s'affichent pas : un modèle qui manque, sans téléchargement passé ni ancien modèle à remplacer, et un outil de calcul qui manque, sans action. Tout le reste garde sa ligne : un échec, une reprise, un modèle abîmé, un remplacement. L'en-tête dit ce qui manque. « Le téléchargement est en cours » ne s'affiche que si tout ce qui manque se télécharge.
- **Langues en cartes (précise 0072).** Une carte compacte par langue sur ce Mac, avec sa taille propre et, en pastilles, les espaces qui l'ont par défaut (« Aucun espace » sinon) ; « Supprimer » seulement sur une langue qu'aucun espace n'a par défaut. Le français est toujours là, « Inclus » tant qu'il n'est pas téléchargé. Dessous, « Ajouter une langue » en tuiles, une fois le français là. Choisi sur maquettes le 2026-11-10 (proposition A, retouchée).
- **Une séance qui attend ce qui manque.** Toute la page le dit, sans bandeau ni « Arrêter le traitement » (resté dans « … ») : une illustration, « Il manque de quoi écouter cette séance », « Voir ce qui manque ». La fenêtre reprend les tuiles de l'onboarding, seulement ce qui manque, et le total sur le bouton (« Télécharger · 4,1 Go ») : pas d'écran de confirmation de plus ; les mêmes tuiles suivent ensuite le téléchargement (« Arrêter », « Reprendre » pour ce qui n'est ni en cours ni fini), y compris en rouvrant la fenêtre après un échec ; la page dit alors « Téléchargement en cours ». Une séance qui attend, quelle qu'en soit la raison, n'affiche plus « Arrêter le traitement » : il reste dans « … ». Choisi sur maquettes le 2026-11-10.
- **Résumé sans Ollama.** Une page complète, pas une erreur : le compte rendu esquissé de l'étape 6 de l'onboarding, « Facultatif », « Pas encore de résumés », « Installer Ollama » (vers Réglages › Rédaction). Ollama sans modèle compte comme absent. Les résumés déjà faits restent lisibles, sans bandeau, avec une ligne discrète qui dit qu'aucun ne peut être rédigé. Choisi sur maquettes le 2026-11-10.

## Conséquences
- La spec (§7.4, §7.12) le décrit.
- Le Service garde une séance en attente tant qu'il manque quoi que ce soit à sa chaîne (0080). Sans cela, une séance repartirait après le seul téléchargement de sa langue.
- La demande d'autorisation du son de l'ordinateur à la bienvenue relève d'un autre ADR (celui de Distribution), et la page la branchera une fois le contrat fusionné.
- Pas encore tranché : la variante B des maquettes (« Premier lancement » : une carte sur l'accueil, sans fenêtre). Elle reste à choisir par l'utilisateur.

## Alternatives écartées
- **Un nouveau champ d'API pour « tout ce qui manque » :** la page le lit déjà dans l'état du moteur, comme la bienvenue. Le Service en offre un depuis (0080), facultatif pour la page.
- **Garder les sept lignes « Pas installé » :** c'est exact, mais illisible pour quelqu'un qui découvre Coulisses.
