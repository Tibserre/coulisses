# 0046 — Les enregistrements gardés en FLAC, sans perte, une fois l'enregistrement fini

Statut : Proposée (2026-10-16, lot 12e du plan). Elle précisera l'ADR 0027 (format) et changera la spec §7.2.

## Contexte
L'app enregistre en WAV PCM 24 bits à 48 kHz (ADR 0027), soit 518 Mo par heure et par piste mono. Une réunion avec le son de l'ordinateur garde 4 pistes : le micro, l'ordinateur, le mix que le moteur entend, le mix d'écoute (ADR 0032, 0037). Cela fait 2,07 Go par heure. La source est le relevé `docs/technique/tailles/2026-10-16-v0.28.0.md`.

Essai du 2026-10-16 sur l'enregistrement de Données-dev (1,73 h, mono, 24 bits) :
- le FLAC fait 498 Mo au lieu de 896 Mo, soit −44 % ;
- les échantillons décodés sont identiques au bit près (même SHA-256 du PCM) ;
- les niveaux de compression 5 et 8 donnent la même taille, à 0,1 % près.

Ce qui est en jeu :
- **P5** : rejouable à l'identique ;
- **P8** : aucune perte, aucune suppression muette ;
- **ADR 0027** : un fichier lisible après un plantage, ce que le WAV tenu à jour assure.

Ce que l'existant permet déjà :
- le moteur lit tout format que ffmpeg lit (`engine/README.md`) ;
- le ffmpeg embarqué décode le FLAC, mais ne l'encode pas (`scripts/construction.toml`) ;
- la fenêtre de l'app (WKWebView) lit le FLAC.

## Décision
- **Pendant l'enregistrement, rien ne change** : WAV tenu à jour, réparé après un plantage (ADR 0027).
- **Une fois l'enregistrement fini et les mixes faits, chaque piste enregistrée par l'app est gardée en FLAC.** Cela vaut pour :
  - les micros, le son de l'ordinateur ;
  - `mix` (ce que le moteur entend : on le garde, pour que relancer lui redonne exactement la même entrée) ;
  - `listening` (le mix d'écoute).
  Le FLAC garde les échantillons à l'identique, en 24 bits et 48 kHz, avec ses canaux.
- **Le WAV n'est supprimé qu'après preuve.** Le FLAC est écrit à côté sous un nom provisoire, relu entièrement, et l'empreinte de ses échantillons décodés doit être celle du WAV. Ensuite seulement il prend son nom et le WAV est supprimé. Sinon, le WAV reste, l'erreur va au journal et la séance le signale (P8). La conversion est inscrite au journal des suppressions (ADR 0029) : fichier, tailles avant et après, empreinte des échantillons.
- **L'empreinte qui identifie une piste devient celle de ses échantillons**, quel que soit le format. Le mix est fait de deux sources (`mix.json`, `made_from`) ; il ne doit pas être refait parce que l'une d'elles est passée en FLAC. **Changement du schéma de données** (`audio_source`) : il demande l'accord de l'utilisateur avant d'être fait.
- **L'encodeur** : le ffmpeg embarqué reçoit l'encodeur et le format FLAC (`construction.toml`, conversation Distribution, quelques centaines de ko). Ce n'est pas une nouvelle dépendance native.
- **Les fichiers importés restent tels quels** (spec §7.2 : l'original est conservé).
- **Les séances déjà enregistrées ne sont pas converties d'office.** Les convertir sera proposé à part, avec la place à gagner, et fait seulement sur accord de l'utilisateur.
- La purge et la suppression de l'audio (ADR 0029) s'appliquent aux FLAC comme aux WAV.

## Conséquences
- **Place par heure** : environ 290 Mo pour une répétition au lieu de 518, environ 1,16 Go pour une réunion au lieu de 2,07. Les 90 jours de conservation coûtent d'autant moins.
- **Un passage de plus à la fin de l'enregistrement**, en tâche de fond : encodage, puis vérification. Le traitement part du `mix` ou de `ref` en FLAC, une fois la conversion finie. Ce délai est à mesurer.
- La provenance des exécutions nommera `ref.flac`. Les anciennes exécutions gardent le nom `ref.wav` : c'est du texte, elles restent lisibles.
- **À vérifier avant de l'accepter** :
  - le moteur donne des sorties identiques sur le WAV et sur son FLAC ;
  - la lecture et le déplacement dans le temps sont précis dans la fenêtre de l'app ;
  - le type `audio/flac` est servi.
- La spec §7.2 et l'ADR 0027 seront mis à jour dans le même commit que le code.

## Alternatives écartées
- **Refaire les mixes à la demande au lieu de les garder** (environ 0,6 Go par heure de réunion) : un mix refait par une autre version de l'app peut différer de celui que le moteur a entendu, ce qui contredit P5. Le mix d'écoute pourrait l'être ; on le garde pour qu'il soit simple de l'entendre tout de suite. **À trancher par l'utilisateur.**
- **Enregistrer directement en FLAC** : un fichier interrompu par un plantage ne se répare pas aussi sûrement qu'un WAV tenu à jour (ADR 0027).
- **Un format avec perte** (AAC, Opus) : la captation est brute (spec §7.2), et le moteur doit pouvoir rejouer à l'identique.
- **Encoder avec `soundfile` (libsndfile)** : c'est une dépendance native de plus, alors que le moteur s'apprête à ne plus la tirer (lot 12c).
