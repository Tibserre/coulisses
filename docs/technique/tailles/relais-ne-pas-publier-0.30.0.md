# Relais urgent : ne pas publier v0.30.0 (pour « Distribution et publication » et « Pilotage »)

De : la conversation « Alléger Coulisses », le 2026-10-19.

**La v0.30.0 (moteur v1.8.0) ne doit pas être publiée.** En sortant torch du Python de l'app, le moteur v1.8.0 a aussi changé la transcription Qwen3 : transformers calcule le spectre audio avec NumPy au lieu de PyTorch, et les arrondis diffèrent. Sur les repas du banc ESLO2, le taux d'erreur passe de 41,0 % à 41,3 %. Les tests de l'app ne pouvaient pas le voir : ils comparent deux entrées, pas deux versions du moteur.

Le moteur l'a corrigé en v1.8.1 et v1.8.2 : Qwen3 tourne aussi dans l'environnement `torch`, et la sortie redevient identique, octet pour octet, à celle de la chaîne retenue. L'app passe en v1.8.2 sur la branche `fix/moteur-1.8.2`. Elle sera fusionnée (sans doute en v0.30.1) une fois le test lent et l'essai du paquet passés, dès que l'environnement `torch` de la v1.8.2 sera installé sur ce Mac.

Publiez la version suivante, jamais la v0.30.0. La note de version de la v0.30.1 pourra dire « corrige la justesse de la transcription de la v0.30.0, jamais publiée ».

## Mise à jour : v0.30.1 est la version à publier (2026-10-19)

- **Fusionnée** : `b0595ec`, moteur v1.8.2. La transcription redevient identique à la chaîne retenue, d'après le Moteur. L'app d'essai fait 229 Mo installée et son DMG 112 Mo, contre 1,99 Go et 773 Mo pour la référence v0.28.0 ([relevé](2026-10-19-v0.30.0-moteur-v1.8.2.md)).
- **Vérifié** : 416 tests et 2 tests lents passent. L'essai du paquet passe ses étapes 1 à 4 (traitement complet réseau coupé), rien n'est écrit dans l'app et la signature est intacte. **L'étape 5 (aucun accès réseau sans accord) n'a pas pu passer ici** : la Coulisses publiée était ouverte. `publier.py` la passe de toute façon, une fois cette Coulisses fermée.
- **Chez un ami** : l'environnement `torch` (≈ 1,3 Go) sert maintenant à la transcription, à l'alignement et au filet pyannote. Il s'installe depuis Réglages > Transcription. Les notes de version doivent le dire.
- **Pilotage** : 12c est entièrement fait (12c-1 et 12c-2). 12d est mesuré : Qwen3 en 8 bits garde la même justesse (41,03 % contre 41,04 %), pour −2,2 Go et un calcul 1,7 fois plus rapide. Le 4 bits est écarté. La distribution du modèle 8 bits reste à trancher par l'utilisateur, et wav2vec2 en demi-précision est en mesure.
