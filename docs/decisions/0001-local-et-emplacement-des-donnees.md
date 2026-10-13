# 0001 — 100 % local ; code et données séparés

Statut : Acceptée (2026-09-24). Emplacements du code, des données et des modèles **remplacés par 0009 et 0010** ; le reste (hors ligne, séparation code/données, organisation interne) tient toujours ; hors ligne : exception des mises à jour ajoutée par 0040.

## Contexte
Principe P1 : aucune donnée ne sort de la machine. Le projet a démarré dans un dossier OneDrive d'entreprise, synchronisé vers le cloud, qui abîme aussi les bases SQLite et gère mal les `.venv`, `node_modules` et `.git`.

## Décision
- **Code** : `~/Code/coulisses`, versionné avec git, sauvegardé sur un dépôt GitHub **privé**. Le dépôt ne contient **jamais** d'audio, de transcript réel, de base de données ni de modèle (`.gitignore` + hook git `pre-commit`).
- **Données** : `~/Library/Application Support/Coulisses/`, jamais synchronisé.
  ```
  Coulisses/
    coulisses.db                  # SQLite : métadonnées, file, corrections, index plein texte
    sessions/<session_id>/
      sources/<source_id>.<ext>   # originaux, tels quels
      runs/<run_id>/              # une exécution d'étape : sorties (JSON/RTTM/WAV dérivé) + provenance.json
    models/                       # remplacé par 0009 : les modèles sont dans ~/Coulisses/Modèles
    bench/                        # résultats du banc d'essai
  ```
- **Emplacement surchargeable** par la variable `COULISSES_DATA_DIR`. Développement et tests n'utilisent **jamais** le dossier réel : tests → dossier temporaire, développement → `~/Library/Application Support/Coulisses-dev`.
- **Hors ligne à l'exécution** : le service démarre avec `HF_HUB_OFFLINE=1` et `TRANSFORMERS_OFFLINE=1`. Le seul code autorisé à accéder à Internet est la commande explicite de téléchargement de modèles. Le seul accès réseau local est Ollama sur `127.0.0.1`. Le service n'écoute que sur `127.0.0.1`.
- **Vérification** : un test automatisé exécute le parcours complet avec le réseau coupé.

## Conséquences
- Les modèles déjà présents dans `~/.cache/huggingface` (téléchargés par OpenWhispr) sont re-téléchargés dans le dossier des modèles (0009) pour que l'app ne dépende pas d'une autre app.
- La sauvegarde des données relève de Time Machine : l'app ne sauvegarde pas elle-même.

## Alternatives écartées
- Tout dans OneDrive : contraire à P1.
- Données dans le dépôt (`./data`) : risque de commit accidentel, mélange code/données.

