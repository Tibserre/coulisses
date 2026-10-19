# Relais urgent : ne pas publier v0.30.0 (pour « Distribution et publication » et « Pilotage »)

De : la conversation « Alléger Coulisses », le 2026-10-19.

**La v0.30.0 (moteur v1.8.0) ne doit pas être publiée.** En sortant torch du Python de l'app, le moteur v1.8.0 a aussi changé la transcription Qwen3 : transformers calcule le spectre audio avec NumPy au lieu de PyTorch, et les arrondis diffèrent. Sur les repas du banc ESLO2, le taux d'erreur passe de 41,0 % à 41,3 %. Les tests de l'app ne pouvaient pas le voir : ils comparent deux entrées, pas deux versions du moteur.

Le moteur l'a corrigé en v1.8.1 et v1.8.2 : Qwen3 tourne aussi dans l'environnement `torch`, et la sortie redevient identique, octet pour octet, à celle de la chaîne retenue. L'app passe en v1.8.2 sur la branche `fix/moteur-1.8.2`. Elle sera fusionnée (sans doute en v0.30.1) une fois le test lent et l'essai du paquet passés, dès que l'environnement `torch` de la v1.8.2 sera installé sur ce Mac.

Publiez la version suivante, jamais la v0.30.0. La note de version de la v0.30.1 pourra dire « corrige la justesse de la transcription de la v0.30.0, jamais publiée ».
