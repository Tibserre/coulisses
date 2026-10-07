# 0018 — Schéma de données : SQLite fait foi, les exécutions restent des fichiers

Statut : Acceptée (2026-10-05). Tranche la question ouverte Q8. La troupe devient l'espace (ADR 0020).

## Contexte
Le moteur (`coulisses-traiter`) range une séance dans un `session.json` et un dossier par exécution. L'application a besoin de plus : troupe, présents, corrections, phases, notes, résumés, file de traitement, conservation, recherche. Le schéma doit tenir N sources (ADR 0006), garder les corrections à part des sorties (P5), ne rien perdre en silence (P8), et rester lisible après la purge. Le 2026-10-05, l'utilisateur a validé les principes 1 à 4 ci-dessous. Il ne veut pas reprendre dans l'application les séances déjà traitées par l'atelier.

## Décision
1. **La base SQLite (mode WAL) fait foi pour l'application.** Les sorties des exécutions restent des fichiers immuables (`runs/<run_id>/`), que la base indexe et relie. L'application n'écrit pas de `session.json`. Elle garde l'arborescence du moteur (`sessions/<id>/sources/`, `sessions/<id>/runs/`).
2. **Identifiant de séance stable, sans le titre** : `AAAAMMJJ-HHMMSS-xxxx`, qui sert aussi de nom de dossier. Le titre est une colonne, générée puis modifiable.
3. **Tout le modèle V1 est fixé maintenant** (`docs/technique/schema-donnees.md`). Ses tables sont créées au fil des étapes, par des migrations numérotées qui ne vont que vers l'avant. Chaque migration est précédée d'une copie de la base dans `sauvegardes/`, que l'application ne supprime que sur demande explicite de l'utilisateur.
4. **Les corrections forment un journal où l'on ne fait qu'ajouter** (`edit`). Chaque correction désigne l'exécution corrigée et porte ses temps mesurés, qui servent au report. Annuler ajoute une entrée. La vue corrigée est recalculée, jamais stockée comme vérité.
5. **Les étapes de l'application** (phases, titre, résumés) sont aussi des exécutions : un dossier de même forme, avec la provenance (P7). Une génération y garde le prompt envoyé mot pour mot.
6. **La file de traitement est une table** (`job`). À la fermeture, l'application arrête ses étapes par `stop_all` (moteur v1.2.0). Après un plantage, elle clôt au redémarrage les exécutions inachevées par `close_interrupted` : le moteur les enregistre en échec (`Interrupted`), sans perdre leur dossier. La tâche reprend ensuite, en réutilisant les exécutions réussies. Cela précise la règle de l'ADR 0002 (« les exécutions orphelines repassent en file ») : une exécution finie n'est jamais réécrite, c'est la tâche qui repasse en file.
7. **Les suppressions sont tracées** (`deletion_log`, sans clé étrangère, pour que la trace survive à la séance) : purge, suppression de l'audio, suppression de la séance.
8. **Le statut d'une exécution finie ne change plus.** « Périmée » est calculé à partir des exécutions amont, ce qui permet de réactiver une ancienne version.

## Conséquences
- `docs/technique/schema-donnees.md` est la référence. Une migration et sa mise à jour vont dans le même commit.
- Le moteur garde son format pour ses propres outils. L'application ne lit de lui que ses dossiers d'exécution, selon ses schémas.
- Le moteur garantit depuis la v1.2.0 qu'une exécution finie ne contient pas d'audio : la purge ne supprime que `sources/`.
- ~~Les copies de sauvegarde gardent le texte d'une séance supprimée : la confirmation de suppression le dit, et l'utilisateur supprime lui-même les sauvegardes s'il le veut (choix du 2026-10-05).~~ Remplacé par l'ADR 0029 : supprimer une séance l'efface aussi des sauvegardes.
- La recherche plein texte (FTS5) est un cache reconstructible, pas une source de vérité.
- Un fichier supprimé à la main dans le Finder se signale à l'affichage. La base n'est jamais « réparée » en silence.
- Le glossaire gagne deux termes : tâche (`job`) et journal des suppressions (`deletion_log`).

## Alternatives écartées
- Tout en JSON, comme `session.json` : ni requêtes, ni recherche, et un fichier interrompu en pleine écriture se perd.
- Dossier nommé d'après le titre (format du moteur) : il faudrait le renommer quand le titre change.
- Créer toutes les tables tout de suite : on figerait des formes qu'on ne connaît pas encore (phases, actions).
- Corrections appliquées en place sur une copie des sorties : le report après une relance et l'annulation deviennent impossibles à tracer.
- Reprendre les séances déjà traitées par l'atelier : écarté par l'utilisateur.
