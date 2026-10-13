# Coulisses

Assistant de débrief, 100 % local, pour une troupe d'impro comme pour une équipe : enregistrer une séance, savoir qui a dit quoi, obtenir un compte rendu en français.

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

Le service écoute sur `http://127.0.0.1:8765` et ouvre l'interface. Les séances vont dans `~/Coulisses/Données`. Ctrl-C arrête le service ; un traitement en cours reprend au lancement suivant.

**Pour développer** (ADR 0040), jamais sur les vraies séances :

```bash
uv run coulisses-app --dev
```

Le service écoute alors sur le port 8766, sur `~/Coulisses/Données-dev` (ou le dossier donné par `COULISSES_DATA_DIR`), et refuse le dossier des données réelles. `scripts/installer-lanceur.sh --dev` installe l'app « Coulisses (dév) », icône graphite, qui le lance depuis le dépôt ; elle vit à côté de Coulisses sans partager ni service, ni données, ni permissions.

Pendant le développement de l'interface : `cd web && npm run dev` (port 5173, l'API passe par le service de dév ; `COULISSES_PORT` en vise un autre).

## Construire l'app à donner

Pour les amis (ADR 0040, 0041) : une `Coulisses.app` autonome, avec son Python, l'app, le moteur, l'interface, ffmpeg, ffprobe et uv. La première fois, `--telecharger` va chercher l'archive de ffmpeg et le Python autonome (versions et empreintes dans `scripts/construction.toml`) ; ensuite, rien ne passe plus par le réseau.

```bash
uv run python scripts/construire.py --telecharger
scripts/essai-paquet.sh dist/Coulisses.app
```

L'essai lance le service de l'app comme son lanceur, réseau coupé et sans Homebrew, sur un dossier temporaire, et traite une séance synthétique avec les vrais modèles.

## Publier une version

Depuis une étiquette `vX.Y.Z` (née d'une fusion dans `main`), en trois temps (ADR 0040) :

```bash
uv run python scripts/publier.py vX.Y.Z              # prépare tout ici, n'envoie rien
uv run python scripts/publier.py vX.Y.Z --envoyer    # puis la pré-version sur GitHub
uv run python scripts/publier.py --confirmer vX.Y.Z  # les amis la reçoivent
```

Préparer passe tous les tests de l'étiquette, construit et signe l'app, l'essaie, vérifie qu'elle garde l'exigence désignée et ouvre la base de la version publiée avant, puis fait le DMG, sa signature EdDSA, les notes (tirées de `CHANGELOG.md`) et l'appcast signé, dans `~/Coulisses/Publications/vX.Y.Z`. La pré-version n'a pas d'appcast : vous l'installez et vous en servez ; confirmer vérifie que son DMG est celui préparé, puis publie l'appcast. Le dépôt doit être public pour que les apps des amis le lisent.

## Tests

```bash
uv run pytest                 # service, avec les faux moteurs du moteur (secondes)
uv run pytest -m slow         # la vraie chaîne sur un enregistrement synthétique (≈ 1 min)
uv run ruff check . && uv run pyright
cd web && npm test && npm run typecheck && npm run lint
```

Après un clonage : `git config core.hooksPath .githooks` active les garde-fous (données de séance hors de git, messages de commit, versions automatiques).
