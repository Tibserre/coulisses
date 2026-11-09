# 0074 — Un seul fichier par son : chaque piste gardée en FLAC dans un MP4

Statut : Acceptée (2026-11-06, par l'utilisateur, « vas y », puis « il faut que la migration se fasse aussi », relayés par Pilotage : une solution durable qui ne multiplie pas la place prise, et les séances existantes migrées). Le mix d'écoute identique au mix applique la même règle : vu à l'essai de Distribution, accepté par l'utilisateur (« Oui, supprimer », 2026-11-06). Remplace l'ADR 0073. Précise l'ADR 0046.

## Contexte
- L'ADR 0073 a corrigé le saut dans l'écoute. Dans un FLAC brut, le lecteur de la page (WebKit) tombe à plusieurs secondes de l'endroit annoncé après un clic sur une phrase. Dans le même FLAC rangé dans un MP4, il tombe juste.
- Pour une séance sans le son de l'ordinateur, elle gardait pourtant la piste en FLAC brut, pour le moteur, et ajoutait une copie d'écoute en MP4 à côté. Le même son était donc gardé deux fois, environ 260 Mo de plus par heure.
- Le moteur lit tout par ffmpeg (« tout format que ffmpeg lit », `engine/README.md`). Les imports en `.m4a` d'un téléphone passent déjà. Garder un FLAC brut pour lui n'a pas de raison.
- Mesuré sur une vraie piste d'une heure, le même FLAC dans un MP4 pèse 160 Ko de plus (+0,06 %).

## Décision
- **Chaque piste gardée** est conservée en un seul fichier, du FLAC dans un MP4 (`.m4a`) : les micros, le son de l'ordinateur, le mix que le moteur entend et le mix d'écoute. Ce fichier remplace le FLAC brut. Il n'y a plus de copie d'écoute. Une séance sans le son de l'ordinateur fait entendre sa piste elle-même.
- **Ce qui ne change pas de l'ADR 0046** :
  - un fichier n'est remplacé qu'après la preuve par l'empreinte des échantillons décodés ;
  - le fichier d'avant n'est supprimé qu'une fois les deux reprouvés ;
  - chaque suppression est inscrite au journal (ADR 0029) ;
  - un fichier abîmé est mis de côté ;
  - un passage coupé est repris au démarrage.
- **Ce qui n'est jamais refait pour un changement de conteneur** :
  - la base garde le codec `flac` et l'empreinte des échantillons, `pcm_sha256` ;
  - `mix.json` garde `made_from`, `made_at`, le gain et `pcm_sha256` ;
  - ni le mix ni aucune étape du moteur n'est donc refait.
  
  Seuls le nom du fichier et son empreinte (`sha256`) changent. La provenance d'une exécution passée garde le chemin qu'elle a lu, comme après le passage en FLAC (ADR 0046).
- **Les séances gardées en FLAC brut avant sont migrées d'elles-mêmes.** C'est décidé par l'utilisateur (« il faut que la migration se fasse aussi », 2026-11-06), et cela lève pour elles la réserve de l'ADR 0046.
  - **Quand :** après la mise à jour, en tâche de fond à chaque démarrage, une séance après l'autre, sans bloquer l'app. Interrompue, la migration reprend au démarrage suivant.
  - **Pour chaque piste et chaque mix :** passage dans un MP4 sans réencodage (`-c:a copy`), preuve, puis suppression du FLAC brut, inscrite au journal.
  - **Une séance dont un traitement attend ou tourne** est laissée pour un démarrage suivant.
  - **Une séance qui échoue** garde ses fichiers. Le journal des suppressions dit pourquoi (P8). Elle est notée (`app_setting`, `lossless.mp4_failed`) pour n'être ni retentée ni réécrite au journal à chaque démarrage. `coulisses-app --ecoute-exacte` (service arrêté) la retente, à la demande.
- **Les WAV d'avant l'ADR 0046 ne sont pas migrés.** Ils n'ont pas d'empreinte de leurs échantillons, et leur mix les reconnaît par l'empreinte du fichier. Les convertir ferait refaire le mix et rendrait la preuve plus faible. Un WAV saute juste dans le lecteur.
- **Un mix d'écoute qui rend exactement les échantillons du mix** (le micro jamais baissé, ADR 0037) est le même son. `mix.json` le fait entendre depuis le fichier du mix (`listening_mix.file`), puis son propre fichier est supprimé, une fois les deux prouvés, avec une entrée au journal. Sinon il reste, car c'est un autre son. Seulement une fois le mix dans un MP4, sa forme dernière : en FLAC brut, les deux restent, et le passage en MP4 les dédouble ensuite. Cela vaut pour les nouvelles séances comme pour celles déjà migrées, reprises au démarrage.
- **La copie d'écoute faite par la v0.38.2** (`listening-copy.m4a`) reste servie tant que sa piste est en FLAC brut. Une fois la piste dans un MP4, la copie est un deuxième fichier du même son. Elle est alors supprimée, après la preuve qu'elle rend les échantillons de la piste, et la suppression est inscrite au journal avec toute sa place libérée. Une copie qui diffère est gardée, et c'est dit. Une copie restée inachevée (`.partiel`) est retirée et le journal du service le dit.
- **Sans un ffmpeg qui écrive du FLAC dans un MP4** (essai réel, une fois par service), les pistes restent en FLAC brut, comme avant, et la commande ne fait rien et le dit. Le ffmpeg embarqué l'écrit depuis la v0.38.2 (`build/ffmpeg-mp4`).
- La page reçoit `audio/mp4` pour un `.m4a` et `audio/flac` pour un FLAC brut.

## Conséquences
- Une séance prend la même place qu'avec l'ADR 0046, à 0,06 % près.
- Le moteur lit désormais du FLAC dans un MP4. Un test de l'application avec les vrais modèles donne les mêmes mots, temps et voix qu'en WAV et en FLAC brut ; le rôle Moteur doit encore le garantir dans son contrat (relais du 2026-11-06), avant la publication.
- Les imports restent tels quels (spec §7.2). Un FLAC importé garde le défaut de saut.
- Au premier démarrage après la mise à jour, la page d'une séance en cours de migration peut devoir être rouverte : son fichier change sous le lecteur.
- Le défaut de WebKit n'est mesuré que sur des fichiers synthétiques. La correction est à confirmer à l'oreille dans l'app.

## Alternatives écartées
- **La copie d'écoute de l'ADR 0073** : elle garde le même son deux fois.
- **Garder la piste du moteur en FLAC brut** : sans raison, le moteur lit par ffmpeg.
- **ALAC** : il saute juste lui aussi, mais il réencode et ne rend pas le FLAC déjà gardé.
