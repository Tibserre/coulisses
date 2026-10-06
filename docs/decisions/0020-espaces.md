# 0020 — Des espaces plutôt qu'une troupe

Statut : Acceptée (2026-10-05). Tranche la question ouverte Q9. Les résumés lancés automatiquement sont remplacés par un résumé proposé, lancé à la demande (ADR 0025).

## Contexte
La spec V1 ne parle que d'une troupe d'impro. Le 2026-10-05, l'utilisateur précise qu'il utilisera aussi l'outil au travail, avec des gens variés. Les participants ne sont donc pas les mêmes d'une réunion à l'autre : ils dépendent de l'équipe concernée. L'interface est déjà générique (ADR 0017). Le schéma (ADR 0018) n'a pour l'instant qu'une table `troupe` sans contenu propre.

## Décision
- **Un espace** (`space`) remplace la troupe. Il regroupe des membres, des invités, un glossaire, des projets et des réglages. Chaque enregistrement appartient à un seul espace. Exemples : une troupe d'impro, une équipe, un client.
- **Une personne appartient à un seul espace.** La même personne dans deux espaces y a deux fiches. Les espaces restent étanches.
- **Un rôle libre** pour chaque membre (« coach », « comédienne », « cheffe de projet »), au lieu d'une liste fermée.
- **Des projets** (`project`) au lieu des spectacles. Ils regroupent les enregistrements d'un espace. Un enregistrement peut n'appartenir à aucun projet.
- **Pas de type d'espace.** Ce qui varie d'un espace à l'autre est un réglage de l'espace : les résumés lancés automatiquement après le traitement, et le glossaire. À la création, on part d'un **modèle de départ** (« Troupe d'impro », « Réunions de travail », « Vide »). Le modèle remplit ces réglages une fois, puis on peut tout modifier.
- **La reconnaissance des voix d'une réunion à l'autre est un réglage de l'espace**, désactivé par défaut. Désactivée, l'application ne crée aucune signature vocale de personne. Les empreintes que le moteur écrit dans ses exécutions restent où elles sont (P5) et ne servent à rien. Nommer reste manuel, réunion par réunion.

## Conséquences
- La spec, le glossaire (troupe → espace, spectacle → projet) et le schéma changent. La table `troupe` devient `space`, par une migration (étape 2).
- Les actions fournies gardent leurs prompts. Le Résumé Impro devient l'action par défaut du modèle « Troupe d'impro ». Une action « Compte rendu de réunion » est à écrire pour le modèle « Réunions de travail » (`/action-resume`).
- Le découpage en phases (étape 4) doit valoir pour tout type de réunion : chapitres dans l'interface, scènes et discussions pour l'impro. La méthode reste à mesurer (M7).
- Les profils vocaux (« plus tard ») ne fonctionneront que dans les espaces qui les activent.

## Alternatives écartées
- Un type d'espace (impro / travail) qui fixe les actions et le vocabulaire : trop rigide. Les besoins se mélangent, par exemple un atelier d'impro en entreprise.
- Des personnes partagées entre espaces : pratique pour soi-même, mais les espaces ne seraient plus étanches, et la fusion des fiches serait à gérer.
- Garder une seule troupe et ajouter « invités » partout : la liste des présents deviendrait illisible.
