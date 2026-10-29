# 0065 — Un assistant lit Coulisses par un pont MCP en lecture seule, livré dans l'app

Statut : Proposée (2026-10-27, après exploration avec l'utilisateur, qui a choisi l'onglet « Connecteur », les deux options par espace et le masquage des noms au mieux ; précise 0001, 0034, 0040 et 0043)

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
  - **Transmettre les noms** : sans cette option, chaque nom connu de l'espace devient « Personne A », « Personne B »… Les noms connus sont ceux des présents, des voix nommées, des personnes de l'espace et des noms propres de son glossaire. La même personne garde la même lettre dans toute la séance. Le masquage s'applique **partout** : transcript, notes, titre, titres de chapitres, résumés et extraits de la recherche. Une recherche sur un nom masqué ne trouve rien. Ce masquage est fait **au mieux** : un surnom, un diminutif ou un nom mal transcrit passe. L'option le dit.
  Les deux options sont fermées par défaut. Elles demandent une migration du schéma.
- **Le service applique ces règles à la source**, dans des routes réservées au connecteur (`/api/connecteur/…`). Ce que voit la page de Coulisses ne change pas. Le pont ne lit que ces routes et ne filtre rien lui-même. Un connecteur coupé refuse tout.
- **Un journal des accès** : chaque lecture du connecteur est notée (date, outil, séance, avec ou sans les noms) et se consulte dans l'onglet « Connecteur ». Où le garder se décide avec la migration.
- **L'onglet « Connecteur » dit aussi** :
  - ce qui est lu part chez le fournisseur de l'assistant et y reste, même si la séance est supprimée dans Coulisses ;
  - ce sont aussi les voix des autres participants : c'est à l'utilisateur de juger s'il peut les transmettre ;
  - un transcript peut contenir des consignes adressées à l'assistant ;
  - un assistant peut ouvrir Coulisses en arrière-plan.
- **App fermée : le pont réveille l'app du Dock** en arrière-plan (`open -g`), par l'identifiant de sa propre app : Coulisses ou Coulisses (dév), jamais l'autre. Il attend que le service réponde (une minute au plus), puis répond. Une app réveillée ainsi n'ouvre aucune fenêtre, pas même celle des gestes demandés au lancement (ADR 0049). Elle fait pour le reste ce que fait tout lancement : reprise des tâches coupées, et recherche de mises à jour si l'utilisateur l'a acceptée. Le pont ne lance jamais un service à lui : un seul service par dossier de données (`lock.py`), et c'est l'app du Dock qui le possède (ADR 0034, 0040). L'app reste ouverte ensuite et se voit dans le Dock.
- **Pendant une mise à jour par Sparkle**, le pont s'arrête proprement et le client le relance.
- **Aucune perte silencieuse** : un transcript long se lit par morceaux (par chapitre ou par tranche), et chaque réponse dit s'il reste une suite. Une app qui ne démarre pas, un connecteur coupé, un espace fermé ou une séance introuvable donnent un message en français.
- **Provenance** : un transcript ou un résumé lu porte sa provenance (version du moteur, modèle de rédaction, date).
- **Un lanceur fixe, `~/Coulisses/Connecteur/coulisses-mcp`**, est le seul chemin noté dans la configuration d'un assistant. L'app l'écrit à son lancement. Il retrouve l'app par son identifiant, où qu'elle soit, puis lance le pont qu'elle contient. Déplacer l'app ne casse donc rien. Si l'app est introuvable, il le dit en français.
- **L'accord pour chaque appel** est demandé par le client MCP. Coulisses n'écrit jamais lui-même dans la configuration d'un autre outil. Les Réglages donnent, toutes deux vers le lanceur fixe, la ligne `claude mcp add` à copier pour Claude Code et une extension `.mcpb` à ouvrir pour Claude Desktop.
- **P1 précisé** : le service et le pont n'ouvrent rien au réseau. Si des données sortent, c'est par le client que l'utilisateur a choisi d'y brancher, après qu'il a ouvert l'accès en connaissance de cause.

