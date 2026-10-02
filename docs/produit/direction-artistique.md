# Direction artistique de l'interface

Statut : proposée (2026-09-28). Brief de l'utilisateur : « chaleureux, coloré, aéré, animé ; un outil un peu rigolo et sympa, sans être beauf ». Explorée dans l'atelier (`atelier/web/src/theme/`, ADR 0015 : référence, pas le produit) et écran de référence `#/maquette`.

## Direction retenue et finitions

Le 2026-09-29, l'utilisateur a retenu **Loge** (accent chaud, Figtree en texte) avec **DM Sans en titres**. Projecteur et Atelier ont été retirés du dépôt avec leurs polices.

Le même jour, l'utilisateur a rejeté les fonds crème ou jaunâtres et l'effet papier : « très signature IA », « de mauvais goût ». Toutes les finitions reposent désormais sur des neutres sans teinte, sans grain. **Texte de scène** est la finition qui rend le mieux ; c'est la finition par défaut.

Pour monter en gamme, Loge se décline en finitions commutables en direct (sélecteur « Finition » dans la barre latérale, ou lien `#/maquette?finition=script&mode=dark`). Elles gardent la même direction et changent la retenue, la matière et la mise en page de la relecture :

| Finition | Idée | Ce qui change |
|---|---|---|
| **Loge** | La proposition retenue, telle quelle | Pastilles pleines, frise en blocs colorés, titres gras |
| **Velours** | Plus de retenue | Terre cuite `#b3441f`, titres DM Sans medium serrés, échelle 1,333, pastilles en anneau, frise fine, filets, ombres amples, tempo plus lent |
| **Texte de scène** | Éditorial, le transcript se lit comme une pièce | Horodatage en marge, noms en petites capitales espacées, didascalies en italique entre parenthèses, titre d'acte entre deux filets à chaque phase, angles nets, brique `#a63d1e` |
| **Lumière** | Profondeur | Halo de projecteur chaud derrière la page, verre dépoli sur en-tête, pied et panneaux, ombres amples, tour courant éclairé |

Les accents de chaque finition passent 4,5:1 sur les boutons dans les deux modes. Les effets d'ambiance (halo, verre) sont peints sur des calques fixes et non interactifs, et le verre se replie sur un fond opaque quand l'utilisateur réduit la transparence. Une fois la finition choisie, les autres sont retirées et un ADR consigne la direction complète.

## Organisations de l'écran de relecture

Le 2026-09-29, l'utilisateur a précisé la cible : l'outil doit servir à transcrire et analyser **n'importe quel type de réunion**, pas seulement des répétitions. L'écran de relecture montre toute la transcription d'un côté, et à côté une vue d'ensemble et un résumé. Il doit être attrayant sans « sentir l'IA » (pas d'icône d'étincelles, pas de dégradé gratuit, pas de ton de chatbot).

La maquette repose donc sur un modèle générique (participants avec rôle, chapitres typés, décisions, actions avec responsable et échéance, questions ouvertes, notes, résumé avec renvois au transcript). Elle propose deux exemples commutables, « Réunion d'équipe » et « Répétition d'impro », pour vérifier que chaque organisation tient avec les deux. Toutes les variantes gardent le texte façon Texte de scène : horodatage en marge, noms en petites capitales, titres de chapitre entre filets.

| Organisation | Idée |
|---|---|
| **Deux colonnes** | Transcript à gauche ; à droite les chiffres clés puis deux onglets, « Vue d'ensemble » (participants, décisions, actions, questions) et « Résumé ». Survoler une citation surligne la réplique. |
| **Annotations en marge** | Sommaire des chapitres à gauche, transcript au centre ouvert par « L'essentiel » comme un chapeau d'article, et les décisions, actions, questions et notes posées dans la marge à la hauteur de la réplique d'où elles viennent. |
| **Double page** | Un livre ouvert : transcription à gauche, compte rendu écrit sur la page d'en face (résumé, décisions, actions, questions, message d'équipe prêt à copier). |
| **Lecture focus** | Une seule colonne de texte. Une barre fine résume la réunion (participants, répartition de la parole, compteurs) ; chaque compteur ouvre un tiroir. Lecteur flottant. |
| **Par chapitres** | Un bloc par chapitre avec sa durée, qui a parlé et ce qui en est sorti ; le texte est replié sauf pour le chapitre en cours. Pensé pour les longs enregistrements. |

