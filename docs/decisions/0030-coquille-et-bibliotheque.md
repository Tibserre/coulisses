# 0030 — Une coquille d'application : colonne des espaces et des séances, recherche, export vers un dossier

Statut : Acceptée (2026-10-07, choix de l'utilisateur). Tranche la question Q7.

## Contexte
La page d'accueil était un formulaire « Nouvelle séance » suivi d'une liste plate ; ouvrir une séance faisait quitter la bibliothèque, et les espaces vivaient sur une page à part. L'utilisateur veut l'organisation d'écran d'OpenWhispr : passer d'une séance à l'autre d'un clic, avoir les espaces sous la main, en ajouter facilement, et trouver leurs paramètres dans un menu « … ». La spec demande aussi les projets, la recherche plein texte et l'état de chaque séance (§7.11). La question Q7 portait sur le rangement des comptes rendus dans Google Drive.

## Décision
- **Une coquille** : une barre en haut (la colonne à afficher ou masquer, ⌘\ ; la recherche, ⌘K ; « Nouvelle séance », ⌘N), une **colonne latérale** toujours là, et le volet principal où s'ouvre ce qu'on choisit (une séance, les paramètres d'un espace, les actions, les réglages, l'enregistrement). Sans séance ouverte, le volet montre les dernières séances et ce qui demande l'attention.
- **La colonne** : les espaces, chacun avec ses projets (dossiers) puis ses séances sans projet, la plus récente d'abord. Sur un espace, « + » ouvre une nouvelle séance à cet endroit et « … » un menu : nouveau projet, paramètres de l'espace (membres, invités, glossaire, résumé proposé), archiver. Un point signale une séance en enregistrement, en traitement ou en échec. On range une séance en la glissant sur un projet, ou depuis le fil « espace · projet » au-dessus de son titre. Le repli de chaque branche est retenu par le navigateur. La page « Espaces » disparaît.
- **« Nouvelle séance »** devient un dialogue : espace, projet, présents, puis enregistrer avec le micro du Mac ou importer un fichier.
- **Projets** (migration 0008) : une séance appartient à un projet de son espace, ou à aucun ; un projet s'archive, jamais ne s'efface, et ses séances y restent.
- **Recherche** : un index plein texte SQLite (FTS5, accents et casse ignorés) des transcriptions corrigées, des notes, des résumés et des titres. C'est un cache : une séance est réindexée quand ce dont son texte est fait a changé (version affichée, corrections, notes, résumés, titre), vérifié à chaque recherche. Chaque mot tapé est cherché comme début de mot ; la syntaxe FTS5 n'est jamais transmise telle quelle. Un résultat ouvre la séance au passage (temps mesuré), ou sur l'onglet Résumé.
- **Export vers un dossier (Q7)** : un dossier choisi une fois dans les Réglages, par la fenêtre du Finder (souvent un dossier synchronisé par Google Drive) ; « Exporter vers le dossier », dans le menu « … » d'une séance, y écrit le compte rendu en Markdown. Coulisses n'écrit qu'un fichier sur le disque : il n'envoie rien (P1). Un fichier du même nom n'est remplacé qu'après confirmation (P8). L'export ne se fait jamais tout seul.

## Conséquences
- La relecture tient en trois colonnes sur un écran de 1440 px (la colonne, la transcription, la vue d'ensemble) ; la colonne se masque pour relire au large.
- Le premier appel à la recherche après beaucoup de changements réindexe les séances concernées : quelques secondes au plus. Supprimer l'index ne perd rien.
- Supprimer une séance efface aussi ses lignes de l'index (ADR 0029).

## Alternatives écartées
- Une page « bibliothèque » en colonne latérale ou en sections par projet, qu'on quitte pour ouvrir une séance : l'utilisateur veut passer d'une séance à l'autre sans changer d'écran.
- Indexer à chaque écriture (correction, note, résumé) : plus de points d'accroche, pour un gain que l'utilisateur ne verrait pas.
- Exporter tout seul à chaque résumé : un dossier partagé recevrait des comptes rendus que l'utilisateur n'a pas relus.
