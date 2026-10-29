# 0056 — Enregistrer en un geste : « Nouvelle note », hybride par défaut, le déroulé au centre

Statut : Acceptée (2026-10-21, choix de l'utilisateur pour le parcours « je lance l'enregistrement en réunion… jusqu'à l'arrêt », étape 13c, maquettes validées : « Nouvelle note lance une réunion en hybride de base, en un geste » ; un bouton pour couper le son de l'ordinateur, « activé ou désactivé à la demande » ; la note dans l'espace sélectionné ; l'écran A, le texte au centre ; « annotations » pour les notes prises pendant). Choix de mise en œuvre : le micro par défaut de macOS, « Le micro seul » si le démarrage échoue, Jeu ⇄ Discussion gardé dans tous les espaces. Précise 0030 (« Nouvelle séance » devenait un dialogue) et 0032 (le son de l'ordinateur se choisit au départ). Import et fenêtre « Nouvelle note » : remplacés par 0069 (import en un geste, fenêtre supprimée).

## Contexte
L'utilisateur trouvait la fenêtre « Nouvelle séance » trop lourde : espace, projet, présents, invités, non-nommés, lieu et micros, avant de pouvoir enregistrer. En réunion, il veut que ça démarre tout de suite. Les présents se cochent déjà après coup (spec §7.1). L'écran d'enregistrement mettait en avant une grande horloge et une illustration, avec le déroulé dessous. Principes : P2 (temps mesurés), P3 (les présents ne sont qu'un minimum), P8 (rien de perdu ni de caché).

## Décision
- **Un geste** : « Nouvelle note » (⌘N), le « + » d'un espace ou d'un projet, et le bouton de l'accueil démarrent l'enregistrement aussitôt. Il est en ligne ou hybride (micro et son de l'ordinateur), avec le micro par défaut, sans présent coché, dans l'espace sélectionné : celui de la séance ouverte (et son projet), celui dont la page est ouverte, sinon celui de l'accueil. Pendant un enregistrement, le geste y ramène. Un échec au démarrage est dit, avec « Le micro seul ». L'import et le choix détaillé restent dans la fenêtre « Nouvelle note », ouverte depuis « ou importer un fichier ».
- **Le contexte se corrige en enregistrant** : en tête de l'écran, l'espace, le projet et les présents s'ouvrent en listes flottantes. Changer d'espace (`PUT /api/seances/{id}/espace`) n'est possible que tant que rien n'est traité. Les présents de l'ancien espace sont alors décochés, et l'écran dit lesquels, d'après la réponse du service. Le nombre de non-nommés est gardé ; le projet revient à « Aucun ».
- **Couper le son de l'ordinateur**, à tout moment (`POST /api/enregistrement/son-ordinateur`) : du silence est écrit à sa place sur la même horloge. Son fichier garde la même longueur que celui du micro, et les temps restent mesurés (P2). L'avertissement « macOS ne l'a sans doute pas donné » ne se tait que si le son a été coupé du début à la fin.
- **L'écran** : une barre fine collée en haut (temps, niveau, son de l'ordinateur et son bouton, Jeu ⇄ Discussion, ★ Moment, Pause, Arrêter), les alertes seulement quand il y en a, le contexte, la frise, puis le déroulé au centre. Ce déroulé est mis en page comme la transcription qu'il deviendra : annotations, moments et changements de mode à leur heure. En bas, la ligne pour annoter, sans cadre. Le texte en direct (moteur, ADR 0053 du moteur) viendra s'y intercaler.
- **Vocabulaire** : le bouton s'appelle « Nouvelle note » (choix de l'utilisateur). Le mot du domaine reste « séance ». Les notes prises pendant l'enregistrement deviennent des **annotations** (`timed_note`), pour ne pas les confondre avec ce bouton.

## Conséquences
- L'illustration « enregistrement » (direction artistique, `enregistrement.riv`) n'est plus montrée pendant la captation. Son emplacement reste prévu.
- macOS demande la permission « Enregistrement audio du système » dès le premier enregistrement, puisque l'hybride est le défaut. Sans elle, le son de l'ordinateur arrive muet, et l'écran le rappelle (ADR 0032).
- Le mot « note » désigne encore la note d'après séance (Vue d'ensemble) : à revoir avec l'utilisateur.
- Jeu ⇄ Discussion reste visible dans tous les espaces. Le limiter aux espaces qui s'en servent demanderait un réglage d'espace, donc une décision sur le schéma (à poser à l'utilisateur).
- Les moments où le son de l'ordinateur a été coupé ne sont gardés nulle part : plus tard, ce silence ne se distingue pas d'un silence réel (P7). Les garder changerait le schéma : à décider avec l'utilisateur si le besoin se présente.

## Alternatives écartées
- Un petit panneau sous le bouton (où, comment), puis « Commencer » : encore un pas avant d'enregistrer.
- Le son d'abord, avec le temps en grand et le texte en bande : le texte, qui deviendra la transcription, est ce qu'on veut voir.
- « Sur place » par défaut : en réunion, une partie des gens est souvent à distance.
