# Relais : lot 12e fait, v0.29.0 (pour « Pilotage », « Distribution et publication », « Interface »)

De : la conversation « Alléger Coulisses », le 2026-10-19. Aucune de ces conversations n'était ouverte : ce relais tient lieu de message.

## Ce qui est fait (ADR 0046)
Fusion dans `main` : v0.29.0 (`46480ce`). Une fois l'enregistrement fini, chaque piste enregistrée par l'app passe en FLAC, sans perte : les micros, le son de l'ordinateur, le mix et le mix d'écoute. Le WAV n'est supprimé qu'une fois prouvé que le FLAC rend les mêmes échantillons.

Gain : environ −44 % par piste. Une répétition passe de 518 Mo à ≈ 290 Mo par heure, une réunion de 2,07 Go à ≈ 1,16 Go par heure.

- **Base** : migration 0009 (`audio_source.pcm_sha256` ; `deletion_log` accepte `conversion`). Une sauvegarde est faite avant la migration.
- **Tests** : 416 tests passent, dont 20 pour ce lot. Les tests lents passent aussi : le moteur rend les mêmes sorties sur un WAV et sur son FLAC.
- **Pas de conversion automatique** pour les imports, les enregistrements faits avant cette version et les enregistrements récupérés après un plantage.

## Pour Distribution
- **La conversion ne marche pas encore dans l'app construite.** Son ffmpeg ne sait pas écrire de FLAC, donc les pistes restent en WAV, sans perte, et le journal du service le dit. Il faut ajouter l'encodeur et le format `flac` dans `construction.toml`, avec l'essai d'aller-retour : voir [relais-12e-distribution.md](relais-12e-distribution.md).
- **Avant de publier une app qui convertit**, l'utilisateur doit vérifier à la main, dans l'app « Coulisses (dév) » : la lecture d'une séance enregistrée, et le déplacement précis dans le temps (clic sur un mot) dans la fenêtre de l'app (WKWebView). L'ADR 0046 l'exige.
- **La note de version de v0.29.0** dit « garde les enregistrements en FLAC, sans perte, une fois finis ». Pour des amis, on peut la compléter à la publication : « deux fois moins de place, mêmes sons ».

## Pour Interface
Un seul changement dans `web/` : le libellé `conversion` du journal des suppressions (`web/src/retention.ts`, `LOG_KIND` : « Pistes gardées en FLAC, sans perte ») et son type (`web/src/api.ts`). Pour une conversion, `bytes` est la place gagnée. Tu peux reprendre ce libellé à ta façon.

## Pour Pilotage
- **12e fait.**
- **12c-2 (ADR 0047, A et B) est publié par le Moteur en v1.8.0** : torch sort de l'app, dans un environnement `torch` installé à la demande (≈ 1 Go). Ce n'est pas encore monté dans l'app. Pour le passage à la v1.8.0 et le test lent, cet environnement devra être installé sur ce Mac, ce qui demande l'accord de l'utilisateur pour le télécharger.
- **12d** : le banc de Qwen3 quantifié est en cours chez le Moteur.
