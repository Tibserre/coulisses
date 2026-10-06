# 0026 — Le titre à la demande, fait à partir des chapitres

Statut : Acceptée (2026-10-06, choix de l'utilisateur). Remplace, dans l'ADR 0025, le titre automatique après le traitement.

## Contexte
Après l'ADR 0025, la fin du traitement lançait encore deux appels à Ollama : les chapitres, puis le titre. Chacun relisait la transcription entière, soit environ 36 000 tokens pour une séance de 1 h 30 et deux minutes de calcul intensif avec qwen3.8. L'utilisateur veut éviter de consommer pour rien, surtout sur batterie, et juge qu'un titre n'a pas besoin de toute la transcription.

## Décision
- Après une chaîne réussie, la file ne prépare plus que **les chapitres**.
- **Le titre se demande** sous le titre de la séance (« Proposer un titre »), avec le modèle par défaut. En attendant, la séance s'appelle « Séance du … ». Un titre écrit par l'utilisateur n'est jamais remplacé, et le bouton n'apparaît pas tant qu'il existe.
- **Le titre lit le moins possible.** Il part des titres des chapitres (avec leur heure et leur type) quand il y en a. Sinon, il lit le dernier résumé, et en dernier recours la transcription. L'appel passe toujours par l'assemblage unique, consigne de français comprise (P4). La provenance dit ce qui a été lu (`input_kind` : `chapters`, `summary` ou `transcript`).

## Conséquences
- Un titre coûte quelques secondes, au lieu de relire la séance.
- Sa qualité dépend de celle des chapitres. S'ils changent après coup, le titre ne change pas tout seul : on le redemande.
- Il n'y a plus d'appel combiné « chapitres et titre » à envisager. Un tel appel avait été proposé, puis rendu inutile par cette décision.

## Alternatives écartées
- Un seul appel pour les chapitres et le titre : il économise une lecture, mais le titre reste automatique.
- Garder le titre automatique en le faisant à partir des chapitres : l'utilisateur veut qu'il soit à la demande.
