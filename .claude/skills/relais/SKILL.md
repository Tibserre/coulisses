---
name: relais
description: Réécrit le carnet du rôle de la session Coulisses (état présent seulement) et, si quelque chose revient à un autre rôle, écrit un relais. À utiliser à la fin de chaque bloc de travail (une fusion, un arrêt, une attente de l'utilisateur), avant de fermer une session, ou quand un sujet sort de son territoire.
argument-hint: [rôle destinataire et sujet, si un relais est à écrire]
---

# Relais : $ARGUMENTS

Copie identique dans `Pilotage/`, `App/` et `Moteur/` (`.claude/skills/relais/`) : en modifier une, c'est modifier les trois.

## 1. Réécrire ton carnet
`~/Coulisses/Pilotage/roles/<ton rôle>.md` (Pilotage : `tableau-de-bord.md`). Tu le **réécris en entier**, tu n'ajoutes rien à la fin. 30 lignes au plus, avec ces sections :

```
# Carnet — <Rôle>

Mis à jour le AAAA-MM-JJ.

## Où on en est
<branches et worktrees en cours, ce qu'ils contiennent, ce qui n'est pas commité>

## Prochaines étapes
<3 à 5, dans l'ordre>

## Pièges
<ce qu'une session neuve doit savoir pour ne pas casser quelque chose ; une leçon durable va plutôt dans le CLAUDE.md du dépôt>

## Attend l'utilisateur
<essais, choix, accords ; « Rien pour l'instant. »>
```

- Ce qui est fini sort du carnet : git, `CHANGELOG.md`, les ADR et le plan le gardent.
- Pas de « fait le … », pas de liste de commits, pas de compte rendu.
- Jamais d'extrait de transcript, de nom de participant ni de contenu de `~/Coulisses/Données/`, ni ici ni dans un relais (ce dossier est un dépôt git).

## 2. Écrire un relais, si quelque chose revient à un autre rôle
`~/Coulisses/Pilotage/relais/AAAA-MM-JJ-<ton rôle>-pour-<rôle>-<sujet>.md`, 20 lignes au plus :
- **Ce qui est demandé**, précis et vérifiable (fichiers, fonctions, critère de fin).
- **Pourquoi**, en une ou deux phrases.
- **Ce qui est déjà fait de ton côté**, et sur quelle branche.
- **Ce qui attend l'utilisateur**, s'il y a lieu.

Le destinataire le supprimera une fois traité. Si la session du destinataire est ouverte, dis à l'utilisateur qu'un relais l'attend (ou envoie-le-lui si tu peux joindre la session).

## 3. Sauvegarder
N'ajoute que tes fichiers, jamais `add -A` (une autre session écrit peut-être son carnet) : `git -C ~/Coulisses/Pilotage add roles/<rôle>.md relais/<ton relais>`, puis `git -C ~/Coulisses/Pilotage commit -m "chore(<rôle>): <ce qui a changé>"`. Si git signale `index.lock`, une autre session commite : attends quelques secondes et recommence.
