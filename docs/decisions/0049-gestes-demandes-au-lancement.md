# 0049 — Une fenêtre au lancement pour les mises à jour qui attendent une action

Statut : Acceptée (2026-10-19, choix de l'utilisateur : ouverture au lancement et point sur « Réglages », même fenêtre au premier lancement, une mise à jour à la fois avec ses sorties en boutons, gains chiffrés publiés par le moteur v1.11.0, ADR 0050 du moteur). Précise 0036. Onglet « Transcription » devenu « Ce Mac » : précisé par 0051.

## Contexte
Le moteur v1.10.0 transcrit avec un autre modèle (ADR 0048 du moteur). Chez un ami, l'ancien reste installé à côté du nouveau tant qu'il ne le supprime pas : deux modèles pour un même travail, 4,7 Go perdus. Le moteur v1.8 avait déjà demandé un nouvel environnement. Jusqu'ici, seule la section « Modèles » des Réglages le montrait (ADR 0036), sans dire qu'un modèle est remplacé ni pourquoi. Le moteur le dit pourtant : `readiness().missing`, `installed()` (`replaced_by` sur un modèle installé qui n'est plus exigé, environnements à `current` faux, `label`), `catalog()` (`replacement_note`, en français). Une première forme, une liste de gestes avec un bouton chacun, a été jugée peu claire par l'utilisateur. Principes : P1 (téléchargement sur demande), P6 (rien de codé en dur), P8 (suppression explicite).

## Décision
- **Les mises à jour qui attendent une action** se déduisent de la vue des modèles, sans liste propre à une version. Il y en a trois sortes, dans cet ordre :
  1. **un modèle remplacé** (`replaced_by`) ;
  2. **ce qui manque au traitement** à part cela (`readiness`), modèles et environnements regroupés ;
  3. **les environnements d'un ancien moteur** (`current` faux), regroupés.
  Une prochaine mise à jour du moteur de ces sortes s'affiche sans code nouveau.
- **Une fenêtre** les montre une à une, à chaque lancement de l'app, s'il en reste une qui n'est pas écartée. Elle ne s'ouvre ni pendant un enregistrement ni sur sa page.
- **Chaque mise à jour se dit en peu de mots**, pour tout le monde et pas seulement pour des techniciens, dans cet ordre :
  1. sa nature, en petit : « Mise à jour du moteur de transcription » (« Bienvenue dans Coulisses » au premier lancement) ;
  2. le titre : « Une action est attendue de votre part » ;
  3. une phrase : « Un nouveau modèle de transcription, plus léger, peut remplacer celui que vous utilisez. » ;
  4. pour un remplacement, trois cases chiffrées au plus : vitesse (`replacement_speedup`, « aussi rapide » à ×1, « plus lente » en dessous) et qualité (`replacement_quality`), mesurées au banc du moteur, et poids, d'après les tailles de son catalogue. Une sortie qui télécharge dit toujours « depuis internet », avec la taille quand le moteur l'annonce. Leur source (`replacement_evidence`) n'apparaît qu'en mode développeur, et la mémoire n'est pas montrée. Sans ces mesures, la phrase du moteur (`replacement_note`) est montrée telle quelle ;
  5. ses **deux sorties**, en boutons, la recommandée d'abord.
  Rien d'autre : ni liste d'éléments, ni nom technique, ni pied de page.
- **Les sorties possibles :**

  | Cas | Sortie recommandée | Autre sortie |
  |---|---|---|
  | Le nouveau modèle manque | « Remplacer l'ancien par le nouveau » : télécharge le nouveau, puis supprime l'ancien une fois le nouveau installé | « Garder l'ancien pour l'instant » : rien ne change ; les séances ne peuvent pas être traitées, et la question revient au prochain lancement |
  | Le nouveau modèle est déjà là | « Supprimer l'ancien modèle » | « Garder l'ancien modèle » : écarté pour de bon |
  | Il manque de quoi traiter | « Télécharger » (« Tout télécharger » au premier lancement) | « Plus tard » : la question revient au prochain lancement |
  | Un ancien composant du moteur (environnement) est resté | « La supprimer » | « La garder » : écartée pour de bon |

  Rester sur l'ancien modèle n'est pas possible : le moteur n'en exige qu'un (un seul profil), et l'app ne choisit pas de modèle (P6).
- **Choisir une sortie, c'est confirmer.** Le bouton dit d'avance ce qu'il fera : la taille téléchargée, l'usage d'internet et la place libérée. Il tient lieu de la confirmation exigée par 0036. La suppression de l'ancien modèle après un remplacement est faite par l'app, mais décidée par ce choix : si le téléchargement échoue ou s'arrête, rien n'est supprimé.
- **Après un choix qui agit**, la fenêtre suit le téléchargement, qui continue si on la ferme et qu'on peut y arrêter, puis passe à la mise à jour suivante. Si l'ancien modèle ne peut pas être supprimé, la fenêtre se rouvre, dit pourquoi et repropose le choix. Les mises à jour écartées pour de bon sont gardées dans `app_setting` (clé `gestes_ecartes`), sans changement de schéma. Une mise à jour nouvelle rouvre la fenêtre.
- **Un point sur « Réglages »**, dans la colonne, tant qu'une mise à jour non écartée attend.
- **Dans Réglages, onglet « Transcription »**, un modèle remplacé le dit (« Remplacé, ne sert plus »), avec la note du moteur, et son bouton « Supprimer » est mis en avant (toujours confirmé). Tout y reste faisable, même ce qui a été écarté.

## Conséquences
- La vue des modèles se lit une fois au lancement (environ une seconde, en arrière-plan) : rien ne bloque l'ouverture.
- L'app monte au moteur v1.11.0, qui publie ces mesures pour un modèle remplacé ; une mesure absente (`null`) n'a pas de case.
- Si l'app se ferme pendant un remplacement, l'ancien modèle reste : au lancement suivant, la fenêtre propose de le supprimer.

## Alternatives écartées
- Une liste de gestes, un bouton chacun, avec « Plus tard » et « Ne plus me rappeler » en bas : jugée peu claire par l'utilisateur.
- Une fenêtre détaillée (quatre cases dont la mémoire, la phrase du moteur en plus des chiffres, la liste des éléments, la mention d'internet à part, un pied de page) : jugée lourde et trop dense.
- Ouvrir seulement après une mise à jour de Coulisses : une mise à jour remise à plus tard serait oubliée.
- Une liste écrite dans l'app pour chaque version : contraire à P6, à refaire à chaque version du moteur.
- Garder les mises à jour écartées dans le navigateur (`localStorage`) : perdues si la fenêtre de l'app change de stockage ; la base est sauvegardée.
