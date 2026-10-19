# Relais : lot 12c-2 fait, v0.30.0 (pour « Pilotage », « Distribution et publication », « Interface »)

De : la conversation « Alléger Coulisses », le 2026-10-19. Aucune de ces conversations n'était ouverte : ce relais tient lieu de message.

## Ce qui est fait
L'app passe au moteur v1.8.0 (ADR 0047 du moteur, choix A et B validés par l'utilisateur). Fusion dans `main` : v0.30.0 (`ca60f96`). L'alignement et le filet pyannote tournent dans un environnement isolé `torch`, installé à la demande comme DiariZen. L'app ne tire plus torch, pyannote ni leurs dépendances.

Mesuré sur une app d'essai, signée ad hoc et jamais publiée ([2026-10-19-v0.29.0-moteur-v1.8.0.md](2026-10-19-v0.29.0-moteur-v1.8.0.md)), par rapport à la référence v0.28.0 :

| | Avant | Après |
|---|---|---|
| App installée | 1,99 Go | **732 Mo** |
| DMG | 773 Mo | **295 Mo** |
| Environnement `torch`, nouveau, téléchargé une fois | — | 1,14 Go |

Vérifications :
- 416 tests passent, ainsi que 2 tests lents sur les vrais modèles ;
- l'essai du paquet passe ses étapes 1 à 4 : traitement complet réseau coupé, depuis l'app construite. L'étape 5 a été arrêtée parce que la Coulisses publiée était ouverte ;
- vérifié à la main : rien d'écrit dans l'app, signature intacte, aucune tentative réseau.

## Pour Pilotage
- **Plan à mettre à jour.** Le point de départ et 12c-2 sont encore décrits comme « à faire », avec torch dans l'app : 12c-2 est fait, à mettre à jour avec les tailles ci-dessus.
- **Ce qui reste de l'étape 12 :**
  - 12b (Distribution) ;
  - 12d (banc du Moteur en cours) ;
  - l'encodeur FLAC du ffmpeg embarqué, pour activer 12e dans l'app publiée (relais de Distribution) ;
  - 12f (lot 11g).

## Pour Distribution
- **Un environnement de plus chez un ami.** Il doit installer `torch` (≈ 1 Go) depuis Réglages > Transcription. La page des modèles le montre déjà, d'après `readiness()`, et un traitement sans lui le dit (`environment_missing`). Les notes de version de v0.30.0 doivent le dire clairement.
- **À la publication, l'essai du paquet doit passer en entier.** Il faut fermer la Coulisses publiée avant de le lancer.
- **12b se mesure maintenant sur une app de 732 Mo**, où torch n'est plus. Les gains de tests, d'en-têtes et de stubs sont à remesurer.

## Pour Interface
Dans `web/src/components/ModelsSection.tsx` (vers la ligne 192), chaque environnement installé est décrit comme servant à « qui parle quand ». C'est faux pour `torch`, qui sert d'abord à l'alignement. Il faudrait un libellé neutre (« utilisé par le traitement »). Le mieux serait le rôle donné par le moteur lui-même : c'est demandé à la conversation Moteur (libellé et étapes de chaque environnement).
