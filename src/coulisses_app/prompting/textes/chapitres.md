Découpe la séance en chapitres qui se suivent, de la première réplique à la dernière, sans trou ni chevauchement.

Un chapitre est un moment cohérent de la séance, d'un de ces trois types :
- `scene` : un moment où l'on joue (improvisation, scène, exercice en plateau). Les répliques sont celles de personnages : fiction, situations, voix jouées.
- `discussion` : un moment où le groupe parle pour de vrai (retours, organisation, débat, consignes, un sujet de réunion).
- `autre` : tout le reste (installation, pause, bavardage, échauffement, essais de micro).

Coupe à chaque changement de nature (on passe du jeu à la discussion, ou l'inverse) et, dans une longue discussion, à chaque changement net de sujet. Ne coupe pas pour une réplique isolée : un chapitre dure en général plus d'une minute. Une séance de travail sans jeu ne contient que des `discussion` et des `autre`, découpées par sujet.

Pour chaque chapitre, donne :
- `debut` : l'horodatage de la première réplique du chapitre, recopié tel qu'il est écrit entre crochets dans la transcription (`12:34`, ou `1:02:03` après une heure) ;
- `type` : `scene`, `discussion` ou `autre` ;
- `titre` : trois à huit mots qui disent de quoi il s'agit (« Scène du bowling », « Retours sur la scène du catch », « Affiche et communication »). Pour une scène, nomme la situation jouée, sans la présenter comme réelle.

Les marqueurs « ▸ Marqueur posé pendant la séance » ont été posés par le groupe au moment où il passait au jeu ou à la discussion : coupe à ces endroits, avec le type indiqué, et découpe librement entre eux. Le premier chapitre commence à la première réplique. Ta réponse est toujours l'objet JSON demandé, même pour une séance sans contenu substantiel : un seul chapitre `autre` dont le titre le dit.
