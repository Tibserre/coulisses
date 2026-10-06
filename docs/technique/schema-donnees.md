# Schéma de données de l'application

Référence du stockage (ADR 0018). Tenu à jour à chaque migration, dans le même commit.
Les noms suivent le glossaire (`docs/produit/glossaire-domaine.md`).

## Dossier de données

```
$COULISSES_DATA_DIR/                  ~/Coulisses/Données (réel), Données-dev (développement)
  coulisses.db                        SQLite, mode WAL
  sauvegardes/                        copie de la base avant chaque migration (voir « Sauvegardes »)
    coulisses-avant-0002-20261012T091500.db
  sessions/<session_id>/
    sources/<source_id>.<ext>         originaux, tels quels ; seul contenu purgé
    runs/<run_id>/                    une exécution : spec.json, output.json, provenance.json…
```

- `session_id` : `AAAAMMJJ-HHMMSS-xxxx` (heure locale du début de l'enregistrement ou de l'import, puis 4 caractères aléatoires `[a-z0-9]`). Jamais le titre.
- `source_id` : `ref` pour la source de la V1 (l'identifiant que le moteur donne à la source dans ses sorties). La source de référence est désignée par `session.reference_source_id`, jamais déduite du nom.
- `run_id` : `<étape>-<8 hexadécimaux>`, aussi le nom du dossier.
- Exécutions du moteur : le moteur écrit le dossier, l'application ne fait que le lire. Exécutions de l'application (chapitres `segment_phases`, titre, résumés) : même forme de dossier, écrit par l'application, immuable une fois fini. Les chapitres détectés sont dans `output.json` ; ceux qui sont affichés sont recalculés à partir de la détection active et du journal `edit` (ADR 0024).
- Une exécution finie ne contient jamais d'audio (garantie du moteur depuis la v1.2.0) : du JSON, un journal et, parfois, des empreintes vocales (`speaker_embeddings_file`). La purge ne supprime donc que `sources/`, et liste chaque fichier supprimé dans le journal.

## Conventions

- Dates : texte ISO 8601 en UTC (`2026-10-05T09:15:00Z`). Temps dans la séance : secondes (`REAL`) depuis le début de la source de référence.
- Clés : `INTEGER PRIMARY KEY` sauf `session.id`, `run.id` (noms de dossier) et `audio_source` (`session_id`, `source_id`).
- `PRAGMA foreign_keys = ON`. Aucune suppression en cascade sauf depuis `session`, et seulement par la suppression confirmée d'une séance entière.
- Contenu JSON (`payload`, `params`) : validé par un modèle pydantic à l'écriture et à la lecture, avec un champ `v` (version du format).
- Version du schéma : `PRAGMA user_version`. Migrations numérotées (`migrations/0001_socle.sql`…), uniquement vers l'avant, chacune dans une transaction, précédée d'une sauvegarde de la base.

## Tables

`*` : non nul. Étape : celle du découpage où la table est créée.

| Table | Colonnes | Étape |
|---|---|---|
| `troupe` | `id`, `name*`, `created_at*` | 1 (une créée d'office) ; devient `space` à l'étape 2 |
| `space` (ADR 0020) | `troupe` renommée (migration 0002), plus `voice_recognition*` (bool, faux par défaut), `archived_at` | 2 |
| `session` | `id*` (texte), `troupe_id*`, `title`, `title_edited*` (bool), `recorded_at*` (début de la captation ; pour un import, date de modification du fichier, corrigeable), `created_at*`, `reference_source_id*`, `attendee_count` (nombre saisi, minimum de voix) | 1 ; à l'étape 2, `troupe_id` → `space_id` et `attendee_count` → `unnamed_attendees` (présents non nommés, en plus des cochés) |
| `audio_source` | `session_id*`, `source_id*`, `origin*` (`captured`, `imported`), `original_name*`, `file_name*`, `sha256*`, `size_bytes*`, `duration_s`, `sample_rate`, `channels`, `codec`, `device`, `offset_s*` (0 en V1), `drift_ppm*` (0 en V1), `added_at*`, `removed_at` | 1 |
| `audio_source` (captation) | `capture_state` (`recording`, `complete`, `recovered` : interrompue puis réparée au redémarrage ; vide pour un import), `capture_ended_at` (migration 0005, ADR 0027) | 6 |
| `job` | `id`, `session_id*`, `kind*` (`chain`, puis `stage`, `generation`), `state*` (`queued`, `running`, `done`, `failed`), `params*` (JSON : présents, glossaire figé, étapes demandées), `requested_at*`, `started_at`, `finished_at`, `error` | 1 |
| `run` | `id*` (texte), `session_id*`, `job_id`, `stage*`, `status*` (`queued`, `running`, `succeeded`, `failed` : jamais modifié une fois fini), `producer*` (`engine`, `app`), `engine_version`, `created_at*`, `finished_at`, `error_summary` | 1 |
| `run_upstream` | `run_id*`, `upstream_run_id*` | 1 |
| `active_run` | `session_id*`, `stage*`, `run_id*` (clé : séance + étape) | 1 |
| `person` | `id`, `space_id*`, `kind*` (`member`, `guest`), `name*`, `role` (texte libre), `color_slot*` (couleur de la palette, gardée d'une séance à l'autre : la moins utilisée de l'espace à la création), `created_at*`, `archived_at` | 2 |
| `attendee` | `session_id*`, `person_id*` | 2 |
| `glossary_entry` | `id`, `space_id*`, `term*`, `category`, `variants*` (JSON : graphies fautives connues), `created_at*`, `archived_at` | 2 |
| `edit` | `id`, `session_id*`, `run_id*` (exécution « qui a dit quoi » corrigée), `kind*` (`assign_speaker` : nommer une voix, personne, nom libre ou personnage joué par une personne ; `merge_speakers` ; `reassign_turns` : donner des répliques à une autre voix ou à une nouvelle, pour scinder ; `edit_text` : texte d'une réplique ; `set_phase` : un chapitre commence à une réplique, ou change de type ou de titre ; `remove_phase` : une coupure de chapitre retirée ; `revert` : annulation), `payload*` (JSON), `person_id` (pour un rattachement), `anchor_start_s`, `anchor_end_s` (temps mesurés, pour le report), `reverts_edit_id`, `created_at*` | 2 |
| `edit_carryover` | `edit_id*`, `target_run_id*`, `outcome*` (`applied`, `not_applied`), `reason` | 7 |
| `marker` | `id`, `session_id*`, `kind*` (`scene`, `discussion`, `key_moment`), `at_s*` (temps de l'enregistrement, pauses exclues), `created_at*` (migration 0005) | 6 |
| `note` | `id`, `session_id*`, `at_s` (nul : note d'après séance), `text*`, `created_at*`, `updated_at*` (migration 0004 ; une seule note d'après séance par séance, gardée même vidée) | 5 (en direct : 6) |
| `action` | `id`, `name*`, `description*`, `prompt*`, `based_on` (clé de l'action fournie dont c'est la version modifiée, qui garde cette clé ; vide pour une action à soi, de clé `perso-<id>`), `created_at*`, `updated_at*`, `archived_at` (restaurer l'original ou retirer une action archive la ligne, jamais d'effacement) (migration 0004 ; une seule version modifiée en vigueur par action fournie) | 5 |
| `generation` | `id`, `session_id*`, `run_id*`, `action_ref*` (clé d'action fournie ou id), `created_at*` (migration 0003 ; provenance : `schemas/generation-provenance.schema.json`, ADR 0022) | 3 |
| `action_preference` | `space_id*`, `action_ref*`, `model` (inutilisée depuis l'ADR 0025), `auto_run*` (depuis l'ADR 0025 : le résumé proposé en premier dans l'espace ; rien ne se lance seul) | 3 |
| `project` + `session.project_id` | `id`, `space_id*`, `name*`, `created_at*`, `archived_at` | 8 |
| `search_index` | FTS5 `unicode61 remove_diacritics 2` : `session_id`, `kind`, `ref`, `text`. Cache reconstructible, jamais une source de vérité | 8 |
| `session` (conservation) | `pinned*`, `retain_until` (prolongation), `audio_removed_at`, `audio_removed_reason` (`purge`, `audio_deletion`) | 9 |
| `deletion_log` | `id`, `at*`, `kind*` (`purge`, `audio_deletion`, `session_deletion`), `session_id*` (sans clé étrangère : la trace survit à la séance), `session_title`, `detail*` (JSON : fichiers supprimés, tailles) | 9 |
| `app_setting` | `key*`, `value*` (JSON) : modèle de génération choisi (étape 3), puis durée de conservation, préavis, dossier d'export | 3 |

## Ce qui n'est pas en base

- **Sorties et provenance** : dans les dossiers d'exécution. La base ne recopie que ce qu'il faut pour lister et décider (`status`, dates, version du moteur, résumé d'erreur).
- **Vue corrigée** : recalculée depuis l'exécution active et le journal des corrections, jamais stockée comme vérité.
- **Actions fournies** : fichiers de l'application (`prompting/textes/actions/*.md`), en lecture seule. Modifier une action fournie crée une action en base (`based_on`), l'original reste restaurable.
- **Prompts envoyés, réponses, réglages du LLM** : dans le dossier d'exécution de la génération, un fichier par appel (`calls/01-prompt.txt`, `calls/01-response.md`… ; plusieurs appels pour un résumé par sections, puis la consolidation), le résultat (`output.md`) et `provenance.json`. Le schéma de provenance des exécutions de l'application (modèle, `num_ctx`, tokens comptés, température, graine, durée par appel) est publié à l'étape 3, dans `schemas/`.

## Règles de cohérence

- À la fermeture du service, `stop_all` du moteur arrête les étapes en cours et les enregistre en échec (`Interrupted`). Après un plantage, le sous-processus s'arrête seul ; au démarrage suivant, une tâche `running` est orpheline : l'application clôt chacune de ses exécutions sans provenance par `close_interrupted` (le moteur écrit l'échec, le dossier reste), puis remet la tâche en file. Les exécutions réussies sont reprises telles quelles (précise l'ADR 0002). Si le moteur refuse la clôture (processus encore vivant), la tâche reste en attente et le refus s'affiche.
- Seul un `run` `succeeded` peut devenir actif ; une ancienne exécution réussie peut le redevenir.
- **Périmée** (`stale`) est un état calculé, jamais stocké : une exécution active est périmée quand l'une de ses exécutions amont (`run_upstream`) n'est plus l'exécution active de son étape.
- Une correction n'est jamais effacée : l'annuler ajoute une correction qui la désigne (`reverts_edit_id`).
- Un fichier attendu et absent (supprimé dans le Finder) se signale à l'affichage ; la base n'est pas modifiée en silence.
- La suppression d'une séance entière efface sa ligne et son dossier. Les sauvegardes de migration, elles, gardent une copie de la base : la confirmation le dit, et l'application liste ces sauvegardes ; l'utilisateur les supprime lui-même s'il le souhaite (étape 9, choix de l'utilisateur du 2026-10-05).
- Le minimum de voix transmis au moteur : le nombre de présents cochés plus `unnamed_attendees` (rien si les deux sont nuls).
