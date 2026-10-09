# Coulisses — l'application

App macOS 100 % locale de débrief de séances (répétitions d'impro d'abord, réunions de travail aussi, ADR 0020) : enregistrement mono-micro → qui a dit quoi → comptes rendus en français. Un seul utilisateur, un seul Mac (M5 Pro, 64 Go).

**Phase actuelle : construire l'application, à neuf, à partir de `docs/`.** Ce dépôt ne contient que l'application. Le traitement de l'audio est fait par **le moteur**, un autre dépôt (`~/Coulisses/Moteur`, `coulisses-moteur`), utilisé **par une version étiquetée** et **uniquement par son contrat**. (Tiens cette ligne à jour à chaque changement de phase.)

## Où trouver quoi
- `docs/produit/spec-v1.md` : ce que fait le produit et pourquoi. **À lire avant toute fonctionnalité.**
- `docs/produit/glossaire-domaine.md` : terme français ↔ identifiant anglais. Aucun synonyme inventé.
- `docs/produit/direction-artistique.md` : la direction visuelle retenue (ADR 0017). **À lire avant tout écran.**
- `docs/decisions/` : ADR de l'application. Une décision **acceptée** ne se contourne pas : on propose un nouvel ADR (`/adr`). Les ADR techniques du moteur (0003, 0004, 0009, 0011 à 0015) sont dans `coulisses-moteur`.
- `docs/produit/questions-ouvertes.md` : ce qui n'est pas tranché. Ne tranche pas à la place de l'utilisateur.

## Le moteur
- Dépôt `~/Coulisses/Moteur`. Son contrat : `engine/README.md` (entrées, sorties, organisation des exécutions, garanties) et `engine/schemas/*.schema.json`.
- L'application en dépend **par étiquette** (`vX.Y.Z`), jamais par chemin vers le code d'un autre dépôt. Dans le `pyproject.toml` de l'application : `coulisses = { git = "file:///Users/t.serre/Coulisses/Moteur", subdirectory = "engine", tag = "v1.6.0" }` (dans `[tool.uv.sources]`, avec `coulisses[mlx-audio,pyannote,wav2vec2]` en dépendance). Monter de version = changer cette étiquette, relire le `CHANGELOG.md` du moteur, puis passer les tests de l'application. Une version **majeure** du moteur change le contrat : l'application doit s'adapter.
- Le paquet Python de l'application ne s'appelle pas `coulisses` (nom pris par le moteur) : `coulisses_app`.
- Le moteur ne fait que transcription, alignement, diarisation, attribution (un seul profil, `chaine-retenue`). Phases, titre et résumés sont faits par l'application (`prompting/`).
- **Seul `coulisses.api` est public** (et `coulisses.testing` pour les tests), depuis la v1.2.0 (ADR 0019 du moteur). On appelle le moteur par `run_chain` ou `coulisses-traiter`, et on lit ses sorties selon ses schémas (`read_output`, `read_provenance`). `run_chain` laisse l'application choisir le dossier de chaque exécution et fournir la fonction `run_stage` qui lance chaque étape (celle du moteur : `execute_stage(séance)`, que l'application enveloppe pour réutiliser une exécution réussie) : c'est ce qui permet de reprendre ou de relancer une seule étape. L'avancement se lit dans `chain.json` et `progress.json` (`chain-plan.schema.json`, `progress.schema.json`, règle de suivi dans `engine/README.md`). Arrêter une étape : `cancel`, `stop_all` (à la fermeture), `close_interrupted` (après un plantage de l'application). On n'importe jamais rien d'autre que `coulisses.api` et on n'écrit jamais dans ses exécutions.
- Installer le moteur : la dépendance étiquetée, puis `coulisses-models installer-environnement diarizen` et les modèles du catalogue (`coulisses-models telecharger <clé>`), qui vont dans `~/Coulisses/Modèles` et `~/Coulisses/Environnements`.
- Le moteur à améliorer (nouveau modèle, plus rapide, plus juste) : dans son dépôt, avec son banc d'essai, jamais ici.

## Principes non négociables
Ils priment sur la vitesse, la simplicité et le délai. Si une tâche semble exiger d'en violer un, arrête-toi et demande.
1. **Hors ligne.** Aucun appel réseau à l'exécution. Seule exception côté application : le client du LLM (`prompting/`, Ollama sur 127.0.0.1). Les modèles se téléchargent par le moteur, sur demande explicite. Pas de télémétrie, pas de CDN.
2. **Horodatages mesurés.** Chaque temps de mot vient du moteur, mesuré sur l'audio, ou est absent ; l'application n'en invente jamais (pas d'interpolation, pas de répartition au prorata du texte).
3. **Sur-segmenter plutôt que fusionner.** Le nombre de présents est un minimum de locuteurs, jamais un maximum.
4. **Français.** Toute génération LLM passe par l'assemblage unique de `prompting/`, qui ajoute la consigne de langue. Aucun autre chemin vers le LLM.
5. **Rejouable, lisible pour toujours.** Une exécution du moteur terminée est immuable ; relancer crée une nouvelle exécution. Les corrections de l'utilisateur sont stockées à part et ne sont jamais perdues lors d'une relance. Les sorties textuelles ne sont jamais purgées.
6. **Aucun modèle gravé.** L'application n'importe aucune bibliothèque de modèle et ne nomme aucun modèle : elle passe par le moteur et son profil.
7. **Transparence.** Chaque résultat garde la provenance du moteur (version, modèles, réglages, durée).
8. **Aucune perte silencieuse.** Pas de troncature, d'écrasement ni d'`except: pass` muet ; pas de suppression sans décision explicite et visible. Une erreur se voit.

