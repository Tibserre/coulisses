# Coulisses

Assistant de débrief pour une troupe d'impro, 100 % local : enregistrer une séance, savoir qui a dit quoi, obtenir un compte rendu en français.

Ce dépôt contient **l'application**. Le traitement de l'audio (transcription, alignement, diarisation, attribution) est fait par **le moteur**, dépôt `coulisses-moteur`, utilisé par version (`vX.Y.Z`) et par son contrat.

- Produit : [`docs/produit/spec-v1.md`](docs/produit/spec-v1.md)
- Décisions : [`docs/decisions/`](docs/decisions/README.md)
- Direction artistique : [`docs/produit/direction-artistique.md`](docs/produit/direction-artistique.md)
- Questions ouvertes : [`docs/produit/questions-ouvertes.md`](docs/produit/questions-ouvertes.md)
- Versions : [`CHANGELOG.md`](CHANGELOG.md), publiées automatiquement à chaque fusion dans `main`.

État : l'application est à construire, à partir de la spécification.

Après un clonage : `git config core.hooksPath .githooks` active les garde-fous (données de séance hors de git, messages de commit, versions automatiques).
