# 0058 — De l'arrêt à la relecture : arrêter sans confirmation, la relecture qui se construit, un présent muet est une question

Statut : Acceptée (2026-10-21). Choix de l'utilisateur pour la fin du parcours « je lance l'enregistrement… jusqu'à l'arrêt » (étape 13c), sur maquettes :
- pas de confirmation d'arrêt, mais « la possibilité de reprendre dans les 3 secondes suivant l'arrêt » ;
- la variante C, « la relecture se construit » ;
- la question « un présent n'a pas parlé » ;
- l'erreur dite en français ;
- l'attente sur batterie, « à peu près esthétique ».

Choix de mise en œuvre : l'arrêt différé est fait par le service, la pause tient pendant le délai, le temps restant est estimé à environ 10 min par heure d'audio, l'aperçu est relu toutes les 4 s. Précise 0005 (l'arrêt) ; respecte 0027 (sur batterie, le traitement attend un clic).

## Contexte
Avant, « Arrêter » ouvrait une fenêtre de confirmation. La page de la séance montrait ensuite un titre, une phrase et la liste des étapes, sans rien de la séance elle-même. L'échec « 4 voix trouvées pour 5 présents » arrivait en rouge, avec son message en double. Une erreur de l'application, une validation par exemple, s'affichait brute et en anglais. Avec le lancement en un geste (0056), les présents se cochent pendant la réunion, et un présent qui n'a pas parlé devient courant. Principes : P2 (temps mesurés), P3 (les présents ne sont qu'un minimum), P8 (rien de perdu, une erreur se voit).

## Décision
- **Arrêter** : l'enregistrement est mis en pause aussitôt (`POST /api/enregistrement/arret-differe`), et l'écran d'arrêt passe au premier plan, la séance estompée derrière (0059) : une grande icône stop dans un disque couleur accent (précisé le 2026-10-21), « Arrêt », une barre qui se remplit pendant le délai et « Reprendre » (aussi Espace ou Échap). Demande de l'utilisateur, après un premier essai où la barre du haut le disait : « une page intermédiaire… barre qui charge, mais pouvoir reprendre ». Au bout de `STOP_DELAY_S` (3 s), le service l'arrête lui-même, même si la page a été fermée entre-temps. « Reprendre » annule l'arrêt et laisse l'enregistrement comme il était : il reprend (`/reprise`), ou reste en pause s'il l'était avant « Arrêter » (`/arret-annule`). Une fois l'arrêt commencé, il est trop tard : le service le dit (409). Ces secondes de pause ne sont pas enregistrées. Le service tient l'arrêt sous un verrou (`stopping.DelayedStop`) : un arrêt demandé par la barre des menus pendant le délai arrête tout de suite, et pendant un arrêt en cours, il l'attend au lieu de le doubler. À la fermeture du service, un délai qui court est abandonné (l'enregistrement est fermé proprement), un arrêt commencé est attendu. La page lit l'issue de l'arrêt (`GET /api/enregistrement/arret` : en cours, fait, ou erreur), tant qu'il est en cours, puis ouvre la séance avec ce qu'a dit l'arrêt (un micro qui a lâché…) ; sans réponse au bout d'une minute, elle le dit. L'arrêt immédiat (`POST /arret`) reste pour la barre des menus.
- **Pendant le traitement, la relecture se construit** :
  - une ligne fine dit l'étape en cours, le temps qui reste (« environ ») et les étapes faites ;
  - dessous, le texte dès qu'il est transcrit (`GET /api/seances/{id}/apercu`), en gris. Il est lu dans les exécutions de la dernière tâche de traitement, sinon de la version affichée ; l'alignement n'est pris que s'il a aligné cette transcription (jamais deux versions du moteur mêlées, 0040). Chaque ligne est à l'heure mesurée de son premier mot ; une ligne sans temps mesuré n'en reçoit pas et garde sa place dans le texte (P2). Les annotations et les moments s'y glissent à leur heure ;
  - cet aperçu se lit depuis les exécutions du moteur, par son contrat, et n'est jamais gardé ;
  - quand « Qui a dit quoi » se termine, la relecture s'ouvre, et les noms s'y posent en glissant (400 ms), une seule fois.
- **Moins de voix que de présents** : ce n'est plus un échec affiché en rouge, mais une question : « 4 voix entendues, 5 présents cochés : quelqu'un n'a peut-être pas parlé ». L'app recommande ce qu'elle a entendu : « Relancer avec 4 présents (recommandé) » ; « Choisir un autre nombre » permet de le fixer (demande de l'utilisateur : « recommander un nb de présents par rapport à ce qu'il a vu »). Si aucune voix n'est entendue, la question le dit. Les voix ne sont jamais fusionnées (P3).
- **Une erreur de l'application** (sans code d'erreur du moteur) est dite en français, avec « Reprendre ». Son texte brut n'apparaît qu'en mode développeur. Les étapes et leur provenance s'affichent en mode développeur, dès qu'une étape s'arrête, ne donne plus de nouvelles ou est à refaire (P7, P8).
- **Sur batterie**, une ligne : « Le Mac est sur batterie : le traitement attend votre accord », la durée estimée, puis « Traiter maintenant » (0027 inchangé).

## Conséquences
- **La pause** se dit aussi à toute la pièce : la séance s'estompe sous un voile flouté (0059), une grande icône pause dans un disque, « En pause », les icônes barrées du micro et du son de l'ordinateur, un grand « Reprendre ». Demande de l'utilisateur : « un pause visible sur l'écran, un fond blur, et reprendre… qui montre aux interlocuteurs en présentiel que c'est en pause… mettre en confiance », puis « un gros icon pause et un gros icon stop, pas juste des mots, que ça soit moins verbeux » (précisé le 2026-10-21).
- Pendant les 3 s, l'enregistrement est en pause : la barre des menus le montre « en pause ». Un arrêt demandé par la barre des menus pendant ce temps arrête tout de suite.
- Le traitement démarre 3 s plus tard qu'avant : sans effet pour l'utilisateur.
- L'estimation du temps restant est grossière (une moyenne par heure d'audio), d'où le « environ ».

## Alternatives écartées
- Une confirmation accrochée au bouton : encore un geste pour un arrêt presque toujours voulu.
- Un délai tenu par la page seule : une page fermée pendant le délai laisserait l'enregistrement tourner.
- Les voix qui se démêlent (les cordes), ou une barre sobre : l'utilisateur préfère voir le texte arriver.
- Démarrer le traitement de lui-même au branchement du Mac : contraire à 0027, qui attend un clic ; à rediscuter avec l'utilisateur si besoin.
