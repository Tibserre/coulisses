# 0065 — Un assistant lit Coulisses par un pont MCP en lecture seule, livré dans l'app

Statut : Proposée (2026-10-27, après exploration avec l'utilisateur ; précise 0001, 0040 et 0043)

## Contexte
L'utilisateur veut qu'un assistant (Claude Desktop, Claude Code ou un client MCP local sur Ollama) puisse **consommer les données de Coulisses, sans piloter l'app** : chercher et lire les séances. Le même outil doit servir chez les amis (ADR 0040).
- **Claude Desktop ne branche un serveur local qu'en stdio** (sa configuration, ou une extension `.mcpb`). Un connecteur déclaré par une adresse passe par les serveurs d'Anthropic et n'atteint pas 127.0.0.1. Claude Code accepte stdio et HTTP local.
- **Lire la base hors du service n'est pas de la lecture** : la recherche rafraîchit l'index (`search.search`), `connect` règle le journal WAL. Les corrections, la version affichée et les reports sont de la logique du service (ADR 0028).
- **L'API locale sert déjà tout en GET** : recherche, séances, espaces, projets, chapitres, notes, résumés, provenance, export Markdown du transcript corrigé. L'ADR 0043 accepte un GET vers 127.0.0.1 sans `Origin`, mais demande un ADR pour toute nouvelle intégration.
- **P1** : le pont n'ouvre rien au réseau, mais un assistant distant envoie à son fournisseur tout ce qu'il lit (transcripts, résumés, noms des présents). P5, P7 et P8 s'appliquent à ce qui est rendu.

## Décision
- **Un pont stdio, `coulisses-mcp`**, dans le paquet `coulisses_app` et inclus dans `Coulisses.app` (son Python embarqué). Il est lancé par l'assistant et ne parle qu'au service de sa propre app, sur 127.0.0.1 : port 8765 pour Coulisses, 8766 pour Coulisses (dév), qui ne lit donc jamais les données réelles.
- **Lecture seule par construction** : le pont n'envoie que des GET. Ses outils sont `chercher`, `lister_seances`, `lire_seance` (métadonnées, présents, chapitres, notes, provenance), `lire_resume` et `lire_transcript`. Il ne donne ni l'audio, ni les prompts, ni les réglages. Il n'enregistre rien, n'importe rien, ne rédige rien et ne corrige rien. Un test vérifie que le pont n'a aucune requête autre que GET.
- **Coupé par défaut.** L'accès s'ouvre dans Réglages, avec cette phrase : « Un assistant distant envoie ce qu'il lit à son fournisseur. » Le pont vérifie l'accès à chaque appel, par une route GET du service, et refuse s'il est fermé.
- **Aucune perte silencieuse** : un transcript long se lit par morceaux (par chapitre ou par tranche), et chaque réponse dit s'il reste une suite. Une app fermée, un accès coupé ou une séance introuvable donnent un message en français.
- **Provenance** : un transcript ou un résumé lu porte sa provenance (version du moteur, modèle de rédaction, date).
- **L'accord pour chaque appel** est demandé par le client MCP. Coulisses n'écrit jamais lui-même dans la configuration d'un autre outil. Les Réglages donnent :
  - la ligne `claude mcp add` à copier, pour Claude Code ;
  - une extension `.mcpb` à ouvrir, pour Claude Desktop.
- **P1 précisé** : le service et le pont n'ouvrent rien au réseau. Si des données sortent, c'est par le client que l'utilisateur a choisi d'y brancher, après qu'il a ouvert l'accès en connaissance de cause.

## Conséquences
- L'app doit être ouverte pour que l'assistant lise ; sinon l'outil le dit.
- Il faut une nouvelle dépendance : le SDK `mcp` Python, en pur Python.
- La spec gagne une section « Assistants ».
- Coût estimé de 3 à 4 jours :
  - Service : la route d'accès, le pont et ses tests, peut-être un transcript paginé (1 à 2 j) ;
  - Interface : le réglage et son avertissement (½ j) ;
  - Distribution : le pont dans le `.app`, le `.mcpb`, `essai-paquet.py` (le pont démarre, liste ses outils et refuse quand l'accès est coupé), la doc pour les amis (1 j) ;
  - Rédaction n'est pas concernée.
- Un transcript est du texte non sûr pour l'assistant (injection de consignes). La lecture seule borne le risque pour Coulisses, pas pour les autres outils de l'assistant : les Réglages le disent.
- **Restent ouvertes** :
  - l'accès espace par espace (il demanderait une migration, donc une validation) ;
  - les noms des présents rendus tels quels, ou remplacés par « Voix 1 » à la demande ;
  - le démarrage du service par le pont quand l'app est fermée.

## Alternatives écartées
- **MCP dans le service, en HTTP local** : Claude Desktop ne le voit pas sans un pont Node à installer chez les amis. Le MCP en HTTP passe par des POST, donc une nouvelle porte en écriture à défendre dans 0043. Et le service prendrait un rôle qui n'est pas le sien.
- **Lecteur autonome de `~/Coulisses/Données/`** : il ferait des écritures concurrentes à celles du service, devrait suivre les migrations et referait la logique des corrections, avec un risque pour la base réelle.
- **Piloter l'app (enregistrer, importer, rédiger, corriger)** : l'utilisateur ne le veut pas.
