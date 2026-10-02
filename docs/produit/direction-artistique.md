# Direction artistique de l'interface

Statut : retenue (2026-10-02, ADR 0017). Ce document décrit une seule direction. Les pistes écartées sont listées à la fin, pour ne pas les reproposer.

## En une phrase

Une interface sobre et éditoriale : des fonds neutres, une typographie soignée, et la couleur réservée à ce qui porte du sens. L'écran de relecture montre toute la transcription à gauche, la vue d'ensemble et le résumé à droite.

## Principes

Dans cet ordre de priorité quand ils se contredisent :

1. **Aéré.** Relire deux heures d'enregistrement ne doit pas fatiguer. L'espace prime sur la densité.
2. **Sobre.** Fonds neutres, filets fins, peu d'effets. L'interface s'efface derrière le texte.
3. **La couleur porte du sens.** Elle identifie les participants et les chapitres, et signale l'action. Elle ne décore pas.
4. **Le mouvement dit quelque chose.** Un état change, un élément arrive, le son avance. Rien ne bouge en boucle.
5. **Générique.** Le vocabulaire de l'interface vaut pour toute réunion : participants, chapitres, décisions, actions, questions ouvertes, notes. Les mots de l'impro (scène, retours) viennent du contenu, jamais de l'interface.
6. **Rien qui sente l'IA.** Pas d'icône d'étincelles, pas de dégradé gratuit, pas de ton de chatbot.

## Couleur

Valeurs données en clair puis en sombre. Les deux modes sont conçus ensemble.

| Rôle | Clair | Sombre |
|---|---|---|
| Fond de page | `#fafafa` | `#131313` |
| Surface, carte | `#ffffff` | `#1b1b1b` |
| Zone atténuée | `#f2f2f2` | `#212121` |
| Texte principal | `#1d1d1f` | `#ededed` |
| Texte secondaire | `#6b6b6b` | `#a3a3a3` |
| Bordure, filet | noir à 10 % | blanc à 9 % |
| Accent (brique) | `#a63d1e` | `#ec9a78` |
| Texte sur l'accent | `#ffffff` | `#2a0f06` |
| Mot en cours de lecture | `#f5dfd9` | `#4a241c` |
| Mot peu sûr (soulignement) | `#a8742f` | `#d5a86e` |

- **Neutres sans teinte.** Jamais de crème, de beige, de jaunâtre ni de brun. Jamais de noir pur.
- **Un seul accent**, la brique. Il sert aux actions principales, à la sélection et à la réplique en cours. Il passe 4,5:1 sur les boutons dans les deux modes.
- **Participants** : huit teintes à luminosité constante, hors de la zone de la brique. Chacune a une encre (nom, repères) et un fond pâle (pastille, citation). Encres en clair : framboise `#a33d78`, ciel `#0075ae`, olive `#697100`, prune `#824ba9`, sarcelle `#00817f`, ambre `#995700`, bleuet `#4860be`, menthe `#00803b`. Au-delà de huit, la palette boucle.
- **Participant non nommé** : gris neutre (`#737373`, `#a8a8a8`), jamais une couleur de la palette.
- **Chapitres** : trois poids. Principal en brique atténuée, secondaire en gris moyen, discret en gris clair.
- **États** (succès, avertissement, erreur) : ceux d'Astryx. Une erreur se voit toujours (principe 8 du projet).

## Typographie

- **Titres** : DM Sans, graisse medium, approche serrée (-0,03 em). La hiérarchie vient de la taille, pas du gras.
- **Texte et interface** : Figtree.
- **Échelle** : base 15 px, rapport 1,333. Transcript en 17 px, interligne 1,6. Largeur de lecture d'environ 70 caractères.
- **Chiffres** : tabulaires partout (horodatages, durées, pourcentages). Pas de police à chasse fixe.
- **Noms dans le transcript** : petites capitales espacées (0,1 em), dans l'encre du participant.
- Polices variables, sous licence OFL, embarquées dans l'application. Aucune ressource distante (principe 1).

## Forme, espace, matière

- **Angles nets** : 4 px pour les petits éléments, 8 px pour les contrôles, 10 px pour les conteneurs. Les boutons ne sont pas en pilule.
- **Filets plutôt que boîtes.** On sépare par un filet ou par de l'espace. La carte est réservée à un bloc isolé.
- **Ombres** rares, amples et neutres. En sombre, un liseré clair remplace l'ombre.
- **Aucun effet de matière** : ni grain, ni verre dépoli, ni halo, ni dégradé de fond.
- **Icônes** : Lucide, trait de 1,75. Une seule famille. Pas d'emoji dans l'interface.

## Mouvement

- Durées : 160 ms (survol, retour tactile), 400 ms (entrée, sortie), 850 ms (rare). Courbe `cubic-bezier(0.22, 1, 0.36, 1)` : départ vif, arrivée douce, sans rebond.
- Ce qui bouge, et pourquoi :
  - le surlignage glisse d'un mot au suivant : suivre l'audio ;
  - une citation s'allume quand sa réplique passe : relier le résumé à ce qu'on entend ;
  - un panneau s'ouvre en glissant : voir d'où vient le contenu ;
  - un bouton se soulève au survol et s'enfonce au clic : retour tactile.
