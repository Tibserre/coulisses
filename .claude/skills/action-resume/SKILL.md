---
name: action-resume
description: Crée ou modifie une action de résumé Coulisses (Résumé Impro, Retours de jeu par comédien, Idées de scènes, Prochaines étapes, Résumé court…) ou le cadre système de génération, puis organise une comparaison à l'aveugle avant adoption. À utiliser pour tout travail sur les prompts de génération.
argument-hint: <nom de l'action> [ce qu'il faut changer]
---

# Action de résumé : $ARGUMENTS

## Règles de rédaction
- Lis d'abord `docs/produit/prompt-resume-impro.md` : c'est le **témoin** OpenWhispr, la barre de qualité à égaler. Sa structure est discutable. Ne le modifie pas, et n'en recopie ni la consigne de langue ni la règle de repli : l'assemblage les ajoute.
- Français natif, écrit directement en français et non traduit de l'anglais. Vocabulaire de l'impro conservé tel quel.
- Le prompt de l'action ne contient **que** sa consigne propre. Le cadre système, la règle de repli, la consigne de langue, le contexte et le transcript sont ajoutés par l'assemblage (spec §7.9) : ne les recopie pas.
- Toute action doit :
  - dire quoi faire quand le contenu est pauvre (renvoyer à la règle de repli, jamais une réponse vide) ;
  - interdire d'inventer (sujets, décisions, attributions) ;
  - garder l'attribution des idées aux personnes nommées, en distinguant personne et personnage ;
  - distinguer ce qui est décidé de ce qui reste une piste.
- Les actions fournies vivent dans `src/coulisses_app/prompting/textes/actions/<id>.md` : un en-tête (nom, description), puis le prompt. Celles de l'utilisateur, et ses versions modifiées, sont en base (table `action`).

## Comparer avant d'adopter
Une nouvelle version ne remplace l'ancienne qu'après comparaison :
1. Génère les deux versions sur **la même vraie séance** : même modèle, même `num_ctx`, même graine.
2. Présente-les à l'utilisateur **à l'aveugle** : ordre aléatoire, étiquetées A et B, avec la grille d'`evaluation.md` §2 (fidélité, attribution, décisions vs pistes, vocabulaire, complétude, français naturel, structure).
3. Relève toi-même les inventions factuelles, en vérifiant chaque décision et chaque attribution contre le transcript.
4. L'utilisateur tranche. Consigne le résultat dans le commit (`résumés : …`).

## Vérifications
- Le test de l'assembleur passe : ordre des blocs, présence de la consigne de langue, noms corrigés utilisés.
- Aucune troncature : le nombre de tokens de la séance test tient dans `num_ctx`, sinon le résumé par sections a bien été déclenché.
