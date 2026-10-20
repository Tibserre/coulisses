# 0052 — Ne garder que les trois dernières copies de la base

Statut : Acceptée (2026-10-20). Le choix est celui de l'utilisateur (étape 13, revue de l'expérience : « garder seulement les 3 dernières copies ») ; la migration 0010 qu'il entraîne a été validée par l'utilisateur le même jour. Remplace, dans l'ADR 0018 (point 3), la règle selon laquelle l'application ne supprime une copie de la base que sur demande explicite.

## Contexte
Avant chaque série de migrations, l'application copie la base dans `sauvegardes/` (`coulisses-avant-XXXX-<date>.db`, ADR 0018). Elle n'en supprimait aucune : une copie de plus à chaque version qui change le schéma. Le 2026-10-20, Données-dev en comptait 8, pour 2,1 Mo en tout (contre 972 Mo d'audio). L'utilisateur ne veut pas que l'app « devienne ultra lourde à force de copies » et a choisi de garder les 3 dernières.

Une copie sert à revenir en arrière après une mise à jour (ADR 0029) : seules les plus récentes servent. Le texte d'une séance supprimée en est déjà effacé (ADR 0029).

Principes en jeu : P5 (rien de perdu lors d'une relance : une copie n'est pas une relance, la base en place reste entière), P8 (aucune suppression sans décision explicite et visible).

## Décision
1. **Après chaque nouvelle copie réussie**, au démarrage, une fois les migrations faites, l'application ne garde que les **3 dernières copies**, celle qui vient d'être faite toujours comprise, quelle que soit sa date. Les plus anciennes (d'après la date de leur nom) sont supprimées, avec le journal que SQLite aurait laissé à côté.
2. Seuls les fichiers nommés comme les fait la migration sont concernés : un autre fichier de `sauvegardes/` n'est jamais touché ni compté, dont la copie que `scripts/rapatrier-donnees.py` garde de la base qu'il remplace (`coulisses-avant-rapatriement-…`). Les copies s'ordonnent par la date de leur nom, jamais par leur nom.
3. **Chaque suppression est écrite dans le journal des suppressions avant d'avoir lieu**, sous le genre `backup_pruning` (« Anciennes copies de la base ») : date, fichiers, tailles. Si le journal ne peut pas être écrit, rien n'est supprimé.
4. **Un échec se voit et n'empêche rien** : une copie qui ne peut pas être effacée est notée dans le journal (`problems`) et dans les problèmes du démarrage ; la migration est faite, le service démarre.
5. Migration 0010 : `deletion_log` accepte `backup_pruning`, et son `session_id` est vide pour ce genre seulement (une copie de la base n'appartient à aucune séance).

## Conséquences
- La décision explicite est celle de l'utilisateur ; le journal rend chaque suppression visible (P8). Aucune copie ne disparaît sans ligne au journal.
- Le dossier des sauvegardes reste petit et borné. La liste des copies, dans les Réglages, en montre au plus trois, plus les autres fichiers `.db` qu'on y aurait mis.
- Revenir plus de trois changements de schéma en arrière n'est plus possible par ces copies. Time Machine reste la sauvegarde des données (ADR 0001).
- À la première version qui contient ce changement, la migration 0010 fait une copie, puis les copies en trop (8 sur Données-dev) sont supprimées d'un coup, en une ligne du journal.

## Alternatives écartées
- Tout garder (règle de l'ADR 0018) : le dossier grossit à chaque version, sans usage pour les anciennes copies.
- Garder les copies d'une durée (30 jours…) : plusieurs migrations rapprochées les garderaient toutes, une longue pause n'en garderait aucune.
- Supprimer sur demande seulement, depuis les Réglages : l'utilisateur ne veut pas avoir à y penser.
- Noter ces suppressions dans le seul journal du service : invisible depuis l'app (P8).
