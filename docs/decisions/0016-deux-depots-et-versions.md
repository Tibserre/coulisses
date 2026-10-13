# 0016 — Deux dépôts, un moteur versionné, des versions automatiques

Statut : Acceptée (2026-10-02 : l'utilisateur veut un dépôt qui soit juste l'application, un moteur qu'il peut améliorer et publier par versions, et des versions propres et automatiques). Dossiers chez un ami, Python et cache de uv : précisés par 0040.

## Contexte
Le moteur est fixé (ADR 0014) et l'atelier n'est pas le produit (ADR 0015). Le produit va être construit dans un dépôt propre. Il doit utiliser une version précise du moteur, et le moteur doit pouvoir s'améliorer sans casser l'application.

## Décision
- **Deux dépôts, sans dépôt « global » ni sous-module** :
  - `coulisses-moteur` (`~/Coulisses/Moteur`) : le moteur (`engine/`), son atelier (`atelier/` : banc, service, interface d'atelier) et la documentation du moteur (évaluation, ADR techniques). Le banc reste avec le moteur : il mesure son code exact.
  - `coulisses` (`~/Coulisses/App`) : l'application seule, et la documentation produit (spécification, user stories, ADR produit, glossaire, direction artistique). Elle dépend du moteur **par une étiquette de version** (`vX.Y.Z`).
- **Dossier unique `~/Coulisses`** (précise l'ADR 0010) : `Moteur/`, `App/` (les deux dépôts), `Modèles/`, `Environnements/` (environnements isolés des moteurs), `Données/`, `Données-dev/`.
- **Le moteur est installable par version** :
  - sa configuration (catalogue des modèles, profils dont la chaîne retenue) est livrée dans le paquet (`coulisses/config/`) ; `COULISSES_CONFIG_DIR` peut en fournir une autre ;
  - l'environnement isolé de DiariZen (ADR 0013) est un projet uv livré dans le paquet (`coulisses/envs/diarizen/`), installé explicitement (`coulisses-models installer-environnement diarizen`) dans `~/Coulisses/Environnements/diarizen-<empreinte du verrou>` ; chaque version du moteur retrouve celui de son verrou ;
  - un moteur installé hors de son dépôt écrit dans la provenance sa version et l'empreinte de ses fichiers (P7).
- **Versions automatiques** (SemVer), dans les deux dépôts :
  - messages de commit Conventional Commits, description en français (`feat(portée): …`), vérifiés par un hook ;
  - à chaque fusion dans `main`, `scripts/release.py` calcule la version suivante, met à jour les fichiers de version et `CHANGELOG.md`, commite `chore(version): vX.Y.Z` et pose l'étiquette ;
  - moteur : `feat` = mineure, `fix`/`perf` = corrective, `!` = majeure ; modifier `engine/schemas/` (le contrat) exige `!` ou une ligne `Contrat compatible:` ;
  - une amélioration du moteur n'est publiée qu'après le banc qui la prouve ; l'application monte de version de moteur en changeant une ligne, puis passe ses tests.

## Conséquences
- Précise les ADR 0004 (campagnes dans `atelier/bench/config/`), 0009 et 0014 (catalogue et profils dans `coulisses/config/`), 0010 (dossiers), 0012 et 0013 (environnements dans `~/Coulisses/Environnements/`, un par verrou ; les versions figées du banc l'installent hors ligne).
- Première version publiée du moteur : `v1.0.0`.
- Pousser vers un dépôt distant reste une décision de l'utilisateur.
