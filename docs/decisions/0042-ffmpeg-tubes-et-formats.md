# 0042 — Le ffmpeg embarqué lit aussi par un tube, et lit Matroska (WebM, MKV) et W64

Statut : Acceptée (2026-10-13, validée par l'utilisateur). Précise l'ADR 0041 (protocoles et formats lus).

## Contexte
Le lot 11c a montré que l'ADR 0041 était trop étroit sur trois points :
- **la transcription** (mlx-audio, dans le moteur) envoie l'audio à ffmpeg par un tube (`pipe:0`) et le reçoit de même (`pipe:1`, en `s16le`). Avec le seul protocole `file`, elle échouerait ;
- **l'écran d'import** accepte déjà les `.webm` et les `.mkv` ;
- **W64** est le WAV des très longs enregistrements, au-delà de 4 Go.

Aucun de ces ajouts n'ouvre d'accès réseau : ffmpeg reste compilé avec `--disable-network` (P1).

## Décision
- **Protocoles** : `file` et `pipe`, aucun autre.
- **Formats lus** : ceux de l'ADR 0041, plus Matroska (WebM, MKV) et W64.
- **L'essai du paquet** (`scripts/essai-paquet.sh`) vérifie que ffmpeg n'a pas d'autre protocole en entrée que `file` et `pipe`. Chaque format, WebM compris, doit être lu par l'import de l'app, en direct et par un tube.

## Conséquences
- Les versions figées et la liste des composants sont dans `scripts/construction.toml`. Chaque composant est vérifié par `configure` avant la compilation : un nom inconnu arrête la construction.

## Alternatives écartées
- Garder seulement `file` : la transcription échouerait.
- Retirer WebM et MKV de l'écran d'import : un enregistrement fait dans un navigateur ne s'importerait plus.
