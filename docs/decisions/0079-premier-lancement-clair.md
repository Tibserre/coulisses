# 0079 — Un premier lancement clair : écouter (nécessaire), rédiger (facultatif), « Tout télécharger »

Statut : Proposée (2026-11-10, Interface ; onboarding en étapes demandé par l'utilisateur sur maquettes, le même jour ; d'après la revue UX du premier usage ; points 1 à 3 retenus par l'utilisateur pour la v0.39.0, relayés par Pilotage). Précise 0036, 0049 et 0072. S'appuie sur 0080 du Service (une séance attend tout ce qui manque à la chaîne) et 0078 (rédaction facultative), et sur 0077 de Distribution (autorisation du son de l'ordinateur : `coulissesApp.systemAudio`, message `demander-son-ordinateur`, branche `feat/son-ordinateur-autorisation`), toutes à fusionner avant cette branche.

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

  « Plus tard » ou la fermeture : l'onboarding revient au lancement suivant, tant que rien n'est encore sur ce Mac ; ensuite, ce qui manque passe par la fenêtre des mises à jour (0049) et « Tout télécharger ». À l'étape 5, un téléchargement se suit et s'arrête (0049) : « Arrêter » par ligne, « Reprendre » pour une ligne arrêtée ou en échec ; un départ partiel refusé y est suivi, le refus dit. Une taille que le moteur n'annonce pas (outils de calcul) se dit « selon ce Mac », et le total « au moins ».
- **« Tout télécharger ».** Il prend tout ce qui manque au traitement : les modèles et les outils de calcul que nomme l'état du moteur, plus les modèles de la langue d'une séance qui attend. C'est toujours confirmé, et la taille est dite d'avance (« plus de » quand des outils de calcul s'y ajoutent).
  - Sur une séance qui attend plus que les modèles de sa langue, il s'affiche sous « Coulisses n'est pas encore prêt à écouter cette séance ».
  - En tête de Réglages › Transcription, il s'affiche sous « Coulisses n'est pas encore prêt à écouter vos séances », avec ce qui manque en une ligne.
  - Un refus se dit là où l'on a cliqué, même si le bouton a disparu entre-temps.
- **Lignes de modèles (précise 0036).** Hors mode développeur, les lignes que « Tout télécharger » couvre ne s'affichent pas : un modèle qui manque, sans téléchargement passé ni ancien modèle à remplacer, et un outil de calcul qui manque, sans action. Tout le reste garde sa ligne : un échec, une reprise, un modèle abîmé, un remplacement. L'en-tête dit ce qui manque. « Le téléchargement est en cours » ne s'affiche que si tout ce qui manque se télécharge.
- **Langues, sur une installation neuve (précise 0072).** Le français dit « Inclus », sans bouton. Les autres langues n'ont pas de bouton avant « Tout télécharger », et la section le dit en une phrase. Ensuite, chacune retrouve son « Ajouter ».
- **Résumé sans Ollama.** Un bandeau d'information, pas d'avertissement : « Les résumés demandent Ollama ». Il dit que les résumés sont facultatifs et renvoie à Réglages › Rédaction.

## Conséquences
- La spec (§7.4, §7.12) le décrit.
- Le Service garde une séance en attente tant qu'il manque quoi que ce soit à sa chaîne (0080). Sans cela, une séance repartirait après le seul téléchargement de sa langue.
- La demande d'autorisation du son de l'ordinateur à la bienvenue relève d'un autre ADR (celui de Distribution), et la page la branchera une fois le contrat fusionné.
- Pas encore tranché : la variante B des maquettes (« Premier lancement » : une carte sur l'accueil, sans fenêtre). Elle reste à choisir par l'utilisateur.

## Alternatives écartées
- **Un nouveau champ d'API pour « tout ce qui manque » :** la page le lit déjà dans l'état du moteur, comme la bienvenue. Le Service en offre un depuis (0080), facultatif pour la page.
- **Garder les sept lignes « Pas installé » :** c'est exact, mais illisible pour quelqu'un qui découvre Coulisses.
