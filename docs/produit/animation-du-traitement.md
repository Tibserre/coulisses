# Animation du traitement : de l'arrêt aux chapitres

Proposition validée par l'utilisateur le 2026-10-22. **Construits** (2026-10-23, ADR 0060) : les étapes 1 à 5, et l'écriture des chapitres dite sans indicateur qui tourne. **À venir** : les chapitres progressifs de l'étape 6, qui attendent un changement du service (voir « Ce qu'il faut d'abord »). Maquettes faites en conversation (Interface), avec les skills d'animation du dépôt, encadrés par la direction artistique.

## Principe

Ne bouger que pour une raison ; un fondu plutôt qu'un trajet ; une seule séquence orchestrée par moment. Durées de la DA : 160 ms (petits retours), 400 ms (entrée, sortie), 850 ms (le moment rare : l'ouverture de la relecture). Courbe `cubic-bezier(0.22, 1, 0.36, 1)`, sans rebond. Rien ne tourne en boucle. Mouvement réduit : tout change d'un coup.

## Le déroulé

1. **Traitement.** La page de la séance s'ouvre en fondu. Deux grands disques immobiles, comme ceux de la pause et de l'arrêt : « Le texte » (transcription puis alignement) et « Les voix » (diarisation). Le moteur les fait **en même temps** : chacun son anneau brique, qui avance en 400 ms à chaque avancement publié (`progress.json`), sans rien inventer. Dessous, une phrase : « environ N min · vous pouvez fermer Coulisses ». Le texte transcrit arrive en gris, ligne par ligne, en fondu (aperçu jamais gardé, ADR 0058).
2. **Les voix finissent souvent avant le texte** : leur libellé devient « Les voix · prêtes ». Rien ne bouge.
3. **Qui a dit quoi** (attribution, courte et sans avancement) : la phrase devient « Qui a dit quoi · quelques secondes ». Aucun anneau qui tourne.
4. **Les voix arrivent.** Les deux disques laissent place, en fondu de 400 ms, à un seul disque dont l'anneau est découpé en une couleur par personne, à sa part de temps de parole mesurée (voix non nommée en gris, DA), avec la légende (nom, %). Les noms se posent sur le texte (fondu de 400 ms). Construit : la relecture remplace l'écran de traitement, et ce disque apparaît là où étaient les deux autres.
5. **La relecture s'ouvre.** Le disque s'efface (400 ms), puis l'espace se referme en 850 ms : le texte remonte, une seule fois. Les parts de parole restent là où elles existent déjà (les participants, dans les détails de la séance), pas en double.
6. **Les chapitres s'écrivent, progressivement** (décidé le 2026-10-22). L'emplacement de la frise montre jusqu'où le modèle a lu (une zone grise). Après chaque partie lue (15 min au plus, `partie_chapitres_min`), ses chapitres apparaissent, pâles et marqués « provisoire », dans la frise et en tête de leur passage dans le texte. Phrase : « Les chapitres s'écrivent · partie k sur N · vous pouvez déjà relire ».
   - Une coupure due à la lecture par parties se recoud quand la partie suivante continue le chapitre : la barre s'allonge, l'en-tête en trop s'efface (400 ms). C'est le seul vrai mouvement.
   - Puis « Les chapitres se vérifient · k sur M » : un type qui change (jeu ⇄ discussion) ne change que sa couleur.
   - Enfin les chapitres se fixent : couleur pleine, « provisoire » disparaît.
   - **Un chapitre provisoire n'est pas modifiable** (décidé le 2026-10-22) : on le voit, on ne le touche qu'une fois fixé, pour ne jamais perdre une correction.
7. Le **titre** reste à la demande (ADR 0026, confirmé le 2026-10-22) ; le résumé aussi.

## Ce qu'il faut d'abord

- Côté service (`prompting/`, territoire Rédaction et modèles) : publier, pendant le chapitrage, les chapitres de chaque partie lue (aperçu jamais gardé) et l'avancement (partie k sur N, puis vérification k sur M). Aujourd'hui, les chapitres ne sont enregistrés qu'à la fin, d'un bloc. Note de relais à écrire.
- Un ADR pour les chapitres progressifs, au moment de construire.
