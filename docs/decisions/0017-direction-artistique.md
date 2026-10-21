# 0017 — Direction artistique : sobre et éditoriale, relecture en deux colonnes

Statut : Acceptée (2026-10-02 : l'utilisateur retient la finition « Texte de scène » sobre et l'organisation « Deux colonnes »). L'échelle typographique est **remplacée par 0038**. Le flou pour mettre une information au premier plan : permis par 0059.

## Contexte
L'interface repose sur Astryx (ADR 0007), dont le thème par défaut n'a pas d'identité. Du 28 septembre au 2 octobre 2026, plusieurs directions ont été comparées en direct dans l'atelier du moteur (ADR 0015), sur une maquette de l'écran de relecture. L'utilisateur a tranché au fil des essais :
- direction « Loge », DM Sans en titres, Figtree en texte ;
- pas de fond crème ni d'effet papier, jugés « signature IA » ;
- la mise en page « Texte de scène » est celle qui rend le mieux ;
- l'écran montre toute la transcription d'un côté, une vue d'ensemble et un résumé de l'autre ;
- l'interface doit rester valable pour tout type de réunion, et ne pas « sentir l'IA ».

## Décision
- **Une seule direction**, décrite dans `docs/produit/direction-artistique.md`, qui fait référence.
- **Fonds neutres sans teinte** (clair `#fafafa`, sombre `#131313`), **un seul accent** brique (`#a63d1e` clair, `#ec9a78` sombre), une palette de huit teintes pour les participants.
- **Typographie** : DM Sans medium en titres, Figtree en texte, base 15 px, rapport 1,333, transcript en 17 px. Polices embarquées (P1).
- **Forme** : angles nets (4, 8, 10 px), filets plutôt que boîtes, aucun effet de matière (grain, verre, halo, dégradé de fond).
- **Transcript façon texte édité** : horodatage en marge, nom en petites capitales colorées, titre de chapitre entre deux filets, sans avatar.
- **Relecture en deux colonnes** : transcription à gauche ; à droite les chiffres clés puis les onglets « Vue d'ensemble » et « Résumé » ; lecteur en pied de page. Chaque point du résumé renvoie aux répliques par une citation cliquable.
- **Vocabulaire générique** dans l'interface : participants, chapitres, décisions, actions, questions ouvertes, notes.
- L'application porte **un seul thème**, sans sélecteur de finition ni d'organisation.

## Conséquences
- Le thème et l'écran de l'atelier servent de référence visuelle. Ils se relisent, ils ne s'importent pas : l'application écrit son propre thème.
- Le modèle d'affichage (chapitres, décisions, actions, questions, citations) suppose que l'application produise ces éléments. Les phases, le titre et les résumés sont déjà de son ressort (`prompting/`). Décisions, actions et questions avec leurs renvois sont à spécifier avant de les construire.
- Le vocabulaire générique prépare un usage hors impro, mais ne l'acte pas : la portée du produit reste celle de la spec (question ouverte Q9).
- À surveiller : la maturité d'Astryx, et la virtualisation du transcript sur deux heures.

## Alternatives écartées
- Directions Projecteur et Atelier, police Bricolage Grotesque : écartées par l'utilisateur.
- Finitions Velours, Lumière, Gélatines, Rideau, Affiche : trop d'effets, ou trop connotées « IA ».
- Organisations Annotations en marge, Double page, Lecture focus, Par chapitres : non retenues. Le repli par chapitre est gardé pour les longs enregistrements.
- Programme, Table de montage, Carnet, Surtitres : trop propres au théâtre, ou pas centrées sur le transcript.