## Conséquences
- Un appel avec l'app fermée prend le temps de son démarrage. Si le connecteur est coupé, l'app aura été réveillée pour rien : c'est accepté plutôt que de recopier le réglage hors de la base.
- **Le connecteur coupé est une barrière pour l'assistant, pas contre un logiciel malveillant** : tout programme local peut déjà lire l'API en GET (ADR 0043). Le connecteur n'élargit pas ce risque, mais il ne le ferme pas. On ne promet rien de plus.
- Le masquage des noms ne garantit pas l'anonymat ; il évite la plupart des noms connus.
- Le lanceur fixe vit sous `~/Coulisses/`, hors de `Données/`. Coulisses (dév) a le sien, qui ne retrouve que l'app de dév.
- Un changement du schéma (deux options par espace, et peut-être le journal) : validation requise avant de construire.
- Il faut une nouvelle dépendance : le SDK `mcp` Python, en pur Python.
- La spec gagne un sixième onglet de Réglages, « Connecteur », et deux options dans les paramètres d'un espace.
- Coût estimé de 5 à 6 jours :
  - Service : la migration, les routes du connecteur avec le filtrage par espace et le masquage des noms (recherche comprise), le journal, le pont et son réveil de l'app sans fenêtre, ses tests, un transcript paginé (2 à 3 j) ;
  - Interface : l'onglet « Connecteur » avec ses avertissements et son journal, les deux options d'un espace (1 j) ;
  - Distribution : le pont dans le `.app`, le lanceur fixe, le `.mcpb`, `essai-paquet.py` (le pont démarre, liste ses outils et refuse quand l'accès est coupé), la doc pour les amis (1 j) ;
  - Rédaction n'est pas concernée.
- Un transcript est du texte non sûr pour l'assistant (injection de consignes). La lecture seule borne le risque pour Coulisses, pas pour les autres outils de l'assistant.
- Pour essayer l'usage avant de construire, sans rien développer : un serveur MCP « fichiers » standard peut lire le dossier d'export Markdown. Il n'y a alors ni recherche ni masquage, et on n'y met que ce qu'on exporte.

## Alternatives écartées
- **MCP exposé sur un port local (`http://127.0.0.1:8765/mcp`, transport « Streamable HTTP »)**, dans le service :
  - Claude Desktop ne le voit pas sans `mcp-remote`, un pont Node à installer chez chaque ami. Ses connecteurs par adresse passent par les serveurs d'Anthropic, qui n'atteignent pas 127.0.0.1 ;
  - app fermée, personne n'écoute : pas de réveil possible ;
  - le MCP en HTTP passe par des POST, ouverts à toute page web et à tout programme local. C'est une nouvelle porte à défendre dans 0043, sans doute avec un jeton ;
  - le service prendrait un rôle qui n'est pas le sien.
  À reconsidérer, en plus du stdio, si un client utile ne parle que HTTP.
- **Le chemin du pont dans `/Applications/Coulisses.app` noté tel quel dans la configuration** : il casse dès que l'app est déplacée ou lancée d'ailleurs.
- **Lecteur autonome de `~/Coulisses/Données/`** : il ferait des écritures concurrentes à celles du service, devrait suivre les migrations et referait la logique des corrections, avec un risque pour la base réelle.
- **Un service lancé par le pont, sans l'app du Dock** : un second propriétaire du service, à arrêter et à mettre à jour hors de Sparkle.
- **Sans les noms, ne transmettre que le transcript masqué (ni titres ni résumés)** : plus sûr, mais l'assistant perd l'essentiel. L'utilisateur préfère le masquage au mieux, partout.
- **Masquer seulement les présents et les voix** : les résumés (« Retours de jeu » est rédigé comédien par comédien), les titres et la recherche laisseraient passer presque tous les noms.
- **Piloter l'app (enregistrer, importer, rédiger, corriger)** : l'utilisateur ne le veut pas.
