# Résumés par objectif : définition produit

Statut : **proposition, à valider par l'utilisateur** (2026-10-26 ; les résumés vont à l'espace, pas au projet : choix de l'utilisateur le même jour). Rédigée par la conversation Interface à partir des choix de l'utilisateur (maquettes Q1 à Q3, retenue : Q2 avec la demande libre). Une fois validée, elle entre dans la spec (§7.9) et fait l'objet d'un ADR.

## Pourquoi

Aujourd'hui, pour tirer quelque chose d'une séance, on choisit un prompt dans une liste (« Résumé Impro », « Retours de jeu par comédien »…) sans savoir ce qu'il produira, et rien ne couvre une envie ponctuelle. Les résumés fournis sont aussi pensés pour l'impro, alors que Coulisses sert à tout type de séance : répétitions, réunions, ateliers, entretiens…

**Le but : dire ce qu'on veut faire de la séance, pas choisir un prompt.** Et pouvoir demander autre chose en une phrase.

**Réussi si :**
- on rédige ce qu'il faut du premier coup, sans ouvrir la liste des prompts ;
- une demande inhabituelle se fait en une phrase ;
- créer ou adapter un résumé ne demande pas d'écrire un prompt de zéro.

## Les notions

- **Résumé** : un titre, un objectif, un contenu.
  - **Titre** : son nom (« Retours par personne »).
  - **Objectif** : ce qu'on veut en faire, dit du point de vue de l'utilisateur (« Faire progresser chacun »). C'est ce qui s'affiche dans la vue Résumé d'une séance.
  - **Contenu** : ce qu'il doit produire, construit à partir de choix simples (voir « Construire un résumé ») et non tapé en vrac. Le prompt envoyé au modèle en découle, et reste visible et modifiable.
