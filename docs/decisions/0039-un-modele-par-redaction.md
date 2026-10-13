# 0039 — Un modèle de langage par rédaction : titre, chapitres, résumés

Statut : Proposée (2026-10-12), en attente de la validation de l'utilisateur. Demande, mot pour mot : « Il me faudrait toute une page de gestion du modèle LLM utilisé pour Generation du titre génératoin des chapitres génération de résumé genre que je puisse choisir parmis les mod!les llm ». Précise, dans l'ADR 0022, la ligne « le modèle choisi dans l'interface devient le défaut ».

## Contexte
Un seul modèle par défaut servait à tout : le titre, les chapitres (après chaque traitement, ADR 0024) et les résumés. Il ne se choisissait que depuis l'onglet Résumé d'une séance, et ce choix changeait aussi le modèle du titre et des chapitres, sans que rien ne le dise. Les trois rédactions n'ont pas les mêmes besoins : un titre est une ligne, les chapitres une liste courte, un résumé un long texte où la qualité compte le plus.

## Décision
- **Un modèle par rédaction** : titre, chapitres, résumés. Chacun se choisit dans Réglages, onglet « Rédaction », parmi les modèles installés dans Ollama. La liste vient d'Ollama, rien n'est nommé dans le code (P6).
- Chacun est gardé dans `app_setting` (`modele.titre`, `modele.chapitres`, `modele.resume`), sans changement de schéma. Tant qu'une rédaction n'a pas le sien, elle prend l'ancien défaut (`modele`), sinon celui de `prompting/textes/reglages.toml`.
- Le modèle choisi à la main dans l'onglet Résumé d'une séance devient celui des **résumés** seulement.
- Un changement vaut pour ce qui est demandé ensuite. Ce qui est déjà rédigé garde le modèle qui l'a écrit, dans sa provenance (P7).
- L'onglet des modèles du moteur s'appelle désormais « Transcription », à côté de « Rédaction ».

## Conséquences
- `GET /api/modeles` donne le modèle de chaque rédaction (`writings`), et `PUT /api/reglages/modeles/{redaction}` le change. L'ancien `PUT /api/reglages/modele` disparaît.
- Un modèle choisi puis retiré d'Ollama reste affiché, marqué « absent d'Ollama ». La rédaction échoue alors de façon visible (ADR 0022).
- Installer un nouveau modèle reste l'affaire d'Ollama : Coulisses n'en télécharge aucun (P1).
