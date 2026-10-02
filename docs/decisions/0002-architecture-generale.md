# 0002 — Architecture générale

Statut : Acceptée (2026-09-24)

## Contexte
Traitements ML lourds (plusieurs modèles de plusieurs Go, exécutions de plusieurs heures), interface riche (relecture synchronisée avec l'audio), un seul utilisateur sur un seul Mac. Electron n'est justifié que par un besoin natif avéré.

## Décision
- **Service local Python** (FastAPI) sur `127.0.0.1` : API pour l'interface, file de tâches, captation (voir 0005), purge.
- **Worker** : chaque exécution d'étape tourne dans un **sous-processus dédié**. Le modèle est chargé, utilisé, puis libéré avec le processus. Un crash (mémoire, Metal) n'emporte pas le service ; la mémoire max est mesurée proprement ; deux gros modèles ne cohabitent pas.
- **File de tâches persistée dans SQLite** (pas de Redis ni de Celery). Au redémarrage, les exécutions `running` orphelines repassent en file.
- **Stockage** : SQLite (mode WAL) + un dossier par séance (0001). Les sorties d'étapes sont des fichiers (JSON, RTTM, WAV) ; la base indexe et relie.
- **Interface** : application web servie par le service, installable en PWA (voir 0007). Tous les assets sont locaux.
- **Génération** : Ollama en local, via un **unique module client** dans `prompting/`.
- **Outillage Python** : `uv`, Python 3.12 (le Python système 3.14 est trop récent pour l'écosystème ML), `ruff` (format + lint), `pyright` (types), `pytest`.

## Organisation du dépôt
```
engine/                  # paquet Python `coulisses`
  src/coulisses/
    api/                 # FastAPI (127.0.0.1)
    capture/             # captation audio (0005)
    worker/              # orchestration des étapes, sous-processus
    stages/              # contrats des étapes (entrées, sorties, capacités)
    engines/             # implémentations interchangeables, une par moteur
    prompting/           # assemblage des prompts + seul client LLM
    storage/             # SQLite, dossiers de séance, corrections
    retention/           # conservation et purge
    models/              # téléchargement explicite des modèles (seul accès Internet)
  tests/
bench/                   # banc d'essai (DER, WER, temps, mémoire)
config/                  # profils (TOML), actions fournies (prompts en .md)
web/                     # interface
docs/
```

## Alternatives écartées
- Electron / Tauri d'emblée : pas de besoin natif identifié (captation faite par le service).
- Modèles chargés dans le processus du service : fuite mémoire, un crash Metal tue tout.
- Celery/Redis : un service de plus pour un seul utilisateur.