Dans toutes les variantes, une citation s'allume quand la réplique qu'elle cite est en cours de lecture. Le transcript ne défile tout seul que pendant la lecture ou après un clic de navigation, jamais à l'ouverture.

Organisations retirées le même jour : Programme (trop propre au théâtre), Table de montage, Carnet et Surtitres. Elles restent dans l'historique git.

## Intention

Coulisses est l'endroit où l'on revient sur une séance d'impro, souvent le soir, pour la relire tranquillement. L'interface doit avoir la chaleur d'une loge après le spectacle : lumière chaude, couleurs franches mais posées, de l'air entre les choses, et de petits mouvements qui rendent la relecture vivante sans jamais la ralentir.

Quatre mots, dans cet ordre de priorité quand ils se contredisent :

1. **Aéré** : la relecture d'une séance de deux heures ne doit jamais fatiguer. L'espace prime sur la densité.
2. **Chaleureux** : par l'accent (corail ou brique) et les couleurs des locuteurs, jamais par le fond. Les neutres restent sans teinte : ni crème, ni papier, ni gris bleuté.
3. **Coloré** : la couleur porte du sens. Elle identifie les locuteurs et les phases. Elle ne décore pas.
4. **Animé** : chaque animation dit quelque chose (un état change, un élément arrive, le son avance). Rien ne bouge en boucle pour faire joli.

Le ton « rigolo, sympa » vient du dessin des titres, des illustrations d'états vides et des micro-réactions (un bouton qui se soulève, un mot qui s'allume), pas d'emojis, de confettis ou de couleurs criardes.

## Couleur

- **Neutres sans teinte** (`neutralStyle: 'neutral'`). Clair : fond `#fafafa`, surfaces blanches, zones atténuées `#f2f2f2`. Sombre : anthracite `#131313`, surfaces `#1b1b1b`. Jamais de noir pur, jamais de fond crème, beige, jaunâtre ou brun, jamais de grain.
- **Accent corail** (`oklch(0.64 0.18 35)` clair, `oklch(0.77 0.14 40)` sombre). Un seul accent, réservé aux actions et à la sélection. Pas de violet, pas de dégradés.
- **Locuteurs** : palette catégorielle de 8 teintes à luminosité et chroma constants, définie dans le thème (`--coulisses-speaker-N-ink` pour le nom et le trait, `--coulisses-speaker-N-tint` pour le fond). Les teintes évitent la zone du corail pour que l'accent reste reconnaissable. Au-delà de 8 locuteurs, la palette boucle.
- **Phases** : la scène prend une teinte chaude, la discussion une teinte neutre, l'échauffement et le reste des teintes plus effacées. Les phases se lisent sur la frise et en marge du transcript.
- **États** : succès, avertissement et erreur gardent les tokens Astryx. Une erreur se voit toujours (principe 8).

## Typographie

- **Titres** : DM Sans (variable, OFL, embarquée), graisse et approche selon la finition.
- **Texte et interface** : Figtree (variable, OFL, embarquée). Lisible longtemps, chaleureuse.
- **Horodatages et durées** : Figtree en chiffres tabulaires (`font-variant-numeric: tabular-nums`), pas de monospace pour ne pas introduire un registre technique.
- Échelle : base 15 px, ratio 1,25. Transcript en 17 px, interligne 1,6.
- Aucune police ni icône chargée depuis le réseau (principe 1). Les fichiers sont dans le bundle Vite.

## Forme et espace

- Rayons doux et cohérents : éléments 12 px, conteneurs 16 px, boutons principaux en pilule. Règle unique : ce qui se presse est en pilule, ce qui contient est arrondi à 16 px.
- Ombres teintées dans la couleur des neutres, jamais grises pures. En mode sombre, un liseré clair remplace l'ombre.
- Espacement généreux : marge de page 6 (Astryx), gap 4 entre tours de parole, largeur de lecture bornée à 72 caractères environ.
- Pas de cartes pour les listes. Les listes denses sont des rangées (`Item`, `Table`), la carte est réservée aux widgets isolés.

