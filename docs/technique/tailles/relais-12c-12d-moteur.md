# Relais : lots 12c et 12d, un moteur plus léger (pour « Moteur »)

De : la conversation « Alléger Coulisses » (étape 12 du plan de l'app), le 2026-10-16. Ordre validé par l'utilisateur ce jour : 12b (Distribution), 12c-1 et 12d d'abord, en parallèle ; 12c-2 ensuite.

Mesures : `docs/technique/tailles/2026-10-16-v0.28.0.md` du dépôt de l'app (DMG v0.28.0, moteur v1.7.1). L'app n'importe ni librosa, ni torch, ni pandas, ni soundfile : tout ce qui suit vient du moteur, `coulisses[mlx-audio,pyannote,wav2vec2]`.

## 12c-1 — Dépendances du moteur (dans le Python de l'app)

| Quoi | Gain si retiré | Constat |
|---|---|---|
| `librosa` (extra `wav2vec2`) | 170 Mo, avec numba, llvmlite, soxr, pooch, soundfile… | n'est plus importé (commentaire de `engines/align/wav2vec2_ctc.py`, l. 99) |
| `pyannote-audio` (extra `pyannote`, le filet de `diarizen_filet`) | 286 Mo à lui seul : pandas, matplotlib, grpc et opentelemetry (47 Mo), sqlalchemy et optuna (par pyannote-pipeline), torchmetrics, lightning… | pour une inférence ; DiariZen a déjà son pyannote dans son environnement |
| torch | présent deux fois : 617 Mo dans l'app (alignement, filet), 310 Mo dans DiariZen | voir 12c-2 |

Demandé :
1. Retirer `librosa` de l'extra `wav2vec2` s'il n'est vraiment plus utilisé.
2. Étudier comment ne plus tirer, pour le filet, ce qui ne sert qu'à l'entraînement, aux graphiques ou à la télémétrie. Par exemple : le filet dans l'environnement de DiariZen, qui a déjà pyannote ; ou une dépendance plus étroite. À toi de choisir, par le banc.

Gain estimé : 0,3 à 0,45 Go dans l'app.

## 12d — Modèles plus légers (banc d'essai)

| Modèle | Taille | Piste |
|---|---|---|
| `qwen3-asr-1.7b` | 4,70 Go | quantifié 8 bits (≈ 2 Go) ou 4 bits (≈ 1,2 Go), en MLX |
| `wav2vec2-ctc-french` | 1,26 Go | demi-précision (≈ 0,63 Go) |

Retenus seulement si le banc le prouve :
- pour la transcription, la justesse du texte tient ;
- pour l'alignement, les horodatages tiennent (P2), dans la tolérance de ta méthode.

Ce qui change de modèle passe par le catalogue et le profil (P6). Les anciens modèles ne se suppriment chez l'utilisateur que sur sa décision, depuis la page des modèles (ADR 0036, P8).

Gain estimé : 2,5 à 3,5 Go à télécharger et sur le disque, et sans doute de la mémoire et du temps.

## 12c-2 — Plus tard : les étapes à torch hors de l'app

Seulement un avis pour l'instant, après 12c-1. Peut-on mettre les étapes qui ont besoin de torch (alignement, filet) dans des environnements installés à la demande, comme DiariZen ? L'app et chacune de ses mises à jour perdraient environ 0,8 à 1 Go. Cela demandera un ADR : à proposer à l'utilisateur, avec les conséquences pour l'app (ADR 0040 : installation, mises à jour).

## Mesure attendue
- **Côté moteur :** le banc, avant et après, et des sorties identiques quand seul l'empaquetage change (12c-1).
- **Côté app :** une fois l'étiquette poussée, « Alléger Coulisses » monte de version et relance `scripts/mesurer-tailles.py --comparer docs/technique/tailles/2026-10-16-v0.28.0.json`. Donne-lui le gain que tu attends.

## Contrat
- Une version compatible : mineure ou corrective.
- Si un extra change de nom ou de contenu, dis-le dans le `CHANGELOG.md` : l'app en dépend par `coulisses[mlx-audio,pyannote,wav2vec2]`.
- Un nouveau modèle ou un profil changé : version mineure et note de version.
- Aucune nouvelle dépendance lourde ou native sans l'accord de l'utilisateur.
