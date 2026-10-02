---
name: adr
description: Consigne une décision d'architecture ou de produit Coulisses dans docs/decisions/ (nouvelle fiche ou remplacement d'une fiche existante) et met à jour l'index. À utiliser dès qu'une décision structurante est prise ou validée par l'utilisateur, ou qu'une décision existante doit changer.
argument-hint: <titre de la décision>
---

# ADR : $ARGUMENTS

1. Liste les fiches existantes : `ls docs/decisions/`. Prends le numéro suivant, sur 4 chiffres.
2. Vérifie qu'aucune fiche acceptée ne dit déjà le contraire. Si c'est le cas, la nouvelle fiche **remplace** l'ancienne : dans l'ancienne, ne modifie que la ligne de statut (`Statut : Remplacée par 00XX`) et laisse le reste intact.
3. Crée `docs/decisions/00XX-<titre-en-kebab-case>.md` avec ce gabarit :

```markdown
# 00XX — <Titre>

Statut : Proposée | Acceptée (<AAAA-MM-JJ>)

## Contexte
<Le problème, les contraintes, les principes concernés (P1…P8). Faits, pas d'opinions.>

## Décision
<Ce qui est décidé, formulé de façon vérifiable.>

## Conséquences
<Ce que ça implique, ce que ça coûte, ce qu'il faudra surveiller.>

## Alternatives écartées
<Option : raison de l'écart.>
```

4. Statut **Acceptée** seulement si l'utilisateur l'a validée dans la conversation ; sinon **Proposée**.
5. Choix de modèle : cite le rapport du banc (chemin et date) dans le contexte.
6. Ajoute la ligne à l'index `docs/decisions/README.md`. Si la décision tranche une question de `docs/produit/questions-ouvertes.md`, retire-la de ce fichier.
7. Moins de 60 lignes. Pas de remplissage.
