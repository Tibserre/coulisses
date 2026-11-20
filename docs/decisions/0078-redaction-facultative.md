# 0078 — Ollama facultatif : sans modèle de langage, les rédactions attendent

Statut : Acceptée (2026-11-10, choix de l'utilisateur relayé par Pilotage, mot pour mot : « Ollama, tout comme le système de résumés, doit être facultatif, si la personne n'a pas ollama, elle a accès à comment on fait pour l'installer, mais ça ne pose aucun souci »). Précise 0024 et 0039.

## Contexte
- Une séance se traite par le moteur jusqu'au transcript. Les chapitres, le titre et les résumés sont écrits par un modèle de langage, par Ollama (`prompting/`).
- Sans Ollama, la détection des chapitres lancée après le traitement échouait, comme un titre ou un résumé demandé : un échec visible, avec « Relancer » (ADR 0024).
- Une installation neuve n'a pas forcément Ollama, ni de modèle dedans.

## Décision
- **Sans modèle de langage, une rédaction attend au lieu d'échouer.** C'est le cas quand Ollama ne répond pas sur ce Mac (`ollama_absent`) ou quand il répond sans aucun modèle installé (`no_model`). Vérifié quand la rédaction est prise dans la file, par une requête à 127.0.0.1 seulement (P1).
  - Elle reste en file, marquée dans ses paramètres (`GenerationParams.waits_for_writer`), sans nouvel état de tâche ni migration. Les autres tâches passent devant.
  - La séance dit qu'elle n'est pas faite, pas qu'elle a échoué : `waits_for_writer` dans l'état des chapitres (`GET /api/seances/{id}/chapitres`) et dans les rédactions en file (`pending` de `GET /api/seances/{id}/resumes`).
- **Le traitement ne dépend jamais d'Ollama.** Le transcript, les voix et leurs noms se font sans lui.
- **Elle se fait d'elle-même une fois le modèle de langage là.** Ce qui attend est revu au démarrage, puis toutes les 60 secondes tant que quelque chose attend, et chaque fois que les réglages lisent la liste d'Ollama (`GET /api/modeles`).
  - Elle part avec le modèle demandé s'il est installé.
  - Sinon, elle prend celui choisi maintenant pour cette rédaction (Réglages, onglet Rédaction), s'il est installé.
  - Sinon, elle part avec le modèle demandé et échoue en le disant, comme avant (ADR 0039).
- **L'API dit si un modèle de langage peut écrire** : `GET /api/modeles` gagne `available` (Ollama répond, avec au moins un modèle). L'interface en tire un lien discret vers la façon d'installer Ollama. Coulisses n'installe ni Ollama ni aucun modèle (P1).
- Un modèle choisi puis retiré, alors que d'autres sont installés, échoue toujours de façon visible (ADR 0039) : c'est un choix à refaire, pas une absence d'Ollama.

## Conséquences
- Précise l'ADR 0024 : « Si la détection échoue (Ollama absent…) » ne vaut plus pour l'absence d'Ollama. Une réponse illisible reste un échec, avec « Relancer ».
- Demander de nouveau une rédaction qui attend déjà (« Détecter à nouveau », le même résumé) ne la met pas deux fois en file : celle qui attend reste seule.
- Si ce qui attend ne peut pas être revu (une erreur de la base), l'état du service le dit (`writer_release_error`), et Coulisses réessaie chaque minute.
- Une rédaction qui attend peut rester en file longtemps. Elle ne bloque rien, et l'arrêter ou la supprimer suit les mêmes règles qu'une rédaction en file.
- Ollama arrêté au milieu d'une rédaction fait toujours échouer cette rédaction : seule son absence au départ la fait attendre.