- **La bibliothèque** : tous les résumés, en un seul endroit, communs à toute l'application. Aucun n'est « pour l'impro » ou « pour les réunions ».
- **Les résumés d'un espace** : un espace (une troupe, une équipe : le groupe, avec ses membres, son glossaire) a sa sélection de résumés, ceux qu'on propose pour ses séances. À la création d'un espace, **4 résumés de base** y sont associés ; on en ajoute, on en retire, on les réordonne, et on les modifie, depuis les paramètres de l'espace. Toutes les séances ont un espace : aucune n'est sans résumés proposés. Les projets restent de simples dossiers dans l'espace, sans réglage de résumés.
- **Les 4 résumés de base** (choisis par l'utilisateur le 2026-10-26), pour tout type de séance, sans doublon :
  1. **« Le raconter à quelqu'un qui n'était pas là »** : un compte rendu de toute la séance, pour comprendre ce qui s'est dit sans l'avoir vécu ;
  2. **« Savoir qui fait quoi »** : les actions décidées pendant la séance, avec qui s'en charge et l'échéance quand elle a été dite ;
  3. **« Ce que chacun a apporté »** : par personne, ses idées, ses positions, ses retours (en répétition, les retours de jeu ; en réunion, qui défendait quoi) ;
  4. **« Ce qui reste ouvert »** : les questions sans réponse, les désaccords, les sujets à reprendre.

  Les autres (les idées à garder, un message court à envoyer, les moments forts, les résumés actuels…) restent dans la bibliothèque, à ajouter dans un espace qui en a l'usage.
- **Trois niveaux, pas plus** : la bibliothèque (tous les résumés), les résumés de l'espace, la séance (un objectif de son espace, ou une demande libre).
- **Les habitudes** : dans un espace, les résumés les plus rédigés passent en tête. Rien de deviné : on compte ce qui a été rédigé.
- **La demande libre** : une phrase écrite pour cette séance (« les moments où on a ri », « ce que Camille a proposé »). Elle est rédigée une fois, dans son onglet, et **n'est pas gardée comme résumé**. Le texte rédigé, lui, reste avec sa provenance, comme tout texte rédigé. « Ajouter à mes résumés » la transforme en résumé si on le veut.

## Le parcours

1. **Vue Résumé d'une séance, rien de rédigé.** « Qu'aimeriez-vous en tirer ? », puis les objectifs des résumés de son espace, dans l'ordre des habitudes. Sous chacun, le titre du résumé et ce qu'on obtiendra, en une ligne. En dessous, le champ de la demande libre.
2. **Un clic sur un objectif**, ou une phrase et Entrée, lance la rédaction. Son onglet apparaît tout de suite, et on peut relire la transcription en attendant.
3. **Une fois des résumés rédigés**, la même liste est dans « + Rédiger… ». Les onglets, « Refaire » et « Revenir à la version d'avant » restent ceux de l'ADR 0060. Une demande libre se refait avec la même phrase.
4. **Sur l'onglet d'une demande libre**, « Ajouter à mes résumés » : on lui donne un titre et un objectif, et elle rejoint la bibliothèque, ainsi que les résumés de l'espace si on le veut.

## Construire un résumé

Créer ou modifier un résumé, c'est répondre à des questions, avec le prompt en aperçu :

- **L'objectif** : à quoi il sert, en une phrase.
- **Ce qu'on veut obtenir** : ses parties (« ce qui a marché », « à travailler », « qui fait quoi »…), à ajouter, retirer ou réordonner.
- **Pour qui et sous quelle forme** : pour soi, pour les participants, un message à envoyer, un compte rendu.
- **La longueur et le ton.**
- **L'aperçu du prompt** qui en résulte, modifiable à la main.
- **Un essai sur une séance** avant d'enregistrer.

## Les pages

- **La vue Résumé d'une séance** : les objectifs de son espace, la demande libre, les onglets.
- **Les paramètres d'un espace** : la section « Résumés de cet espace », pour en associer, en retirer, les réordonner, et en modifier un sur place (le même éditeur que la bibliothèque).
- **La page « Résumés »** (la bibliothèque) : tous les résumés, en créer, en modifier, en dupliquer, en archiver, et voir dans quels espaces chacun est utilisé.

## Ce qui ne change pas

- **Tout passe par l'assemblage unique de `prompting/`**, consigne de français comprise (P4), la demande libre incluse.
- **Rien ne se rédige tout seul** (ADR 0025). Le modèle est celui des Réglages (ADR 0060). Tout reste local (P1).
- **Chaque texte rédigé garde son prompt exact et sa provenance** (P5, P7). Un résumé modifié ne change pas ce qui a déjà été rédigé avec lui.
- **Rien d'impossible n'est passé sous silence** (P8) : une phrase vide, un modèle absent, un résumé archivé encore associé à un espace sont dits.

## Qui fait quoi

**Interface (conversation Interface)** :
- la vue Résumé (Q2) : la question, les objectifs dans l'ordre des habitudes, la demande libre, les onglets, « Ajouter à mes résumés » ;
- la section « Résumés de cet espace » dans les paramètres d'un espace ;
- la page « Résumés » (la bibliothèque) et l'éditeur qui aide à construire un résumé : objectif, parties, destinataire et forme, longueur et ton, aperçu, essai ;
- les durées affichées, quand le service les donne.

**Système (conversation Rédaction et modèles)** :
- le modèle de données d'un résumé (titre, objectif, contenu structuré) et la construction du prompt à partir de ce contenu, dans l'assemblage unique ;
- la reprise des 6 résumés fournis dans cette forme, sans perdre les versions modifiées par l'utilisateur ;
- l'association des résumés aux espaces (elle étend le « résumé proposé en premier » d'aujourd'hui à une sélection), les 4 de base, et la fin du modèle de départ « troupe » ou « réunion » ;
- les habitudes (le décompte des résumés rédigés par espace) ;
- la demande libre (rédaction, provenance, non gardée) et « Ajouter à mes résumés » ;
- l'essai d'un résumé sur une séance ;
- la durée mesurée d'un résumé avec un modèle ;
- le contrat d'API que l'interface lira, l'ADR, et la migration du schéma (à faire valider par l'utilisateur).

## Questions ouvertes

1. **L'essai d'un résumé** : son texte est-il gardé comme une version de la séance essayée, ou mis de côté (P5 : rien de rédigé n'est jamais purgé) ?
2. **Un résumé modifié depuis un espace** : il change pour tous les espaces qui l'utilisent, ou l'espace en garde une copie à lui ?
