# 0027 — La captation en pratique : WAV 24 bits tenu à jour, niveaux en flux, batterie

Statut : Acceptée (2026-10-06 : l'utilisateur valide la dépendance, la migration 0005 et le comportement sur batterie). Précise l'ADR 0005 et en remplace un point : les niveaux passent par un flux d'événements, pas par WebSocket. Le lanceur du Dock : fait par l'ADR 0034 (l'app Coulisses).

## Contexte
L'ADR 0005 confie la captation au service Python (PortAudio via `sounddevice`), avec écriture continue, survie à un plantage, vumètre par WebSocket et anti-veille. Au moment de la construire (étape 6), il restait à préciser le format, la façon de garder le fichier lisible après un plantage, le transport des niveaux et le comportement sur batterie : un traitement d'une séance de 1 h 30 représente environ un quart d'heure de calcul intensif.

## Décision
- **Format** : WAV PCM 24 bits à 48 kHz, avec les canaux du micro tels quels (deux au plus). Rien n'est traité : ni réduction de bruit, ni gain.
- **Fichier toujours lisible** : l'en-tête WAV est réécrit et le fichier forcé sur le disque au moins chaque seconde. Au démarrage, un enregistrement resté « en cours » est réparé (l'en-tête est recalé sur ce qui est sur le disque), marqué « récupéré » et signalé. Il n'est jamais traité sans l'utilisateur. On perd au plus une seconde.
- **La séance existe dès le début de l'enregistrement** (`capture_state = recording`), pour qu'un plantage la laisse là, à réparer. Le micro est ouvert avant : un micro qui refuse de s'ouvrir ne laisse rien derrière lui.
- **La pause** coupe le son à l'instant où il est entendu, pas quand il est écrit. Le fichier ne contient que ce qui a été enregistré, et les instants des marqueurs et des notes (étape 6b) se comptent dans ce temps-là.
- **Les niveaux** (crête et moyenne, en dBFS) et l'état arrivent dix fois par seconde par un flux d'événements (SSE). Le flux s'arrête avec l'enregistrement. Il n'y a pas de WebSocket, donc pas de paquet en plus.
- **Les alertes** :
  - « trop faible » quand le niveau moyen reste sous −50 dBFS pendant 10 s ;
  - « saturation » pendant 2 s après une crête à 0 dBFS ;
  - « le micro ne donne plus de son » quand aucun bloc n'arrive pendant 3 s.
- **Anti-veille** : `caffeinate -i` de macOS, tenu pendant un enregistrement et pendant chaque tâche de traitement, et relâché à la fin.
- **Batterie** : à l'arrêt, si le Mac est sur batterie, le traitement ne démarre pas tout seul. La séance propose « Traiter maintenant », avec la durée estimée et un rappel de brancher le Mac. Sur secteur, le traitement démarre seul.
- **À l'arrêt du service** (fermeture normale), un enregistrement en cours est arrêté proprement.
- `sounddevice` et `numpy`, déjà installées avec le moteur, deviennent des dépendances directes de l'application.

## Conséquences
- Une seule captation à la fois.
- La permission micro de macOS va au processus qui lance le service : pendant le développement, l'application qui lance le serveur ; ensuite, le lanceur du Dock (étape 10).
- Le traitement d'une séance enregistrée sur batterie attend un clic. C'est voulu.

## Alternatives écartées
- WebSocket pour les niveaux : une dépendance de plus pour un flux à sens unique.
- Laisser libsndfile gérer l'en-tête : il ne le met à jour qu'à la fermeture, ce qui laisserait un fichier illisible après un plantage.
- Traiter quand même sur batterie : refusé par l'utilisateur.
