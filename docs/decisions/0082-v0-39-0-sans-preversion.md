# 0082 — La v0.39.0 publiée sans préversion

Statut : Acceptée (2026-11-11, par l'utilisateur : « si tu testes bien on sera bon », relayé par Pilotage, puis confirmé dans la session de Distribution : publier « directement », sans préversion). Exception ponctuelle à 0040 (étapes 3 et 4 de la publication) ; 0040 reste la règle pour les versions suivantes.

## Contexte
- ADR 0040 : une version part d'abord en **préversion** sur GitHub, hors de l'appcast. L'utilisateur l'installe et s'en sert, puis `scripts/publier.py --confirmer` la publie pour de bon, et les amis la reçoivent.
- La v0.39.0 change le premier usage (accueil en six étapes, ADR 0079), livre pyannote community-1 dans l'app (ADR 0081 du moteur) et passe au moteur v1.15.0. Une préversion installée sur le Mac de l'utilisateur ne montre rien de cela : son Mac a déjà ses modèles et ses séances.
- Ce que vit une personne qui reçoit l'app a donc été essayé autrement, avant la publication, sur l'app construite depuis `essai/v0.39.0` (signée ad hoc) :
  - un parcours de bout en bout par l'utilisateur, sur des dossiers vides (données, modèles, environnements) et sans jeton Hugging Face, refait à chaque correction ;
  - l'essai du paquet (`scripts/essai-paquet.sh`) ;
  - les tests complets ;
  - `main` vérifiée identique à l'essai (`git diff essai/v0.39.0 main`, au CHANGELOG près).

## Décision
- La v0.39.0 est publiée sans préversion. Tout est préparé comme d'habitude (`publier.py vX.Y.Z` : tests de l'étiquette, construction, signature, essai du paquet, exigence désignée, ouverture de la base de la version d'avant), puis `--envoyer` et `--confirmer` se suivent sans que l'utilisateur installe la préversion entre les deux.
- `--confirmer` garde son contrôle : le DMG publié est celui préparé.

## Conséquences
- La seule étape qui ne se fait pas est la mise à jour par Sparkle depuis la v0.38.3, sur un Mac qui a déjà des séances. Elle n'est essayée qu'une fois publiée. Si elle rate, on corrige par une version suivante (0040 : Sparkle ne revient pas en arrière).
- Une prochaine version sans préversion demande une nouvelle décision de l'utilisateur.