## Mouvement

- Tokens Astryx : rapide 150 ms, moyen 350 ms, lent 800 ms, courbe standard (sortie rapide, atterrissage doux).
- Bibliothèque UI : `motion` (`motion/react`) pour les transitions de mise en page et les éléments partagés (le surlignage du mot courant glisse d'un mot à l'autre, la tête de lecture avance sur la frise). CSS seule pour les survols et les états.
- `prefers-reduced-motion` respecté partout : les animations continues s'arrêtent, les transitions deviennent instantanées.
- **Rive** est réservé aux moments narratifs : états vides (rideau, projecteur), attente longue (traitement de nuit), fin de traitement. Les fichiers `.riv` sont embarqués. À introduire quand un premier écran en a besoin, pas avant.
- Ce qui bouge et pourquoi :
  - le mot courant s'allume et le surlignage glisse : suivre l'audio ;
  - un tour qui devient courant se soulève légèrement : savoir où l'on est ;
  - un panneau ou une boîte de dialogue s'ouvre en glissant : voir d'où vient le nouveau contenu ;
  - un bouton se soulève au survol et s'enfonce au clic : retour tactile.

## Iconographie et illustration

- Icônes Lucide, celles du registre du thème neutre d'Astryx. Une seule famille, épaisseur uniforme.
- Illustrations d'états vides et de moments : dessin au trait chaud, deux couleurs (encre + corail), animées en Rive quand elles existent. Pas d'illustration isométrique, pas de personnages « corporate ».
- Pas d'emojis dans l'interface. Un seul emoji est toléré dans le résumé court destiné au groupe WhatsApp (spec 7.9), et c'est du contenu, pas de l'interface.

## Règles propres à la relecture

- Un tour de parole : avatar aux initiales dans la couleur du locuteur, nom dans la même couleur, horodatage en chiffres tabulaires, texte en 17 px.
- Le tour courant porte un liseré à gauche dans la couleur du locuteur et une surface à peine relevée.
- Mot courant : fond corail atténué, texte primaire. Le surlignage glisse (jamais de clignotement).
- Mot peu sûr : soulignement pointillé chaud. Au survol, la confiance s'affiche.
- Mot sans temps (ajouté à la main, ADR 0011) : léger marqueur en exposant, pour que le manque de temps soit visible sans gêner la lecture.
- Locuteur non nommé : avatar gris chaud et nom « Locuteur N » en italique, avec l'action « Nommer » toujours visible. Renommer ne demande jamais d'ouvrir un autre écran.
- Marqueurs et notes s'intercalent dans le fil, en retrait, avec leur propre icône. Ils ne sont pas des tours de parole.

## Ce qu'on s'interdit

- Fonds crème, beige, jaunâtres ou « papier », grain et textures de papier.
- Violet ou bleu électrique comme accent, dégradés « IA », halos lumineux.
- Inter, Roboto ou la police système comme choix par défaut.
- Cartes empilées pour tout, ombres grises, pastilles colorées décoratives.
- Animations en boucle sans état à signifier, confettis, rebonds exagérés.
- Emojis, points médians en série, majuscules espacées comme étiquettes de section.
- Texte anglais visible, ressource distante, police non embarquée.

## Mise en œuvre

- Thème : `atelier/web/src/theme/loge.ts` (fabrique `defineTheme` par finition, sans `extends`, icônes du thème neutre), finitions dans `finishes.ts`, règles communes dans `shared.ts`, cache et contexte dans `index.ts`. Ambiances dans `atelier/web/src/index.css`. En développement le thème s'injecte à l'exécution ; avant de servir `web/dist`, lancer `npx astryx theme build` sur le thème retenu et importer la CSS produite.
- Polices : importées dans `atelier/web/src/index.css` depuis les paquets Fontsource.
- Écran de référence : `atelier/web/src/pages/MaquettePage.tsx`, route `#/maquette`, données synthétiques. C'est là qu'on juge la DA. Il sera remplacé par la vraie relecture (phase 2) et sert de gabarit visuel jusque-là.
- Validation : capture en mode clair et sombre à chaque changement de thème, relue avant de continuer.
