# 0025 — Des résumés à la demande, avec le modèle choisi dans une liste

Statut : Acceptée (2026-10-06, choix de l'utilisateur). Remplace en partie les ADR 0020 (résumés automatiques par espace), 0022 (file des générations après la chaîne) et 0024 (ordre de la file). Remplacée en partie par 0026 (le titre) et par 0060 (le modèle ne se choisit plus au moment de rédiger ; la comparaison passe en mode développeur).

## Contexte
Jusqu'ici, la fin du traitement lançait les chapitres, le titre, puis les résumés automatiques de l'espace (le Résumé Impro pour une troupe), chacun par Ollama. Avec six actions fournies, l'utilisateur a jugé qu'il y aurait trop de générations pour une seule transcription : un bon résumé suffit, les autres se font quand on en a besoin. Chaque génération occupe aussi le Mac plusieurs minutes avec un gros modèle.

## Décision
- Après une chaîne réussie, la file ne prépare que **les chapitres puis le titre**, avec le modèle par défaut. Ce sont deux appels courts, utiles à la relecture.
- **Aucun résumé ne se fait tout seul.** L'utilisateur choisit un résumé et un modèle dans la liste d'Ollama (onglet Résumé), puis le lance. Le modèle qu'il choisit devient le défaut (ADR 0022).
- Le réglage d'un espace ne dit plus quels résumés se lancent, seulement **le résumé proposé en premier**. La colonne `action_preference.auto_run` garde ce sens, et les modèles de départ le remplissent (le Résumé Impro pour une troupe, le compte rendu pour des réunions de travail). Le modèle par action dans l'espace (`action_preference.model`) n'est plus proposé ; la colonne reste, inutilisée.

## Conséquences
- Pas de migration : les colonnes restent, seul leur usage change.
- Ouvrir une séance juste traitée montre la transcription, ses chapitres et son titre, mais pas encore de résumé. L'onglet Résumé l'invite à en lancer un.
- Si un réglage par espace redevient utile (lancer un résumé seul la nuit, par exemple), il fera l'objet d'un nouvel ADR.

## Alternatives écartées
- Garder un résumé automatique par espace : c'était l'état précédent, refusé par l'utilisateur.
- Tout à la demande, titre et chapitres compris : la relecture perd la frise et un titre lisible dans la bibliothèque, pour deux appels courts.