Des hooks bloquent une partie de ces violations (`.claude/hooks/`). Un blocage n'est pas un obstacle à contourner : lis le message, puis corrige l'approche.

## Données
- Tout vit sous `~/Coulisses/` : `App/` (ce dépôt), `Moteur/` (le moteur), `Modèles/`, `Environnements/`, `Données/` (ADR 0010, 0016).
- Données réelles : `~/Coulisses/Données/`. **Tu n'y écris jamais et tu n'y supprimes rien**, même pour un test.
- Développement : `COULISSES_DATA_DIR=~/Coulisses/Données-dev`. Tests : dossier temporaire (`tmp_path`).
- Jamais d'audio réel, de transcript réel, de base ou de modèle dans git. Les fixtures de test sont synthétiques (`say -v Thomas …`) et restent sous 1 Mo.

## Façon de travailler (autonomie encadrée)
- Tu codes, testes et commits par petites étapes, sur une branche par tâche (`feat/…`, `fix/…`).
- **Demande validation avant** : un changement du schéma de données, une montée de version majeure du moteur, toute nouvelle dépendance lourde (plus de 500 Mo ou native), toute décision listée dans les questions ouvertes. Prépare la revue avec `/jalon`.
- Avant chaque commit qui touche le code, la configuration ou un prompt : fais relire le diff par l'agent `gardien-principes`.
- Une décision structurante prise = un ADR (`/adr`). Un comportement produit modifié = la spec mise à jour dans le même commit.
- **Messages de commit : Conventional Commits, description en français à l'impératif** : `type(portée): description`, ex. `feat(enregistrement): ajoute la pause`. Types : `feat` (nouveauté, version mineure), `fix` (correction, version corrective), `perf` (plus rapide, version corrective), `refactor`, `docs`, `test`, `build`, `chore`, `style` (aucune version). `!` après la portée = changement incompatible (version majeure ; avant 1.0.0, mineure). Les fusions : `fusionne <branche>`. Un hook refuse les messages hors convention.
- **Versions : jamais à la main.** À chaque fusion dans `main`, `scripts/release.py` (hook `post-merge`) calcule la version suivante, met à jour les fichiers listés dans `release.toml` et `CHANGELOG.md`, commite `chore(version): vX.Y.Z` et pose l'étiquette. Dès que l'application a un `pyproject.toml` ou un `package.json`, ajoute-les à `release.toml` (`fichiers`), et le dossier de son `uv.lock` à `verrous`.

## Langues
Code, identifiants, commentaires et logs techniques en anglais. Docs, commits, interface, messages d'erreur montrés à l'utilisateur et prompts en français (prompts rédigés en français natif, jamais traduits).

## Pièges connus
- Ollama tronque **en silence** au-delà de `num_ctx`. Il faut toujours le fixer, et compter les tokens avant l'envoi.
- Le traitement d'une séance prend ≈ 10 min par heure d'audio : il tourne en tâche de fond, son avancement se lit dans `chain.json` et les `progress.json` du moteur (schémas publiés), et l'interface ne bloque jamais dessus.
- Ne charge jamais un modèle dans le processus de l'application : le moteur lance chaque étape dans un sous-processus.
- La permission micro de macOS s'applique au processus parent (Terminal pendant le développement).
