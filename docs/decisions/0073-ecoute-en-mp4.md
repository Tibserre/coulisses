# 0073 — L'écoute est servie en FLAC dans un MP4, où le lecteur va au bon endroit

Statut : Remplacée par 0074 (2026-11-06 : un seul fichier par son, plus de copie d'écoute). Acceptée (2026-11-03, par l'utilisateur, qui a choisi « Écoute en mp4 » parmi trois formats, puis « Oui, finir » le 2026-11-04). Correction d'un bug signalé par l'utilisateur. Précise l'ADR 0046.

## Contexte
Sur une séance enregistrée, le mot surligné prenait de l'avance sur la voix, de plus en plus loin dans la séance. Mesures sur la séance enregistrée la plus récente :
- **Les temps sont justes.** Ils tombent sur la parole à l'échelle 1,0000 du début à la fin d'une heure, sur le mix donné au moteur comme sur le mix d'écoute. Toutes les pistes sont à 48 kHz et ont la même durée.
- **La lecture se trompe après un saut.** La page lit l'audio dans WebKit, qui passe par AVFoundation. Dans un FLAC brut, le lecteur (WebKit) atterrit à plusieurs secondes de l'endroit qu'il annonce (`currentTime`) après un saut, c'est-à-dire un clic sur une phrase. L'écart va de −16 s à +6 s sur un fichier de 5 min. En lecture continue, rien ne dérive.
- **Une table de saut n'y change rien.** Les FLAC écrits par ffmpeg n'en ont pas. Une SEEKTABLE ajoutée à la main ne corrige pas le saut.
- **Ce qui saute juste.** WAV, ALAC et **le même FLAC dans un MP4** retombent exactement au bon endroit, à chaque saut. Les imports (MP4, M4A) n'avaient pas le défaut.

## Décision
- **Le mix d'écoute** (ADR 0037) est gardé en FLAC **dans un MP4** (`listening.m4a`), au lieu d'un FLAC brut. Il garde les mêmes échantillons, prouvés comme dans l'ADR 0046 (empreinte des échantillons décodés).
- **Une séance sans le son de l'ordinateur** fait entendre sa piste telle quelle. Celle-ci reste en FLAC brut, intacte, car le moteur la lit. Une **copie d'écoute** dans un MP4 (`listening-copy.m4a`) est faite à côté, prouvée de même, juste après la conversion de la piste. Elle prend la même place que la piste, environ 260 Mo par heure.
- **Mettre en MP4 un FLAC ne le réencode pas** (`-c:a copy`) : seul le conteneur change. Le MP4 a son index en tête (`+faststart`).
- **Les séances gardées en FLAC brut avant ne changent que si l'utilisateur le demande** (ADR 0046). La commande `coulisses-app --ecoute-exacte` le fait, service arrêté :
  - leur mix d'écoute est remis dans un MP4, sans perte et prouvé ; le FLAC brut est alors supprimé et le journal des suppressions le note ;
  - la piste entendue telle quelle reçoit sa copie d'écoute.
  
  Une séance dont la preuve échoue reste telle quelle, et la commande le dit.
- **Sans un ffmpeg qui écrive du MP4**, rien ne change : le FLAC brut est servi, comme avant, et la commande ne fait rien et le dit. Le ffmpeg embarqué doit gagner le format `mp4` en écriture (`scripts/construction.toml`, rôle Distribution).
- La page reçoit `audio/mp4` pour ces fichiers.

## Conséquences
- Une séance sans le son de l'ordinateur prend environ deux fois plus de place qu'avant (la piste et sa copie), mais toujours moins qu'en WAV.
- Les séances anciennes gardent le défaut tant que la commande n'est pas lancée.
- Un fichier importé en FLAC garde le défaut : les imports restent tels quels (spec §7.2) et ne reçoivent pas de copie d'office. `--ecoute-exacte` leur en fait une, l'original intact.
- Une copie ou un rangement coupé (service arrêté) ne laisse rien : la copie d'une séance qui vient d'être enregistrée est refaite au passage suivant, un `.partiel` qui ne sera plus fini est retiré (journal du service), un FLAC brut resté à côté de son MP4 part avec la commande suivante, une fois prouvé.
- Le défaut de WebKit n'est mesuré que sur des fichiers synthétiques, avec un détecteur fragile après un saut. La correction est à confirmer à l'oreille dans l'app.

## Alternatives écartées
- **Copie en MP4 de toutes les pistes servies, sans toucher aux FLAC** : plus simple, mais elle double aussi la place du mix d'écoute.
- **WAV décodé à la volée, à chaque demande du lecteur** : aucune place en plus, mais un ffmpeg par requête et un découpage par octets à tenir juste.
- **Une SEEKTABLE dans le FLAC** : mesurée sans effet.
- **ALAC** : il saute juste lui aussi, mais il réencode, alors que le FLAC dans un MP4 ne change que le conteneur.
