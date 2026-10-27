---
name: reprendre
description: Remet en route une session Coulisses dans son rôle (Pilotage, Moteur, Service, Interface, Rédaction, Distribution) à partir de son carnet, de ses relais et de l'état git, sans rien supposer de conversations passées. À utiliser au début de chaque session, ou quand une conversation a été perdue.
argument-hint: <rôle>
---

# Reprendre le rôle : $ARGUMENTS

Copie identique dans `Pilotage/`, `App/` et `Moteur/` (`.claude/skills/reprendre/`) : en modifier une, c'est modifier les trois.

Rôles et fichiers : pilotage → `tableau-de-bord.md` ; moteur, service, interface, distribution → `roles/<rôle>.md` ; rédaction → `roles/redaction.md`. Tout est sous `~/Coulisses/Pilotage/`.

## 1. Lire, dans cet ordre
1. `~/Coulisses/Pilotage/organisation.md`, s'il n'est pas déjà dans ton contexte : ton territoire et les règles.
2. Ton carnet.
3. Les relais qui te sont adressés : `ls ~/Coulisses/Pilotage/relais/` (le nom du fichier contient `pour-<rôle>`).
4. Le `CLAUDE.md` du dépôt où tu travailles.

## 2. Vérifier l'état réel
Le carnet peut avoir du retard ; git a raison. Pour chaque branche ou worktree cités dans le carnet :
- `git worktree list` et `git log --oneline main..<branche>` ;
- `git -C <worktree> status` : ce qui n'est pas commité, une fusion ou un rebase arrêté en cours (git le signale en tête).

Ne modifie rien dans un worktree avant d'avoir compris ce qui s'y faisait.

## 3. Traiter les relais
Pour chaque relais qui t'est adressé : réécris d'abord ton carnet avec ce qui reste à faire, puis enregistre dans **un seul commit** le carnet et la suppression du relais (`git -C ~/Coulisses/Pilotage rm relais/<fichier>`, `git add roles/<rôle>.md`, commit). Jamais la suppression sans le carnet : la tâche ne doit pas survivre seulement dans l'historique. S'il est faux ou s'il sort de ton territoire, dis-le à l'utilisateur au lieu de le supprimer.

## 4. Présenter à l'utilisateur (10 lignes au plus)
- Où en est le rôle, en une phrase.
- Ce qui ne colle pas entre le carnet et git, s'il y a lieu.
- Ce qui attend l'utilisateur.
- La prochaine étape que tu proposes. Ou, si le brief de la session donne déjà une tâche, commence-la.

Si le carnet a changé à l'étape 2, réécris-le (`/relais`).
