# 0041 — ffmpeg et ffprobe embarqués dans Coulisses.app, compilés sur ce Mac (audio seul, LGPL, sans réseau)

Statut : Acceptée (2026-10-13, choix de l'utilisateur : « compilé sur ce Mac »). Précise l'ADR 0040, dont la liste de ce que contient le .app oubliait ffmpeg.

## Contexte
L'app lit un fichier importé avec `ffprobe`. Le moteur, lui, décode l'audio avec `ffmpeg` et `ffprobe`, appelés par leur nom dans le PATH ; son README les compte parmi ses prérequis. Les amis n'ont pas ffmpeg. Celui de Homebrew ne peut pas être embarqué : il dépend des bibliothèques partagées de Homebrew, et il est compilé sous GPL, alors que l'app est publiée sous MIT. Depuis le lot 11b, le service met le dossier `bin/` du .app en tête du PATH, pour lui et pour le moteur.

## Décision
- **ffmpeg et ffprobe sont compilés sur ce Mac** depuis l'archive officielle de ffmpeg.org. Pour chaque version : le numéro, l'adresse et l'empreinte SHA-256 de l'archive sont écrits dans le dépôt, et toute autre archive est refusée. L'archive est téléchargée une fois, à la construction, jamais à l'exécution (P1).
- **Version minimale** :
  - statique, pour Apple Silicon, macOS 14.4 au moins ;
  - sous LGPL, sans `--enable-gpl` ni `--enable-nonfree` ;
  - aucun accès réseau (`--disable-network`) et un seul protocole, `file` ;
  - seulement les démultiplexeurs et décodeurs audio des formats d'enregistrement courants (WAV, AIFF, CAF, M4A et AAC, MP3, FLAC, Ogg et Opus, ainsi que la piste audio d'un MP4 ou d'un MOV), et le rééchantillonnage.
- Le script de construction (lot 11c) les met dans `Contents/Resources/bin/`, signés comme le reste. Leur licence et la ligne de configuration vont avec les licences des dépendances.
- Un format qu'ils ne savent pas lire est refusé à l'import avec le message existant (« pas lisible par ffmpeg »), jamais en silence (P8).

## Conséquences
- Chaque outil pèse quelques Mo dans le .app.
- Les tests de l'essai du paquet (lot 11c) importent un fichier de chaque format de la liste, fabriqué au moment du test.
- Monter de version de ffmpeg demande de changer la version et l'empreinte, puis de reconstruire et de repasser l'essai du paquet.
- Sur ce Mac, le développement continue avec le ffmpeg de Homebrew.

## Alternatives écartées
- Des binaires statiques faits par des tiers : il faudrait leur faire confiance, ils sont en général sous GPL et pèsent environ 80 Mo.
- Demander aux amis d'installer Homebrew et ffmpeg : il faudrait le Terminal, ce qui contredit « sans autre outil » (ADR 0040).
