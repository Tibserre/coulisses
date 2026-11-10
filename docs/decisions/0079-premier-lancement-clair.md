# 0079 — Un premier lancement clair : écouter (nécessaire), rédiger (facultatif), « Tout télécharger »

Statut : Proposée (2026-11-10, Interface, d'après la revue UX du premier usage ; points 1 à 3 retenus par l'utilisateur pour la v0.39.0, relayés par Pilotage). Précise 0036, 0049 et 0072. S'appuie sur 0080 du Service (une séance attend tout ce qui manque à la chaîne) et 0078 (rédaction facultative), à fusionner avant cette branche.

## Contexte
La revue UX d'une installation neuve (dossier de notes de Pilotage, `interface-revue-ux-premier-usage.md`) relève trois blocages pour quelqu'un qui découvre Coulisses :
- La bienvenue ne parle que des modèles d'écoute. Les résumés demandent Ollama, et rien ne le dit. Le Résumé dit « Lancez l'application Ollama » même quand il n'est pas installé.
- Après « Plus tard », le « Télécharger (3,7 Go) » d'une séance ne prend que les modèles de sa langue. Il manque encore la reconnaissance des voix et les outils de calcul, et le traitement échoue ensuite.
- Réglages › Transcription, à neuf, se contredit : « Le français est inclus », puis « Ajouter · 3,7 Go » sur le français. Il affiche aussi sept lignes « Pas installé », dont certaines en double.

L'utilisateur : « il faut que l'usage de celle ci soit facile et claire », « sans surcharger de texte », et Ollama « doit être facultatif ».

## Décision
- **Bienvenue (précise 0049).** Au premier lancement, la fenêtre dit « Avant votre première séance », à la place de « Une action est attendue de votre part » et de sa phrase. Elle affiche deux lignes :
  - « Écouter vos séances », nécessaire ;
  - « Rédiger des résumés », facultatif, avec Ollama, et un lien « Comment faire » vers Réglages › Rédaction.

  Les deux sorties ne changent pas. « Plus tard » rappelle que « Tout télécharger » reste dans Réglages › Transcription.
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
