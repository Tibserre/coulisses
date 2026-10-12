# 0032 — Enregistrer le son de l'ordinateur avec le micro, pour les réunions en ligne ou hybrides

Statut : Acceptée (2026-10-07, choix de l'utilisateur). Sort « capture audio système ou visio » du hors-périmètre de la V1 (spec §8). Le lanceur du Dock : fait par l'ADR 0034 (l'app Coulisses). L'écoute est précisée par l'ADR 0037 (un mix d'écoute à part).

## Contexte
L'utilisateur fait aussi des réunions en ligne (Zoom, Teams, Meet dans le navigateur) ou hybrides (une partie dans la salle, une partie à distance). Le micro seul ne suffit pas :
- **avec un casque**, il n'entend pas du tout les personnes à distance ;
- **sans casque**, il les entend par les haut-parleurs, mal.

Le son de l'ordinateur contient ces voix, propres. Depuis macOS 14.4, un « tap » de Core Audio donne tout ce que l'ordinateur joue, avec une seule permission (« Enregistrement audio du système »), sans capture d'écran ni pilote à installer. Le moteur ne traite qu'une piste (le traitement de plusieurs pistes viendra par l'ADR 0006).

## Décision
- Dans « Nouvelle séance », **où se passe la séance** :
  - « Sur place » : le micro seul, comme avant ;
  - « En ligne ou hybride » : le micro **et** le son de l'ordinateur.
  - Le dernier choix est proposé à nouveau. Le deuxième micro (ADR 0031) reste une option à part, combinable avec l'un ou l'autre.
- **Tout le son de l'ordinateur** est pris (un tap global, mixé en mono), pas une seule application : une notification ou une vidéo jouée pendant la réunion y entre aussi.
- **Un petit programme Swift** (`native/son-ordinateur/`) fait la captation, car Python n'a pas accès aux taps :
  - Il crée le tap et un **appareil agrégé privé** dont l'horloge est celle du micro. Le tap y est rééchantillonné (compensation de dérive) : les deux pistes ne se décalent jamais, image par image.
  - Il donne au service des blocs bruts sur sa sortie standard. Chaque bloc porte, en tête, le nombre d'images perdues juste avant lui (y compris celles qu'un tampon n'a pas fournies) : chaque perte est comptée à l'écran et journalisée avec sa position.
  - Il s'arrête quand le service ferme son entrée.
  - Il est compilé sur le Mac, avec le compilateur d'Apple, au démarrage du service s'il a changé. Aucun binaire n'est versionné.
  - Captation brute comme pour le micro : ni gain, ni annulation d'écho, ni réduction de bruit.
- **Deux fichiers** : `ref.wav` (le micro, source de référence) et `system.wav` (source `system`, mono, origine captée). Le service les écrit comme deux micros (fils d'écriture, niveaux, pause au même instant). Le son de l'ordinateur a son propre vumètre. Son silence est normal (personne ne parle à distance) : il n'est signalé que par une ligne discrète, qui rappelle la permission.
- **Pour le traitement, les deux pistes sont réunies** en un fichier `mix.wav` :
  - la référence ramenée en mono plus le son de l'ordinateur ;
  - le tout baissé d'un seul gain juste assez pour ne jamais saturer (jamais compressé).
  - Comme les deux pistes sont sur la même horloge, le mix est dans le temps de la référence : chaque temps mesuré reste vrai (P2).
  - `mix.json` garde le gain, les empreintes des deux sources (celles enregistrées à leur fermeture), l'empreinte du mix et si le son de l'ordinateur est resté muet. Le mix est refait dès que les empreintes enregistrées diffèrent (P5). Ces faits sont recopiés dans le traitement qui l'a utilisé (`job.params.mix`), où ils survivent à la purge (P7).
  - Il est préparé dès l'arrêt, en arrière-plan, et c'est lui qu'on écoute sur la page de la séance une fois prêt.
- **Un son de l'ordinateur resté muet du début à la fin** (la permission manquante, le plus souvent) est dit à l'arrêt et sous le titre de la séance, avec la marche à suivre : le micro seul est traité, jamais en silence (P8).
- Une erreur de démarrage du son de l'ordinateur (permission, compilateur, fréquence du micro) n'est pas retentée : elle est dite à l'instant.
- Si le fichier du son de l'ordinateur a disparu, le traitement s'arrête et le dit : il ne traite jamais le micro seul en silence, car les personnes à distance manqueraient (P8). Une piste vide ou illisible est dite sous le titre de la séance, et le micro seul est traité.
- Le mix et `mix.json` vivent dans `sources/` : purgés et supprimés avec l'audio de la séance (ADR 0029). Aucune suppression ne se fait pendant qu'un mix s'écrit.

## Conséquences
- Rien de nouveau dans le schéma : `audio_source` tient N sources. `offset_s` et `drift_ppm` du son de l'ordinateur valent 0, et c'est ici une mesure : la même horloge.
- Les outils de développement d'Apple (Command Line Tools) sont nécessaires une fois, pour compiler le programme. Sans eux, « En ligne ou hybride » le dit et explique comment les installer.
- macOS demande la permission « Enregistrement audio du système » à l'application qui lance Coulisses (pendant le développement : le terminal ; plus tard, le lanceur du Dock, étape 10). Sans elle, le son de l'ordinateur arrive **muet**, sans erreur.
- Les personnes à distance et celles de la salle sont sur deux pistes distinctes. Le moteur pourra s'en servir plus tard (indice fort pour séparer les voix, ADR 0006) ; d'ici là, le mix suffit à les transcrire.
- Sans casque, les voix à distance sont aussi captées par le micro, avec un léger retard : le mix les contient en double, faiblement. La transcription n'en souffre pas en pratique ; c'est une piste d'amélioration pour le moteur.

## Alternatives écartées
- Une seule piste à deux canaux (micro et ordinateur) : le moteur la ramènerait en mono sans le dire, et on perdrait la séparation propre.
- Un pilote audio virtuel (BlackHole, Loopback) : une installation système de plus, un réglage de sortie à faire avant chaque réunion.
- ScreenCaptureKit : demande la permission d'enregistrer l'écran, plus large que nécessaire.
- Capter seulement l'application de réunion : il faudrait la choisir à chaque fois, et une réunion dans le navigateur mélange tous les onglets.
- Deux flux séparés (le micro par PortAudio, l'ordinateur par le programme) : deux horloges, donc une dérive à mesurer, ce que l'appareil agrégé évite.
