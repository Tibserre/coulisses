# 0010 — Un seul dossier visible : ~/Coulisses

Statut : Acceptée (2026-09-24). Remplace l'emplacement du code et des données de 0001. Précise 0009.

## Contexte
0001 séparait le code (`~/Code/coulisses`) des données (`~/Library/Application Support/Coulisses`, caché dans le Finder). 0009 a mis les modèles dans `~/Coulisses/Modèles`. Trois emplacements éloignés, dont un caché : l'utilisateur veut tout voir et gérer au même endroit.

## Décision
```
~/Coulisses/
  Code/          # ce dépôt : le seul dossier sous git
  Modèles/       # modèles téléchargés (0009)
  Données/       # données réelles : base, séances, audio, exécutions, banc
  Données-dev/   # données de développement
```
- **Un seul dépôt git**, sur `Code/`. `Modèles/` et `Données/` ne sont jamais versionnés.
- Chaque emplacement reste surchargeable : `COULISSES_DATA_DIR`, `COULISSES_MODELS_DIR`.
- L'organisation interne de `Données/` est celle de 0001 (`coulisses.db`, `sessions/<id>/sources`, `sessions/<id>/runs`, `bench/`).
- `~/Coulisses` n'est pas un dossier synchronisé : ni iCloud (qui ne synchronise que Bureau et Documents), ni OneDrive.
- Les garde-fous (`.claude/hooks/`, `settings.json`) protègent `~/Coulisses/Données/`, et l'ancien emplacement tant qu'il peut contenir des données.

## Conséquences
- Le dossier de données est visible dans le Finder : une suppression manuelle y est possible. L'app doit donc tolérer un fichier disparu (message clair, jamais de plantage silencieux, P8), comme pour les modèles (0009).
- Time Machine sauvegarde `~/Coulisses` par défaut. L'utilisateur peut en exclure `Modèles/`, qui se retélécharge.
- Le changement de dossier du dépôt demande de rouvrir la session Claude Code depuis `~/Coulisses/Code` (la variable `CLAUDE_PROJECT_DIR` est fixée au démarrage).

## Alternatives écartées
- Garder les données dans Application Support : emplacement standard de macOS, mais caché et éloigné du reste.
- Plusieurs dépôts git (code, configuration) : aucun besoin, un seul dépôt suffit.

## Précisé par l'ADR 0016 (2026-10-02)
`Code/` devient deux dépôts, `Moteur/` et `App/`, et s'ajoute `Environnements/`.
