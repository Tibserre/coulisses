# 0034 — Coulisses, une app dans le Dock avec sa propre fenêtre (la PWA est abandonnée)

Statut : Acceptée (2026-10-09, choix de l'utilisateur ; lancement par `uv run`, signature ad hoc, app sans réseau et empaquetage écarté : remplacés par 0040). Remplace la PWA prévue par les ADR 0002 et 0007. Tranche la question Q3 : l'app s'appelle **Coulisses**.

## Contexte
La spec (§7.12) prévoit une icône dans le Dock qui démarre le service et ouvre l'interface, et que rien ne tourne quand l'app n'est pas utilisée. Les ADR 0002 et 0007 prévoyaient une PWA. Mais une PWA est une app du navigateur :
- son icône ne démarre pas le service ;
- fermer l'onglet n'arrête rien ;
- les permissions (micro, son de l'ordinateur) iraient au navigateur, pas à Coulisses.

macOS donne les permissions à l'app « responsable » du service, c'est-à-dire celle qui le lance.

## Décision
- **`Coulisses.app`**, une petite app Swift (AppKit et WebKit, `native/lanceur/`), est compilée sur le Mac par `scripts/installer-lanceur.sh` et installée dans `~/Applications`. On la glisse dans le Dock.
- **Au lancement**, si un service Coulisses répond déjà sur 127.0.0.1:8765, l'app l'utilise. Sinon elle le démarre :
  - par `uv run --offline` dans le dossier du projet, sans rien télécharger (P1) ;
  - avec le PATH du Terminal, enregistré à l'installation ;
  - en écrivant sa sortie dans `~/Library/Logs/Coulisses/service.log`.
  Elle affiche « Coulisses démarre… », puis l'interface dans **sa propre fenêtre**. Si le service ne démarre pas, ou s'arrête, la fenêtre le dit, avec « Réessayer » et « Ouvrir le journal ».
- **Les permissions** (micro, son de l'ordinateur) vont à « Coulisses » : l'app est responsable du service et de ses sous-processus. Elle déclare leurs usages en français.
- **Quitter (⌘Q)** :
  - pendant un enregistrement, l'app demande d'abord (« Arrêter et quitter ») ; l'enregistrement est fermé proprement et gardé ;
  - si le service ne répond pas, elle demande aussi (« Quitter quand même ? ») : un enregistrement est peut-être en cours ;
  - pendant un traitement, elle prévient qu'il reprendra au prochain lancement ;
  - ensuite, elle arrête le service qu'elle a lancé, comme ⌃C (la fermeture propre du service s'applique), puis plus fermement s'il ne s'arrête pas.
  - Un service qu'elle n'a pas lancé (celui du développement) n'est jamais arrêté par elle.
- **Fermer la fenêtre** la masque : l'app reste ouverte dans le Dock jusqu'à ⌘Q, comme les apps du Mac.
- **Dans la fenêtre** :
  - un export se télécharge par la fenêtre « Enregistrer » du Mac ;
  - « Choisir un fichier » ouvre le Finder ;
  - un lien vers l'extérieur s'ouvre dans le navigateur, jamais dans la fenêtre ;
  - menus en français (Édition pour copier-coller et annuler, Recharger, Fenêtre).
- **Les Réglages** ont une section « Coulisses » : la version, et des boutons pour ouvrir dans le Finder le dossier des données et celui des modèles ; le journal du service, en mode développeur (les pages d'erreur de l'app y mènent aussi).
- **Plus de PWA** : ni manifeste ni service worker. L'interface reste une application web servie par le service, et s'ouvre aussi dans un navigateur pendant le développement.

## Conséquences
- L'app est signée pour ce Mac seulement (signature ad hoc). macOS rattache les permissions à cette signature : après une réinstallation, il les redemande une fois.
- `uv`, le dossier du projet et le PATH sont figés à l'installation. Si l'un d'eux change, il faut relancer `scripts/installer-lanceur.sh`.
- Le service écoute toujours sur 127.0.0.1:8765. Un autre programme sur ce port est dit à l'ouverture.
- Le parcours complet réseau coupé se vérifie par `scripts/essai-hors-ligne.sh` : un bac à sable de macOS ne laisse sortir du service que 127.0.0.1. L'app elle-même ne parle qu'au service, sur 127.0.0.1 ; l'avertissement « site frauduleux » de WebKit, qui téléchargerait des listes, est coupé.
- Si l'app est forcée à quitter ou plante, le service peut lui survivre. Au lancement suivant, l'app le reconnaît (même données, plus de parent) et le reprend à sa charge : ⌘Q l'arrêtera. Un service lancé dans un Terminal n'est jamais arrêté par elle.
- La page d'attente et d'erreur de l'app est affichée avant le service : sans accès aux polices embarquées, elle utilise la police du système (seule exception à la typographie de la direction artistique).
- Le code de l'app n'a pas de tests automatisés ; il se vérifie à la main à chaque changement : lancement, ⌘Q pendant un enregistrement puis relance, export, import d'un fichier.

## Alternatives écartées
- PWA du navigateur : voir le contexte.
- Ouvrir l'interface dans le navigateur par défaut : deux apps pour une, et des permissions données au mauvais endroit.
- Un empaquetage complet (Python embarqué dans l'app) : la distribution est hors périmètre V1, l'app sert un seul Mac.
