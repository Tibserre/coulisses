# 0080 — Une séance attend tout ce qui manque à la chaîne, et tout se télécharge d'un coup

Statut : Acceptée (2026-11-10, demande de l'utilisateur relayée par Pilotage : point bloquant n° 2 de la revue UX d'Interface, à corriger avant la v0.39.0). Précise 0072 et 0036.

## Contexte
- Sur une installation neuve, après « Plus tard », le « Télécharger (3,7 Go) » d'une séance ne prenait que les modèles de sa langue : la transcription et l'alignement.
- L'attente d'une séance (ADR 0072) ne comptait qu'eux. « Qui parle quand » (trois modèles) et les outils de calcul (deux environnements) restaient absents, et le traitement échouait ensuite.
- Le moteur dit déjà tout ce qui manque à sa chaîne pour une langue : `readiness(profil, language=…)`, les modèles de chaque étape et les environnements.

## Décision
- **L'attente d'une séance compte tout ce qui manque à la chaîne** pour sa langue, d'après `readiness` : les modèles de chaque étape, pas seulement ceux de sa langue, et les environnements. `WaitsFor` (`processing_waits_for`) garde ses champs : `missing_models` les a tous, `download_bytes` leur taille annoncée, et il gagne `missing_environments` (nom et ce à quoi il sert, en français, d'après le moteur). La taille d'un environnement n'est jamais connue d'avance : elle n'est pas comptée.
- La séance repart d'elle-même quand la dernière pièce est là, comme avant : fin d'un téléchargement ou d'une installation, ou démarrage de l'app.
- **« Tout télécharger »** : `POST /api/moteur/manquants/telecharger` (corps `{"langue": "fr"}`, le français par défaut) lance, sur demande de l'utilisateur, le téléchargement de chaque modèle manquant et l'installation de chaque environnement manquant. Chacun reste une tâche à part, avec son avancement, son arrêt et sa reprise (`GET /api/moteur/telechargements`, ADR 0036) : rien ne se fait sans se voir. Une tâche déjà en cours est laissée telle quelle. Rien ne manque : rien n'est lancé.
- `GET /api/moteur/manquants?langue=fr` dit ce qui manque, sous la même forme que `processing_waits_for`, ou `null`. Une langue que la chaîne ne prend pas : 422.
- Rien ne se télécharge de lui-même (P1) : seul le clic de l'utilisateur lance ces tâches.

## Conséquences
- Conforme à l'ADR 0072 (« aucune route ne télécharge plusieurs modèles d'un coup sans que chacun se voie ») : la nouvelle route lance plusieurs tâches, chacune visible. `contrat-langue.md` perd sa formule plus stricte.
- `reason` reste `model_missing` quel que soit ce qui manque. L'interface doit pourtant gérer deux cas nouveaux : seul un environnement manque (`missing_models` vide, `download_bytes` à 0 : pas de taille à annoncer, un libellé qui ne parle pas d'un modèle), et un modèle abîmé.
- **Un modèle abîmé** (`model_altered`) est dit à part (`altered_models`) : il n'est ni compté dans `download_bytes` ni lancé par « Tout télécharger », puisque le moteur refuse de télécharger par-dessus. La séance dit de le supprimer dans Réglages, onglet Transcription, puis de le télécharger à nouveau. Avant, un modèle abîmé hors de la langue faisait échouer le traitement ; maintenant la séance attend.
- Les choix ci-dessus (modèle abîmé, environnement seul) sont à montrer à l'utilisateur au prochain jalon.
