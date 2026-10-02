---
name: jalon
description: Prépare un point de validation pour l'utilisateur (choix de modèle, schéma de données, contrat d'étape ou de moteur, dépendance lourde, fin d'une étape du plan). À utiliser quand CLAUDE.md impose une validation, ou avant d'annoncer qu'un lot de travail est terminé.
argument-hint: <sujet du jalon>
---

# Jalon : $ARGUMENTS

L'utilisateur valide aux jalons ; entre deux jalons, tu avances seul. Ce skill produit un point court et décidable.

## État du dépôt
- Branche : !`git branch --show-current`
- Depuis main : !`git log --oneline main..HEAD 2>/dev/null | head -20`
- Non commité : !`git status --short | head -20`

## Préparer
1. Fais relire le diff par l'agent `gardien-principes`. Corrige ce qu'il signale **avant** le jalon, ou mentionne-le explicitement.
2. Lance tous les tests de l'application. Rapporte le résultat exact, même en cas d'échec.
3. Si le jalon porte sur un modèle ou un réglage, joins le rapport du banc (`/banc-essai`).

## Présenter à l'utilisateur (en français, en moins de 25 lignes)
- **Ce qui est fait**, en 3 à 5 puces, du point de vue du produit (pas de liste de fichiers).
- **Preuves** : tests (x réussis / y), mesures clés, et ce qui n'a **pas** été vérifié.
- **La décision attendue**, formulée comme une question fermée, avec ta recommandation et l'alternative. Utilise AskUserQuestion si les options sont nettes.
- **Risques ou dettes** introduits, s'il y en a.

Après validation : ADR si la décision est structurante (`/adr`), mise à jour de la spec ou des questions ouvertes, et la ligne « Phase actuelle » de `CLAUDE.md` si la phase change.
