# 0065 — Un assistant lit Coulisses par un pont MCP en lecture seule, livré dans l'app

Statut : Proposée (2026-10-27, après exploration avec l'utilisateur, qui a choisi l'onglet « Connecteur » et les deux options par espace ; précise 0001, 0034, 0040 et 0043)

## Contexte
L'utilisateur veut qu'un assistant (Claude Desktop, Claude Code ou un client MCP local sur Ollama) puisse **consommer les données de Coulisses, sans piloter l'app** : chercher et lire les séances. Le même outil doit servir chez les amis (ADR 0040).
- **Claude Desktop ne branche un serveur local qu'en stdio** (sa configuration, ou une extension `.mcpb`). Un connecteur déclaré par une adresse passe par les serveurs d'Anthropic et n'atteint pas 127.0.0.1. Claude Code accepte stdio et HTTP local.
- **Lire la base hors du service n'est pas de la lecture** : la recherche rafraîchit l'index (`search.search`), `connect` règle le journal WAL. Les corrections, la version affichée et les reports sont de la logique du service (ADR 0028).
- **L'API locale sert déjà tout en GET** : recherche, séances, espaces, projets, chapitres, notes, résumés, provenance, export Markdown du transcript corrigé. L'ADR 0043 accepte un GET vers 127.0.0.1 sans `Origin`, mais demande un ADR pour toute nouvelle intégration.
- **P1** : le pont n'ouvre rien au réseau, mais un assistant distant envoie à son fournisseur tout ce qu'il lit (transcripts, résumés, noms des présents). P5, P7 et P8 s'appliquent à ce qui est rendu.

## Décision
- **Un pont stdio, `coulisses-mcp`**, dans le paquet `coulisses_app` et inclus dans `Coulisses.app` (son Python embarqué). Il est lancé par l'assistant et ne parle qu'au service de sa propre app, sur 127.0.0.1 : port 8765 pour Coulisses, 8766 pour Coulisses (dév), qui ne lit donc jamais les données réelles.
- **Lecture seule par construction** : le pont n'envoie que des GET. Ses outils sont `chercher`, `lister_seances`, `lire_seance` (métadonnées, présents, chapitres, notes, provenance), `lire_resume` et `lire_transcript`. Il ne donne ni l'audio, ni les prompts, ni les réglages. Il n'enregistre rien, n'importe rien, ne rédige rien et ne corrige rien. Un test vérifie que le pont n'a aucune requête autre que GET.
- **Un onglet « Connecteur » dans Réglages** ouvre ou coupe le connecteur. Il est **coupé par défaut**, et l'onglet dit : « Un assistant distant envoie ce qu'il lit à son fournisseur. »
- **Chaque espace a deux options** dans ses paramètres :
  - **Accessible au connecteur** : un espace fermé n'apparaît dans aucune réponse, pas même dans la recherche ;
  - **Transmettre les noms** : sans cette option, les présents, les voix nommées et les personnes deviennent « Voix 1 », « Voix 2 », de façon stable dans une même séance. Les noms **prononcés** dans le transcript ou **tapés** dans les notes restent tels quels, et l'option le dit.
  Les deux options sont fermées par défaut. Elles demandent une migration du schéma.
- **Le service applique ces règles à la source.** Le pont ne lit que des routes du service qui filtrent déjà les espaces fermés et masquent les noms. Il ne filtre rien lui-même, et un connecteur coupé refuse tout.
- **App fermée : le pont réveille l'app du Dock** en arrière-plan (`open -g`), sans lui donner le premier plan, attend que le service réponde (une minute au plus), puis répond. Il ne lance jamais un service à lui : un seul service par dossier de données (`lock.py`), et c'est l'app du Dock qui le possède (ADR 0034, 0040). L'app reste ouverte ensuite et se voit dans le Dock. L'onglet « Connecteur » le dit : « Un assistant peut ouvrir Coulisses en arrière-plan. »
- **Aucune perte silencieuse** : un transcript long se lit par morceaux (par chapitre ou par tranche), et chaque réponse dit s'il reste une suite. Une app qui ne démarre pas, un connecteur coupé, un espace fermé ou une séance introuvable donnent un message en français.
- **Provenance** : un transcript ou un résumé lu porte sa provenance (version du moteur, modèle de rédaction, date).
- **L'accord pour chaque appel** est demandé par le client MCP. Coulisses n'écrit jamais lui-même dans la configuration d'un autre outil. Les Réglages donnent :
  - la ligne `claude mcp add` à copier, pour Claude Code ;
  - une extension `.mcpb` à ouvrir, pour Claude Desktop.
- **P1 précisé** : le service et le pont n'ouvrent rien au réseau. Si des données sortent, c'est par le client que l'utilisateur a choisi d'y brancher, après qu'il a ouvert l'accès en connaissance de cause.

## Conséquences
- Un appel avec l'app fermée prend le temps de son démarrage. Si le connecteur est coupé, l'app aura été réveillée pour rien : c'est accepté plutôt que de recopier le réglage hors de la base.
- Un changement du schéma (deux options par espace) : validation requise avant de construire.
- Il faut une nouvelle dépendance : le SDK `mcp` Python, en pur Python.
- La spec gagne un sixième onglet de Réglages, « Connecteur », et deux options dans les paramètres d'un espace.
- Coût estimé de 4 à 5 jours :
  - Service : la migration, le filtrage par espace et le masquage des noms, le pont et son réveil de l'app, ses tests, un transcript paginé (2 j) ;
  - Interface : l'onglet « Connecteur » et les deux options d'un espace (1 j) ;
  - Distribution : le pont dans le `.app`, le `.mcpb`, `essai-paquet.py` (le pont démarre, liste ses outils et refuse quand l'accès est coupé), la doc pour les amis (1 j) ;
  - Rédaction n'est pas concernée.
- Un transcript est du texte non sûr pour l'assistant (injection de consignes). La lecture seule borne le risque pour Coulisses, pas pour les autres outils de l'assistant : les Réglages le disent.

## Alternatives écartées
- **MCP dans le service, en HTTP local** : Claude Desktop ne le voit pas sans un pont Node à installer chez les amis. Le MCP en HTTP passe par des POST, donc une nouvelle porte en écriture à défendre dans 0043. Et le service prendrait un rôle qui n'est pas le sien.
- **Lecteur autonome de `~/Coulisses/Données/`** : il ferait des écritures concurrentes à celles du service, devrait suivre les migrations et referait la logique des corrections, avec un risque pour la base réelle.
- **Un service lancé par le pont, sans l'app du Dock** : un second propriétaire du service, à arrêter et à mettre à jour hors de Sparkle.
- **Piloter l'app (enregistrer, importer, rédiger, corriger)** : l'utilisateur ne le veut pas.
