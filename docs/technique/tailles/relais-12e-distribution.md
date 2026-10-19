# Relais : lot 12e, l'encodeur FLAC du ffmpeg embarqué (pour « Distribution et publication »)

De : la conversation « Alléger Coulisses », le 2026-10-19. ADR 0046 acceptée par l'utilisateur ce jour.

## Ce qui est demandé
Dans `scripts/construction.toml`, section `[ffmpeg]`, ajouter l'encodeur `flac` à `encoders` et le format `flac` à `muxers`. C'est ton territoire : je n'y touche pas.

Ensuite, `scripts/essai-paquet.sh` vérifie que le ffmpeg de l'app fait l'aller-retour suivant :
- il encode en FLAC un WAV 24 bits 48 kHz, mono puis stéréo (`-c:a flac`) ;
- il relit ce FLAC ;
- il rend les mêmes échantillons, avec une empreinte du PCM identique.

## Pourquoi
L'ADR 0046 garde chaque piste enregistrée par l'app en FLAC une fois l'enregistrement fini. Le WAV n'est supprimé qu'après preuve que les échantillons sont identiques. Le gain mesuré est de −44 % par piste, soit 518 → ≈ 290 Mo par heure. L'app encodera avec le ffmpeg qu'elle embarque (ADR 0041), ce qui évite une dépendance native de plus (soundfile ou libsndfile).

## Contrat, garde-fous
- On reste en LGPL, sans réseau, avec les protocoles `file` et `pipe` seulement (ADR 0041, 0042). L'encodeur FLAC natif de ffmpeg est sous LGPL.
- La liste des composants est toujours vérifiée par `configure` avant la compilation.
- Gain de taille attendu : quelques centaines de ko au plus pour `ffmpeg`. À mesurer avec `scripts/mesurer-tailles.py --app …`.

## La suite
Tant que l'encodeur manque, je code et teste avec le ffmpeg de Homebrew en développement. L'app publiée ne doit pas sortir avec la conversion FLAC active tant que son ffmpeg ne sait pas encoder. Le code refusera de supprimer un WAV qu'il n'a pas pu convertir, et l'erreur sera visible (P8). Préviens « Alléger Coulisses », ou Pilotage, quand c'est fusionné.
