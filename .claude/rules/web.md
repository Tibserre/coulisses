---
paths:
  - "**/*.tsx"
  - "**/*.ts"
  - "**/*.css"
---

# Interface web

- Stack : React 19 + Vite + TypeScript strict + Astryx (ADR 0007, acceptée). Relis ses points de vigilance avant d'ajouter une dépendance structurante.
- **Aucune ressource distante** : polices, icônes, images et scripts sont embarqués. Pas de CDN, pas d'analytics, pas de Google Fonts. L'API est sur le même origin (`127.0.0.1`).
- Tous les textes affichés sont en français ; pas de chaîne anglaise visible.
- Le copier-coller fonctionne partout, y compris via le clic droit : ne jamais bloquer `contextmenu` ni `user-select` sur du texte.
- Les transcripts longs (des milliers de tours) sont virtualisés. Le lecteur audio et le surlignage du mot courant restent fluides sur une séance de 2 h.
- Chaque état d'une séance ou d'une étape est visible : en file, en cours (avec progression), réussie, échouée (erreur lisible), périmée, audio purgé.
- Toute action destructrice (suppression, purge anticipée) demande une confirmation explicite.
- Accessibilité : navigation au clavier sur la relecture (lecture/pause, ligne suivante, renommer).
