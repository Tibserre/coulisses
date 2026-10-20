# Relais : v0.33.1 publiée, 12b et 12e faits (pour « Pilotage » et « Alléger Coulisses »)

De : la conversation « 5 · Distribution et publication », le 2026-10-20. Aucune des deux n'était ouverte : ce relais tient lieu de message.

## Ce qui est publié
- **v0.33.1** est publiée (Latest sur GitHub, appcast en ligne), avec l'accord de l'utilisateur. Elle remplace la v0.33.0 : `publier.py` construit depuis l'étiquette, il fallait une version pour emporter l'élagage et le FLAC.
- **Vérifié** : 420 tests et 88 tests de l'interface ; essai du paquet complet (six étapes, FLAC compris) ; même signature que la 0.28.0 ; une séance faite par la 0.28.0 s'ouvre dans la v0.33.1.
- **Tailles** : DMG 88 Mo (773 Mo pour la 0.28.0) ; app installée 183 Mo.
- **Notes** : les sections v0.28.1 à v0.33.1 du `CHANGELOG.md` sont réécrites pour les utilisateurs ; celle de v0.33.1 résume tout depuis la 0.28.0.

## Pour Pilotage
- **Lot 11f** : v0.33.1 publiée.
- **Étape 12** : 12b et 12e faits.
- Deux lignes du plan sont périmées : 12b dit « retirer … stubs » (les `.pyi` restent, certaines bibliothèques chargent leurs modules depuis eux) ; 12e dit « mix et mix d'écoute refaits à la demande » (l'ADR 0046 les garde en FLAC, ≈ 1,16 Go gagné par heure de réunion).

## Pour Alléger Coulisses
- **12b** (`[elagage]` de `construction.toml`, chaque retrait listé, une liste périmée arrête la construction) : 15 dossiers de tests (6,9 Mo), pip (5,7 Mo), outils de la bibliothèque standard et Tcl/Tk (11,8 Mo), en-têtes C (0,5 Mo), soit 25 Mo retirés ; l'app passe de 229 à 183 Mo. Les `.pyi` restent. Le DMG reste en ULFO : ULMO gagnait 17 % mais était trois fois plus lent à créer, et le gain ne compte plus guère à 88 Mo.
- **12e** : le ffmpeg de l'app a `flac` **et** `pcm_s24le` (encodeur et format) : sans `s24le`, la preuve de `lossless.decoded_pcm_sha256` et `mixing.decode_to_wav` échouaient. L'essai du paquet fait passer une piste mono puis stéréo par `lossless.convert_file`. Vérification manuelle de l'ADR 0046 faite par l'utilisateur dans Coulisses (dév).
- **À faire chez toi** : `lossless.available()` ne teste que `flac`. Il devrait aussi tester l'encodeur `pcm_s24le` et le format `s24le`, pour qu'un ffmpeg incomplet dise « pistes gardées en WAV » plutôt qu'une erreur par séance.
- **Relevé d'après** : à ranger dans ce dossier si tu le veux, avec `scripts/mesurer-tailles.py --dmg ~/Coulisses/Publications/v0.33.1/Coulisses-0.33.1.dmg`.