- `prefers-reduced-motion` est respecté : les transitions deviennent instantanées.
- Bibliothèque : `motion` pour les éléments partagés et les mises en page ; CSS seule pour les survols.
- Les animations illustrées (Rive) restent possibles pour les états vides et les attentes longues. À introduire quand un écran en a besoin, pas avant.

## L'écran de relecture : deux colonnes

**En-tête.** Le type d'enregistrement, le titre, une ligne de contexte (date, lieu, durée, nombre de participants). À droite, « Exporter » (discret) et « Compte rendu » (principal). Dessous, une frise fine des chapitres : une barre par chapitre, proportionnelle à sa durée, le nom du chapitre en cours au-dessus, une tête de lecture.

**Colonne de gauche : la transcription entière.** Elle se lit comme un texte édité :
- l'horodatage dans la marge, cliquable pour lire à partir de là ;
- le nom en petites capitales dans l'encre du participant, puis la réplique ;
- pas de pastille ni d'avatar dans le texte ;
- la réplique en cours porte un trait brique à gauche ; le mot en cours est surligné ;
- un titre de chapitre, centré entre deux filets, à chaque changement de chapitre ;
- une note prise à la main s'intercale dans une ligne atténuée, en italique, avec son icône ;
- un mot peu sûr est souligné en pointillé, avec sa confiance au survol ;
- un mot ajouté à la main, sans temps mesuré, porte un petit « + » en exposant (ADR 0011 du moteur).

**Colonne de droite : vue d'ensemble et résumé.** Largeur fixe d'environ 420 px.
- En haut, les chiffres clés : durée, participants, décisions, actions, questions.
- Onglet « Vue d'ensemble » : les participants (pastille aux initiales, rôle, part du temps de parole), puis les décisions, les actions (responsable, échéance) et les questions ouvertes.
- Onglet « Résumé » : le compte rendu par sections, puis le message court prêt à copier.
- Chaque point renvoie aux répliques qui le justifient par une **citation** : une petite étiquette à l'heure de la réplique, dans la couleur de la personne. Cliquer y amène la lecture ; survoler surligne la réplique à gauche.

**Pied de page : le lecteur.** Réplique précédente, lecture, réplique suivante, position, vitesse. Espace pour lire ou mettre en pause, flèches pour changer de réplique.

**Comportements.**
- Le transcript ne défile tout seul que pendant la lecture ou après un clic de navigation. Jamais à l'ouverture.
- Un participant non nommé s'appelle « Locuteur N », en italique gris, numéroté dans l'ordre de détection. L'action « Nommer » est toujours visible à côté. Nommer ne demande jamais d'ouvrir un autre écran.
- Les longs enregistrements : le texte d'un chapitre peut se replier, le chapitre en cours restant ouvert. Le transcript est virtualisé (`rules/web.md`).
- Chaque état d'une étape se voit : en file, en cours avec sa progression, réussie, échouée avec une erreur lisible.

## Ce qu'on s'interdit

- Fonds crème, beige, jaunâtres ou « papier ». Grain sur un fond plat.
- Dégradés de fond, dégradés maillés, verre dépoli, halos.
- Violet ou bleu électrique en accent. Plus d'un accent.
- Icône d'étincelles, baguette magique, ou tout code visuel « IA ».
- Inter, Roboto ou la police système comme choix par défaut.
- Boutons en pilule, cartes empilées pour tout, pastilles colorées décoratives.
- Animations en boucle, rebonds, confettis.
- Emojis dans l'interface, points médians en série.
- Texte anglais visible, ressource distante, police non embarquée.

## Pistes écartées

Explorées dans l'atelier du moteur entre le 28 septembre et le 2 octobre 2026, puis abandonnées :

- **Directions** : Projecteur (crème, framboise, très rond) et Atelier (sable, sarcelle).
- **Police de titre** : Bricolage Grotesque, jugée inadaptée.
- **Fonds chauds** : papier, ivoire, grain. Jugés « signature IA ».
- **Finitions** : Loge d'origine (pastilles, pilules, corail), Velours, Lumière (halo, verre), puis les finitions vives Gélatines, Rideau et Affiche.
- **Organisations** : Programme (trop propre au théâtre), Table de montage, Carnet, Surtitres, Annotations en marge, Double page, Lecture focus, Par chapitres. De cette dernière, on garde le repli par chapitre.

## Mise en œuvre

- **Référence visuelle** : l'atelier du moteur (ADR 0015), qui n'est pas le produit. Lancer `cd ~/Coulisses/Moteur/atelier/web && npm run dev`, puis ouvrir `#/maquette?organisation=columns&finition=script`. Deux exemples s'y comparent : une réunion d'équipe et une répétition.
- **Code de référence**, à relire et non à importer : thème dans `atelier/web/src/theme/` (finition `script` de `finishes.ts`, palette dans `shared.ts`), écran dans `atelier/web/src/pages/maquette/` (`ColumnsLayout.tsx`, `parts.tsx`, modèle dans `model.ts`).
- **Dans l'application** : un seul thème Astryx, écrit avec `defineTheme`, sans sélecteur de finition. Construit avec `npx astryx theme build` et importé avec sa CSS. Polices depuis les paquets Fontsource `dm-sans` et `figtree`.
- **Validation** : une capture en clair et une en sombre à chaque changement visuel, relues avant de continuer.
