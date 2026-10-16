Découpe la séance en chapitres qui se suivent, de la première réplique à la dernière, sans trou ni chevauchement. Les chapitres servent à s'y retrouver : chacun doit valoir la peine d'être retrouvé.

Un chapitre est un moment où le groupe fait la même chose, sur le même sujet. Il est d'un de ces deux types :
- `scene` : un moment joué. Les répliques sont celles de personnages : une improvisation, une scène, un exercice en plateau, une simulation, un jeu de rôle.
- `discussion` : tout ce qui n'est pas joué, où l'on parle pour de vrai : un point de réunion, des retours, une décision, de l'organisation, des consignes, mais aussi l'installation, une pause ou du bavardage.

Coupe quand le groupe change d'activité (on passe du jeu à la discussion, ou l'inverse) ou change nettement de sujet. Ne coupe pas pour une digression, une question rapide ou une blague : elles restent dans le chapitre où elles tombent. Par exemple, dans une répétition, chaque improvisation et les retours qui la suivent font deux chapitres ; dans une réunion, chaque point traité fait un chapitre, et une séance sans jeu ne contient que des `discussion`.

Pour chaque chapitre, donne :
- `debut` : l'horodatage de la première réplique du chapitre, recopié tel qu'il est écrit entre crochets dans la transcription (`12:34`, ou `1:02:03` après une heure) ;
- `type` : `scene` ou `discussion` ;
- `titre` : trois à huit mots, tirés de ce qui se dit dans le chapitre, qui nomment son sujet. Pour une scène, nomme la situation jouée, sans la présenter comme réelle ; pour des retours, nomme la scène dont on parle. Deux chapitres de ta réponse n'ont jamais le même titre.

Les marqueurs « ▸ Marqueur posé pendant la séance » ont été posés par le groupe au moment où il passait au jeu ou à la discussion : coupe à ces endroits, avec le type indiqué, et découpe librement entre eux. Le premier chapitre commence à la première réplique. Ta réponse est toujours l'objet JSON demandé, même pour une séance sans contenu substantiel : un seul chapitre `discussion` dont le titre le dit.
