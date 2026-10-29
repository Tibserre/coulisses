# 0070 — Arrêter un traitement, ou supprimer sa séance pendant qu'il tourne

Statut : Proposée (2026-10-29 ; le geste est demandé par l'utilisateur à Interface, la façon de le représenter est à accepter). Précise l'ADR 0018 (la file des tâches) et l'ADR 0046.

## Contexte
Jusqu'ici, une tâche ne s'arrêtait qu'à la fermeture de l'app (`stop_all`, reprise au démarrage) ou par un plantage (`close_interrupted`). L'utilisateur veut arrêter un traitement qu'il ne veut finalement pas faire, et supprimer une séance importée par erreur sans attendre la fin. La table `job` n'accepte que les états `queued`, `running`, `done` et `failed` (CHECK) : un état `cancelled` serait un changement de schéma.

## Décision
- **Arrêter** (`POST /api/seances/{id}/arreter`) vaut pour le traitement en file ou en cours.
  - En file : la tâche est arrêtée sur-le-champ.
  - En cours : plus aucune étape ne démarre, et celles qui tournent sont annulées par le moteur (`cancel`). Leurs exécutions restent telles qu'il les a closes (« Cancelled », P5). Les étapes réussies sont gardées.
  - L'appel attend la fin, 30 s au plus. Au-delà, il répond 202 : l'arrêt est demandé et se fera quand l'étape en cours finira.
- **Une tâche arrêtée** est `failed`, avec `error` = « Traitement arrêté à votre demande. » et `stopped_at` dans ses paramètres. Pas de nouvel état, pas de migration. La séance le dit (`processing_stopped`), distinct d'un échec.
  - « Reprendre » relance ce qui reste, comme après un échec, et efface `stopped_at`.
- **Un vrai échec reste dit.** Si une étape a échoué pour de bon (diarisation refusée, modèle absent…), la tâche garde cet échec et ce qu'il faut faire, même si l'utilisateur arrête le reste (P8). Si tout avait déjà réussi, l'arrêt arrive trop tard : la tâche est faite, sa version en place. Une étape que le moteur a été prié d'annuler et qui lève une erreur en route (l'annulation refusée par macOS, par exemple) compte comme arrêtée : son erreur reste dans l'exécution et le journal. Une étape pas encore annulée qui plante reste un échec.
- **Supprimer une séance pendant son traitement** (`DELETE /api/seances/{id}`, après confirmation dans l'interface) l'arrête d'abord, puis supprime, en un appel. Si l'arrêt n'a pas abouti dans le délai, rien n'est supprimé, et l'erreur demande de réessayer. Le dossier n'est jamais effacé pendant qu'une étape y écrit. Depuis le moteur v1.13.2, une étape ne rend la main qu'une fois ses processus finis ; si l'un d'eux tourne encore 10 s après l'arrêt (`HelpersStillRunning`), l'étape compte comme arrêtée, et la suppression est refusée (« réessayez dans un instant ») tant que son groupe de processus a un processus vivant. Ce refus ne dure que 10 minutes après la clôture de l'étape (un numéro de groupe peut être redonné plus tard à un autre programme) : passé ce délai, la séance est supprimée et la suppression le dit. Une provenance illisible refuse aussi la suppression, avec la raison.

## Conséquences
- Les pistes d'une séance arrêtée restent en WAV jusqu'à la fin d'un traitement repris (ADR 0046). Les convertir à l'arrêt bloquerait la suppression demandée dans le même geste.
- Un état `cancelled` plus tard demanderait une migration : tant qu'il n'y en a pas, « arrêté » se lit dans `stopped_at`, jamais dans le texte de l'erreur.

## Alternatives écartées
- Ajouter `cancelled` au CHECK de `job.state` : un changement de schéma, pour une information que les paramètres de la tâche portent déjà.
- Supprimer sans arrêter (refus tant que la tâche tourne, la règle d'avant) : l'utilisateur doit attendre la fin d'un traitement qu'il ne veut pas.
