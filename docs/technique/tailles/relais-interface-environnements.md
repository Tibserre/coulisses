# Relais : le rôle des environnements dans la page des modèles (pour « Interface »)

De : la conversation « Alléger Coulisses », le 2026-10-19. La conversation Interface n'était pas ouverte : ce relais tient lieu de message.

En passant au moteur v1.9.0, j'ai touché `web/`, ton territoire. La page des modèles écrivait en dur « pour qui parle quand » à côté de chaque environnement. C'était faux pour `torch`, qui sert à la transcription, à l'alignement et au filet de diarisation. Le moteur dit désormais le rôle de chaque environnement (`label`, `stages`), et l'interface l'affiche tel quel.

- `web/src/api.ts` : `EnvironmentInfo.label` et `stages`, `MissingPiece.label`.
- `web/src/models.ts` :
  - `missingEnvironments()` (nouveau, testé) : chaque environnement manquant une seule fois, avec son libellé ;
  - `readinessLine()` dit le libellé et ne répète pas un environnement exigé par plusieurs étapes.
- `web/src/components/ModelsSection.tsx` : le libellé du moteur, le nom technique en mode développeur seulement.

Reprends la mise en forme comme tu l'entends : les textes viennent du moteur, et l'app ne doit pas les réécrire (P6, P7).
