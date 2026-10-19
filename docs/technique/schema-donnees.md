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
    sources/<source_id>.<ext>         originaux : un import tel quel ; un enregistrement en .wav, puis
                                      en .flac une fois fini, sans perte (ADR 0046) ; seul contenu purgé
    sources/mix.{wav,flac}, mix.json  le micro et le son de l'ordinateur réunis (ADR 0032), purgés aussi
    sources/listening.{wav,flac}      le mix d'écoute, micro baissé entre les paroles (ADR 0037), purgé aussi
    runs/<run_id>/                    une exécution : spec.json, output.json, provenance.json…
```

- `session_id` : `AAAAMMJJ-HHMMSS-xxxx` (heure locale du début de l'enregistrement ou de l'import, puis 4 caractères aléatoires `[a-z0-9]`). Jamais le titre.
- `source_id` : `ref` pour la source de référence (l'identifiant que le moteur donne à la source dans ses sorties) ; `mic2`, `mic3`… pour les micros ajoutés, captés en même temps (`sources/mic2.wav`…, ADR 0031, 0033), gardés et pas encore traités : ses `offset_s` et `drift_ppm` valent 0, **non mesurés**, jamais une mesure, jusqu'à l'étape de synchronisation du moteur ; `system` pour le son de l'ordinateur (`sources/system.wav`, mono, ADR 0032), sur l'horloge de la référence : ses `offset_s` et `drift_ppm` à 0 sont ici exacts (la même horloge). Avec `system`, le moteur traite `sources/mix.wav` (la référence en mono plus `system`, un seul gain), décrit par `sources/mix.json` (empreintes des sources enregistrées à leur fermeture, gain, empreinte du mix, son de l'ordinateur muet ou non) : un audio dérivé, hors de `audio_source`, refait quand les empreintes enregistrées diffèrent (celles des échantillons, `pcm_sha256`, depuis l'ADR 0046 : passer une source en FLAC ne refait pas le mix). `mix.json` nomme le fichier du mix (`file`) et de son mix d'écoute, et l'empreinte de leurs échantillons. Ces faits sont recopiés dans `job.params.mix` du traitement qui l'a utilisé : ils survivent à la purge. À côté, `sources/listening.wav`, le mix d'écoute que la page fait entendre (ADR 0037), décrit dans `mix.json` (`listening` : règle, paramètres, gain, empreinte) ; le moteur ne l'entend pas. La source de référence est désignée par `session.reference_source_id`, jamais déduite du nom.
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
| `audio_source` (FLAC) | `pcm_sha256` : empreinte des échantillons (PCM 24 bits petit-boutiste entrelacé), la même pour un WAV et le FLAC qui en est fait ; posée à la fermeture d'un enregistrement, vide pour un import ou un enregistrement d'avant (migration 0009, ADR 0046). Une fois la piste gardée en FLAC, `file_name`, `sha256`, `size_bytes` et `codec` (`flac`) décrivent le FLAC | 12 |
| `job` | `id`, `session_id*`, `kind*` (`chain`, `generation`), `state*` (`queued`, `running`, `done`, `failed`), `params*` (JSON : présents, glossaire figé ; pour une relance, `rerun` (`transcribe`, `diarize`) et `reuse` (étape → exécution de la version de départ reprise telle quelle), étape 7), `requested_at*`, `started_at`, `finished_at`, `error` | 1 |
| `run` | `id*` (texte), `session_id*`, `job_id`, `stage*`, `status*` (`queued`, `running`, `succeeded`, `failed` : jamais modifié une fois fini), `producer*` (`engine`, `app`), `engine_version`, `created_at*`, `finished_at`, `error_summary` | 1 |
| `run_upstream` | `run_id*`, `upstream_run_id*` | 1 |
| `active_run` | `session_id*`, `stage*`, `run_id*` (clé : séance + étape) | 1 |
| `person` | `id`, `space_id*`, `kind*` (`member`, `guest`), `name*`, `role` (texte libre), `color_slot*` (couleur de la palette, gardée d'une séance à l'autre : la moins utilisée de l'espace à la création), `created_at*`, `archived_at` | 2 |
| `attendee` | `session_id*`, `person_id*` | 2 |
| `glossary_entry` | `id`, `space_id*`, `term*`, `category`, `variants*` (JSON : graphies fautives connues), `created_at*`, `archived_at` | 2 |
| `edit` | `id`, `session_id*`, `run_id*` (exécution « qui a dit quoi » corrigée), `kind*` (`assign_speaker` : nommer une voix, personne, nom libre ou personnage joué par une personne ; `merge_speakers` ; `reassign_turns` : donner des répliques à une autre voix ou à une nouvelle, pour scinder ; `edit_text` : texte d'une réplique ; `set_phase` : un chapitre commence à une réplique, ou change de type ou de titre ; `remove_phase` : une coupure de chapitre retirée ; `revert` : annulation), `payload*` (JSON), `person_id` (pour un rattachement), `anchor_start_s`, `anchor_end_s` (temps mesurés, pour le report), `reverts_edit_id`, `created_at*` | 2 |
| `edit_carryover` | `edit_id*` (correction d'origine), `target_run_id*` (exécution « qui a dit quoi » de la nouvelle version), `outcome*` (`applied`, `partial` : une partie des répliques seulement, `not_applied`), `reason` (pourquoi non reportée ou en partie, ou rien n'était à écrire), `carried_edit_id` (la copie sur la nouvelle version, qui s'annule comme les autres), `description*` (la correction telle qu'elle se lisait sur sa version), `created_at*` (migration 0006, ADR 0028) | 7 |
| `marker` | `id`, `session_id*`, `kind*` (`scene`, `discussion`, `key_moment`), `at_s*` (temps de l'enregistrement, pauses exclues), `created_at*` (migration 0005) | 6 |
| `note` | `id`, `session_id*`, `at_s` (nul : note d'après séance), `text*`, `created_at*`, `updated_at*` (migration 0004 ; une seule note d'après séance par séance, gardée même vidée) | 5 (en direct : 6) |
| `action` | `id`, `name*`, `description*`, `prompt*`, `based_on` (clé de l'action fournie dont c'est la version modifiée, qui garde cette clé ; vide pour une action à soi, de clé `perso-<id>`), `created_at*`, `updated_at*`, `archived_at` (restaurer l'original ou retirer une action archive la ligne, jamais d'effacement) (migration 0004 ; une seule version modifiée en vigueur par action fournie) | 5 |
| `generation` | `id`, `session_id*`, `run_id*`, `action_ref*` (clé d'action fournie ou id), `created_at*` (migration 0003 ; provenance : `schemas/generation-provenance.schema.json`, ADR 0022) | 3 |
| `action_preference` | `space_id*`, `action_ref*`, `model` (inutilisée depuis l'ADR 0025), `auto_run*` (depuis l'ADR 0025 : le résumé proposé en premier dans l'espace ; rien ne se lance seul) | 3 |
| `project` + `session.project_id` | `id`, `space_id*`, `name*`, `created_at*`, `archived_at` ; `session.project_id` : projet de l'espace de la séance, ou rien (migration 0008, ADR 0030) | 8 |
| `search_index` | FTS5 `unicode61 remove_diacritics 2` : `session_id`, `kind` (`title`, `turn`, `note`, `summary`), `ref`, `at_s` (temps mesuré), `text`. Cache reconstructible, jamais une source de vérité ; effacé avec la séance (migration 0008) | 8 |
| `search_state` | `session_id*`, `key*` : de quoi le texte indexé d'une séance était fait ; s'il change, la séance est réindexée à la recherche suivante (migration 0008) | 8 |
| `session` (conservation) | `keep_audio*` (bool : « Garder l'audio »), `retain_until` (prolongation), `purge_announced_at` (purge annoncée ; elle n'a lieu qu'une fois le préavis écoulé depuis), `audio_removed_at`, `audio_removed_reason` (`purge`, `audio_deletion`) (migration 0007, ADR 0029) | 9 |
| `deletion_log` | `id`, `at*`, `kind*` (`purge`, `audio_deletion`, `session_deletion` ; `conversion` depuis la migration 0009 : des WAV supprimés une fois gardés en FLAC, ADR 0046), `session_id*` (sans clé étrangère : la trace survit à la séance), `session_title` (vide pour une séance supprimée : aucun texte n'en reste), `detail*` (JSON : fichiers supprimés, tailles, problèmes ; pour une conversion, `kept` liste les FLAC gardés et `bytes` est la place gagnée) (migration 0007) | 9 |
| `app_setting` | `key*`, `value*` (JSON) : modèle de génération choisi (étape 3), durée de conservation (`conservation_jours`) et préavis (`preavis_jours`) (étape 9), dossier d'export (`dossier_export`, étape 8) | 3 |

## Ce qui n'est pas en base

- **Sorties et provenance** : dans les dossiers d'exécution. La base ne recopie que ce qu'il faut pour lister et décider (`status`, dates, version du moteur, résumé d'erreur).
- **Vue corrigée** : recalculée depuis l'exécution active et le journal des corrections, jamais stockée comme vérité.
- **Actions fournies** : fichiers de l'application (`prompting/textes/actions/*.md`), en lecture seule. Modifier une action fournie crée une action en base (`based_on`), l'original reste restaurable.
- **Prompts envoyés, réponses, réglages du LLM** : dans le dossier d'exécution de la génération, un fichier par appel (`calls/01-prompt.txt`, `calls/01-response.md`… ; plusieurs appels pour un résumé par sections, puis la consolidation), le résultat (`output.md`) et `provenance.json`. Le schéma de provenance des exécutions de l'application (modèle, `num_ctx`, tokens comptés, température, graine, durée par appel) est publié à l'étape 3, dans `schemas/`.

## Règles de cohérence

- À la fermeture du service, `stop_all` du moteur arrête les étapes en cours et les enregistre en échec (`Interrupted`). Après un plantage, le sous-processus s'arrête seul ; au démarrage suivant, une tâche `running` est orpheline : l'application clôt chacune de ses exécutions sans provenance par `close_interrupted` (le moteur écrit l'échec, le dossier reste), puis remet la tâche en file. Les exécutions réussies sont reprises telles quelles (précise l'ADR 0002). Si le moteur refuse la clôture (processus encore vivant), la tâche reste en attente et le refus s'affiche.
- Seul un `run` `succeeded` peut devenir actif ; une ancienne exécution réussie peut le redevenir. Les exécutions d'une tâche `chain` deviennent actives **ensemble**, quand toutes ses étapes ont réussi, dans la même transaction que le report des corrections (ADR 0028). Afficher une ancienne version réactive son exécution « qui a dit quoi », celles dont elle vient et ses derniers chapitres.
- **Périmée** (`stale`) est un état calculé, jamais stocké. Pour les étapes du moteur : l'exécution active d'une étape qu'une relance en cours (ou arrêtée) refait. Pour les générations : faites sur une autre version, d'autres corrections, d'autres chapitres ou une autre note.
- Une correction n'est jamais effacée : l'annuler ajoute une correction qui la désigne (`reverts_edit_id`).
- Un fichier attendu et absent (supprimé dans le Finder) se signale à l'affichage ; la base n'est pas modifiée en silence.
- La suppression d'une séance entière efface ses lignes (en `secure_delete`, journal de la base vidé), son dossier, et ses lignes dans chaque sauvegarde de migration, compactée ensuite (ADR 0029, choix de l'utilisateur du 2026-10-07).
- Le minimum de voix transmis au moteur : le nombre de présents cochés plus `unnamed_attendees` (rien si les deux sont nuls).
