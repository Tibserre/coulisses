---
paths:
  - "**/prompting/**"
  - "**/actions/**"
  - "docs/produit/prompt-resume-impro.md"
---

# Prompts et génération

- **Ordre d'assemblage immuable** (spec §7.9) : cadre système → prompt de l'action → règle de repli → consigne de langue française → contexte de séance → transcript `[mm:ss] Nom : texte` avec les marqueurs et les phases.
- La consigne de langue est ajoutée par l'assembleur, **pour toutes les actions, sans paramètre pour la désactiver**.
- **Français natif** : on écrit directement en français, sans passer par une traduction depuis l'anglais. Tutoiement ou impératif, cohérent dans un même prompt.
- Les noms viennent de la **vue corrigée** (rattachements des locuteurs, personnages « joué par X »), jamais des étiquettes brutes « Locuteur 3 » quand un nom existe.
- **Budget de contexte** : compter les tokens du prompt assemblé. Au-delà de `num_ctx` moins la marge de réponse, basculer vers un résumé par sections (par phase) puis une consolidation, et l'indiquer dans la génération. Chaque appel partiel et la consolidation passent par l'assemblage complet. Jamais de troncature.
- Toujours passer `num_ctx` explicitement à Ollama. Température et graine sont enregistrées dans la provenance.
- Une génération enregistre le prompt complet envoyé, mot pour mot.
- Modifier « Résumé Impro » ou le cadre système demande une comparaison côte à côte sur une vraie séance (skill `/action-resume`).
