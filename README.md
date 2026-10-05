# Coulisses

Assistant de débrief pour une troupe d'impro, 100 % local : enregistrer une séance, savoir qui a dit quoi, obtenir un compte rendu en français.

Ce dépôt contient **l'application**. Le traitement de l'audio (transcription, alignement, diarisation, attribution) est fait par **le moteur**, dépôt `coulisses-moteur`, utilisé par version (`vX.Y.Z`) et par son contrat.

- Produit : [`docs/produit/spec-v1.md`](docs/produit/spec-v1.md)
- Décisions : [`docs/decisions/`](docs/decisions/README.md)
- Direction artistique : [`docs/produit/direction-artistique.md`](docs/produit/direction-artistique.md)
- Questions ouvertes : [`docs/produit/questions-ouvertes.md`](docs/produit/questions-ouvertes.md)
- Versions : [`CHANGELOG.md`](CHANGELOG.md), publiées automatiquement à chaque fusion dans `main`.

État : étape 1 du [plan](docs/produit/plan-v1.md) (importer, traiter, lire).

## Lancer

Une fois, après un clonage :

```bash
uv sync
cd web && npm install && npm run build
```

Le moteur (étiquette dans `pyproject.toml`) a besoin de ses modèles et de l'environnement de DiariZen : `uv run coulisses-models installer-environnement diarizen`, puis `uv run coulisses-models telecharger <clé>` pour chaque modèle (`uv run coulisses-models catalogue`).

```bash
uv run coulisses-app
```

Le service écoute sur `http://127.0.0.1:8765` et ouvre l'interface. Les séances vont dans `~/Coulisses/Données`. Pour développer : `COULISSES_DATA_DIR=~/Coulisses/Données-dev uv run coulisses-app`. Ctrl-C arrête le service ; un traitement en cours reprend au lancement suivant.

Pendant le développement de l'interface : `cd web && npm run dev` (port 5173, l'API passe par le service).

## Tests

```bash
uv run pytest                 # service, avec les faux moteurs du moteur (secondes)
uv run pytest -m slow         # la vraie chaîne sur un enregistrement synthétique (≈ 1 min)
uv run ruff check . && uv run pyright
cd web && npm test && npm run typecheck && npm run lint
```

Après un clonage : `git config core.hooksPath .githooks` active les garde-fous (données de séance hors de git, messages de commit, versions automatiques).
