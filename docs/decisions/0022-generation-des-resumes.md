# 0022 — Générer les résumés : une exécution de l'application, une fenêtre jamais dépassée

Statut : Acceptée (2026-10-06 : l'utilisateur choisit `qwen3.6:35b-mlx` par défaut, avec un sélecteur relié à Ollama dans l'application). Précision du 2026-10-06 sur le titre coupé après sa première ligne : validée par l'utilisateur le même jour. Après la chaîne, la file ne prépare plus de résumé (ADR 0025).

## Contexte
Le titre et les résumés sont faits par l'application (spec §7.9), par le LLM local (Ollama sur 127.0.0.1), et par un seul chemin (P4, `prompting/`). Ollama tronque **en silence** ce qui dépasse `num_ctx`. Sa version 0.35 n'offre aucun moyen de compter les tokens d'un texte avant de l'envoyer. Chaque résultat doit garder sa provenance (P7) et le prompt envoyé mot pour mot (rules/prompts.md).

## Décision
- **Une génération est une exécution de l'application** (ADR 0018), dans `runs/summarize-…` ou `runs/title-…`. Elle contient :
  - `spec.json` : l'action, le modèle et les réglages ;
  - `calls/NN-prompt.txt` et `calls/NN-response.md` : chaque appel, mot pour mot ;
  - `output.md` : le résultat ;
  - `provenance.json` : le schéma publié dans `schemas/generation-provenance.schema.json`. Il donne le modèle et son empreinte, `num_ctx`, la température, la graine, les tokens comptés par Ollama, les durées, la stratégie, l'exécution « qui a dit quoi » d'origine et le nombre de corrections prises en compte.
- **Les tokens sont estimés avant l'envoi, puis vérifiés après.**
  - Avant : une estimation volontairement haute, à 1,8 caractère par token. Mesuré le 2026-10-06 avec `qwen3.6` sur une vraie séance : 3,0 caractères par token en moyenne, 2,1 sur les répliques courtes. Si le prompt dépasse `num_ctx` moins la place de la réponse, la séance est résumée par parties, puis les parties sont fusionnées. Chaque appel passe par l'assemblage complet, consigne de français comprise, et la génération l'indique.
  - Après : la génération échoue de façon visible dans quatre cas : Ollama ne rapporte pas ses comptes de tokens ; la fenêtre a été atteinte (`prompt_eval_count` + `eval_count` ≥ `num_ctx`) ; le prompt comptait plus de tokens que l'estimation, qui n'est alors plus une majoration sûre ; la réponse a été coupée (`done_reason = length`). Avec les modèles MLX, Ollama 0.35 ne tronque pas le prompt : il le traite en entier, puis coupe la réponse. Ce cas est donc attrapé. La réponse reçue est gardée dans `calls/`, mais n'est pas retenue comme résultat. Exception pour le titre (précisé le 2026-10-06) : seule sa première ligne est gardée, donc une réponse coupée plus loin est acceptée quand cette ligne est complète (suivie d'un saut de ligne). Avec MLX, Ollama ignore la demande de s'arrêter à la fin de la ligne, et les modèles enchaînent sur un résumé.
- **Rien sur le modèle dans le code (P6).** Le modèle par défaut, `num_ctx` (65 536, pour qu'une séance d'environ 1 h 30 tienne souvent en un appel), les places réservées, la température (0,3) et la graine (42) sont dans `prompting/textes/reglages.toml`. Le modèle choisi dans l'interface devient le défaut (`app_setting`). La liste des modèles vient d'Ollama.
- **Pas de raisonnement visible** : les appels demandent `think: false`, et la provenance l'enregistre avec la version d'Ollama. Un résumé est la réponse elle-même.
- **Une file commune.** Les générations sont des tâches (`job`, de sorte `generation`) dans la même file que la chaîne. Après une chaîne réussie, la file prépare les chapitres (ADR 0024), le titre, puis les résumés automatiques de l'espace (ADR 0020). Le titre ne remplace jamais un titre écrit par l'utilisateur.
- **Un résumé devient « périmé »** quand l'ensemble des corrections en vigueur n'est plus le même (comparé une à une, pas seulement en nombre), ou quand le « qui a dit quoi » a changé depuis qu'il a été généré. Il reste lisible, et on peut le relancer.

## Conséquences
- Un fichier de configuration, sans code, suffit pour changer le modèle par défaut, `num_ctx` ou l'estimation. Un `qwen3.8` se choisira dans l'interface dès qu'il sera installé dans Ollama.
- L'estimation prudente déclenche le découpage plus tôt que nécessaire. Le coût est un appel de plus sur les très longues séances, jamais une troncature.
- Le découpage suit le temps, pas encore les phases (étape 4 du plan).
- Si Ollama offre un jour le comptage des tokens, il remplacera l'estimation, et un nouvel ADR le consignera.

## Alternatives écartées
- Compter avec le tokenizer du modèle, dans l'application : il faudrait une bibliothèque et des fichiers de modèle hors du moteur (P6).
- Faire un premier appel pour mesurer le prompt : il doublerait le calcul, et il serait lui-même tronqué en silence si le prompt dépasse.
- Un `num_ctx` immense (262 144) pour ne jamais découper : beaucoup de mémoire, et une qualité moindre sur un contexte très long.
