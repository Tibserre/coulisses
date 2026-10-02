# 0007 — Interface : React + Vite + TypeScript, design system Astryx

Statut : Acceptée (2026-09-24). Choix ferme de l'utilisateur, sans condition préalable.

## Contexte
Interface riche et haut de gamme : relecture de transcripts de 2 h synchronisés avec l'audio, forme d'onde, édition, comparaison côte à côte. L'utilisateur envisage Astryx, le design system open source de Meta (React 19 + StyleX, plus de 150 composants accessibles, thèmes, mode sombre, CLI et serveur MCP pensés pour les agents).

## Décision
- React 19 + Vite + TypeScript strict.
- **Astryx** comme design system, avec son serveur MCP branché dans Claude Code pendant la phase interface.
- Forme d'onde et lecture : bibliothèque dédiée (ex. wavesurfer.js), à confirmer.
- Listes longues virtualisées (transcripts de plusieurs milliers de tours).
- PWA : manifeste + service worker, **tous les assets locaux** (polices embarquées, aucun CDN) pour respecter P1.
- Textes de l'interface en français.

## Points de vigilance (au début de la phase interface)
Astryx est retenu. Ces points ne remettent pas le choix en cause : ils indiquent quoi contourner, compléter ou signaler.
- Maturité d'Astryx (en bêta en septembre 2026) et compatibilité de StyleX avec Vite.
- Aucune ressource distante chargée à l'exécution (polices, icônes, télémétrie) : P1 prime. Une fuite réseau se neutralise ou se signale, elle ne s'accepte pas.
- Composants manquants pour la relecture (listes virtualisées, menus contextuels, raccourcis clavier) : compléter par une bibliothèque dédiée.

## Alternative écartée
React + Vite + TS avec shadcn/ui (Radix + Tailwind), plus mûr et très bien connu des agents.
