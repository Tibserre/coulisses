# Relais : lot 12c-1a fait, v0.28.1 (pour « Pilotage » et « Distribution et publication »)

De : la conversation « Alléger Coulisses », le 2026-10-19. Ni l'une ni l'autre n'étaient ouvertes : ce relais tient lieu de message.

## Ce qui est fait
- L'app passe au moteur v1.7.2, qui retire librosa et ce qu'il tirait (numba, llvmlite, soxr, pooch, soundfile, decorator, lazy-loader, msgpack, platformdirs). Fusion dans `main` : version v0.28.1 (`a8f7ebb`).
- Les sorties de la chaîne retenue sont identiques (selon le Moteur). Les 396 tests de l'app passent, et le test lent sur les vrais modèles aussi.
- Les tests lisent les WAV avec le module `wave` de Python (`tests/wav_reader.py`) au lieu de soundfile, sans dépendance native.

## Mesuré
Source : [2026-10-19-v0.28.0-moteur-v1.7.2.md](2026-10-19-v0.28.0-moteur-v1.7.2.md), sur une app d'essai signée ad hoc, jamais publiée.
- **App installée : −170 Mo** (1,99 → 1,82 Go).
- **DMG : −50 à −77 Mo.** Pour un même contenu, sa taille varie d'environ 27 Mo d'une construction à l'autre (723 puis 696 Mo, en ULFO). Seul l'écart de l'app est sûr.

## Pour Pilotage (plan, étape 12)
- **12c-1a fait** (librosa).
- **12c-1b attend une décision de l'utilisateur.** Il s'agit des dépendances de pyannote-audio, 286 Mo.
  - pyannote-audio 4 les rend obligatoires.
  - Le filet ne peut pas aller dans l'environnement DiariZen, qui a pyannote 3.1, alors que community-1 exige pyannote 4.
  - Le Moteur propose un environnement « pyannote » installé à la demande : le premier pas de 12c-2, avec un ADR.
  - Proposition : rattacher 12c-1b à 12c-2 dans le plan.
- **12e** : l'ADR 0046 (FLAC) est proposée sur la branche `docs/adr-flac` et attend la validation de l'utilisateur.
- **12d** : le Moteur mesure au banc sans rien télécharger. Le téléchargement des modèles retenus attendra l'accord de l'utilisateur.

## Pour Distribution
- **Remets-toi à jour sur `main` avant le lot 12b** : `uv.lock` change.
- **Pour mesurer 12b**, compare l'app installée, ou plusieurs DMG : un seul DMG ne suffit pas, vu l'écart d'une construction à l'autre.
- **La note de version de v0.28.1** a été écrite d'après le commit : « passe au moteur v1.7.2, qui ne tire plus librosa ». Pour des amis, elle est à reformuler à la publication (lot 11f), par exemple « Coulisses prend environ 170 Mo de moins ».
