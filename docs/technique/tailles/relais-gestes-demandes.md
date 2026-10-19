# Relais : la fenêtre des mises à jour qui attendent une action (pour « Interface », « Pilotage » et « Distribution »)

De : la conversation « Fenêtres d'explication des mises à jour », le 2026-10-19. Aucune des trois conversations n'était ouverte : ce relais tient lieu de message.

Fusionné dans `main` : v0.33.0 (`fusionne feat/gestes-demandes`). L'utilisateur a validé la forme sur une maquette, l'a auditée dans l'app de dév, puis a demandé la fusion. Décision : ADR 0049 ; spec §7.12 ; glossaire (« Geste demandé », « Mise à jour qui attend une action »).

## Ce qui a changé
- **Au lancement**, une fenêtre légère s'ouvre quand l'état du moteur attend une action sur ce Mac. Elle ne s'ouvre jamais pendant un enregistrement ni sur sa page. Au premier lancement, elle s'ouvre aussi, sous « Bienvenue dans Coulisses », avec « Tout télécharger ». Elle traite une mise à jour à la fois et montre :
  - en petit, sa nature : « Mise à jour du moteur de transcription » ;
  - le titre : « Une action est attendue de votre part » ;
  - une phrase ;
  - au plus trois chiffres : vitesse, poids, qualité ;
  - deux sorties en boutons, la recommandée d'abord.
- **Les cas couverts :**
  - un modèle remplacé : « Remplacer l'ancien par le nouveau » ou « Garder l'ancien pour l'instant » ; si le nouveau est déjà là, « Supprimer l'ancien modèle » ou « Garder l'ancien modèle » ;
  - ce qui manque au traitement : « Télécharger » ou « Plus tard » ;
  - un ancien environnement : « La supprimer » ou « La garder ».
- **Un point sur « Réglages »** tant qu'une mise à jour attend. Dans l'onglet « Transcription », un modèle remplacé dit « Remplacé, ne sert plus » et son bouton « Supprimer » est mis en avant.
- **Le moteur passe en v1.11.0** (ADR 0050 du moteur). Il publie les gains mesurés d'un modèle remplacé (`replacement_speedup`, `replacement_quality`, `replacement_memory_saved_bytes`, `replacement_evidence`), demandés pour cette fenêtre. La mémoire n'est pas montrée, pour que la fenêtre reste légère, et `replacement_evidence` n'apparaît qu'en mode développeur.
- **Côté service** : `GET` et `POST /api/gestes-ecartes`, dans `app_setting` (clé `gestes_ecartes`), sans migration.

## Pour Interface (`web/`)
- **Les nouveaux fichiers :**
  - `web/src/steps.ts` : la logique pure, testée dans `steps.test.ts`. Les mises à jour se déduisent de la vue des modèles (`updateNotices`), la suppression d'un remplacé est différée (`settleReplacements`).
  - `web/src/components/UpdateNotices.tsx` : le hook `useUpdateNotices` et le Dialog sans en-tête, avec `aria-label`.
- **Les classes CSS** : `cl-update`, `cl-gains`, `cl-choice`. `.cl-notice` existait déjà ailleurs, d'où le nom `cl-update`.
- **Les fichiers touchés :**
  - `App.tsx` : la fenêtre et le point ;
  - `Sidebar.tsx` : `stepsLeft`, le point sur « Réglages » ;
  - `ModelsSection.tsx` : la ligne du modèle remplacé ;
  - `models.ts` : `purposeOf`, `replacement` dans l'état « installé ».
- **La forme voulue par l'utilisateur** : légère, pour des gens qui ne sont pas des techniciens. Une première version, détaillée (liste de gestes, quatre cases, pied de page), a été jugée « lourde et pas belle ». Garde peu de texte, pas de nom technique hors du mode développeur, et pas de bord coloré.
- **Les textes** viennent des faits du moteur (étape, tailles, mesures) : aucun modèle n'est nommé dans l'app (P6).

## Pour Pilotage
- **La demande de l'utilisateur est faite** : le système de fenêtres pour les mises à jour qui demandent une action, en commençant par le modèle de transcription remplacé (étape 12, Qwen3 en 8 bits).
- **Rester sur l'ancien modèle est impossible** : le moteur n'a qu'un profil. « Garder l'ancien pour l'instant » veut donc dire que les séances ne sont pas traitées. C'est dit à l'utilisateur, et l'ADR 0049 le consigne.
- **Une instabilité, vue une fois** : `tests/test_processing.py::test_the_processing_loop_outlives_an_error_and_shows_it`, qui passe seul et passe sur `main`. À surveiller.

## Pour Distribution
- **v0.33.0 est étiquetée** avec le moteur v1.11.0 (`uv.lock`), mais rien n'est poussé : `main` est en avance sur `origin`. La publication suit le parcours de l'ADR 0040.
- **Chez un ami qui met à jour**, la fenêtre s'ouvrira au lancement : télécharger `qwen3-asr-1.7b-8bit` (2,5 Go), puis supprimer l'ancien `qwen3-asr-1.7b` (4,7 Go). À vérifier dans l'essai du paquet ou sur la pré-version.
- **Sur ce Mac**, la Coulisses publiée (0.28.0) se sert encore de `qwen3-asr-1.7b`, dans le même dossier `~/Coulisses/Modèles`. Il ne faut pas le supprimer avant d'avoir publié et installé une version avec le moteur v1.10.0 ou plus. L'utilisateur a été prévenu.
- **L'interface du dépôt principal** (`~/Coulisses/App/web/dist`) a été reconstruite le 2026-10-19 pour l'essai en dév. L'app quotidienne lancée depuis le dépôt (`~/Applications/Coulisses.app`) sert donc aussi cette interface.
