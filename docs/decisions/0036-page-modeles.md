# 0036 — La section « Modèles » des Réglages, par l'API de modèles du moteur

Statut : Acceptée (2026-10-09). S'appuie sur l'ADR 0035 du moteur (v1.5.0, complétée en v1.6.0). Termine l'étape 10 du plan. Mention « seul moment où Coulisses utilise internet » : reformulée par 0040. Gestes demandés au lancement et modèle remplacé : précisés par 0049. Affichage hors mode développeur et place dans les Réglages (onglet « Transcription ») : précisés par 0051.

## Contexte
La spec (§7.12) veut voir, depuis l'app, les modèles du moteur : ce qui est installé, leur taille, ce que le traitement exige ; les supprimer après confirmation ; les télécharger seulement sur demande, seule exception au hors-ligne (P1). Jusqu'à la v1.4.0, le moteur n'offrait qu'une commande pour humain ; les erreurs `model_missing` renvoyaient vers le Terminal. La v1.5.0 publie `catalog`, `installed`, `readiness`, `download`, `install_environment`, `remove`, `stop_downloads` et trois schémas (`model-catalog`, `model-inventory`, `readiness`).

## Décision
- **Une section « Modèles » dans les Réglages**, avec une ligne par modèle du catalogue :
  - à quoi il sert (l'étape, en français) et son nom ;
  - s'il est nécessaire au traitement ;
  - son état : installé, abîmé, téléchargement interrompu, pas installé, ou en cours avec sa progression ;
  - son action : Télécharger, Reprendre, Arrêter ou Supprimer.
  
  En tête de la section, une phrase dit si tout est prêt pour traiter les séances (`readiness`). Sinon, elle dit ce qui manque. Les environnements de calcul (DiariZen) ont aussi leur ligne. La description, la source, la révision et la licence apparaissent en mode développeur.
- **Un environnement que le traitement n'utilise pas** (ancienne version, ou installation interrompue) se supprime aussi, après confirmation (`remove_environment`, moteur v1.6.0). Celui du traitement n'a pas de bouton ; le moteur le refuserait de toute façon (`current_environment`, dit en français).
- **Télécharger** et installer sont **confirmés**, avec la taille annoncée et la mention « c'est le seul moment où Coulisses utilise internet ». **Supprimer** est confirmé aussi : la confirmation dit si le traitement en a besoin.
- **Le service** fait les téléchargements en arrière-plan, un à la fois par modèle (`engine_models.py`). L'interface suit la progression deux fois par seconde pendant un téléchargement, puis relit l'état du disque à la fin. **À l'arrêt du service, `stop_downloads()`** arrête tout ; les dossiers partiels sont gardés, et le téléchargement reprend la fois suivante.
- **Les erreurs du moteur** (`ModelActionCode`) sont dites en français par leur code. La place manquante est donnée en Go ; pour des conditions à accepter, l'app donne un lien vers la page. Le message anglais du moteur reste disponible en mode développeur.
- Les erreurs d'étape `model_missing`, `model_altered` et `environment_missing` renvoient désormais à « Réglages, section Modèles », plus au Terminal.
- L'app ne nomme aucun modèle (P6) : tout ce qu'elle affiche vient du catalogue du moteur.

## Conséquences
- `installed()` mesure les tailles, en une seconde environ : la section se lit à l'ouverture des Réglages, pas en boucle.
- L'app et `coulisses-models` ne se voient pas (ADR 0035 du moteur) : n'utiliser que l'un des deux à la fois.
- Une page de conditions s'ouvre dans le navigateur (l'app du Dock envoie les liens extérieurs au navigateur, ADR 0034).
