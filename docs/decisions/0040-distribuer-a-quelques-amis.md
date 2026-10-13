# 0040 — Distribuer Coulisses à quelques amis : une app autonome, signée par un certificat à soi, mise à jour par Sparkle

Statut : Proposée (choix de l'utilisateur, 2026-10-13 : distribution dans la V1, vérification automatique des mises à jour avec accord, certificat auto-signé, dépôt de l'app public sous licence MIT, construction sur ce Mac, l'app guide pour Ollama, dépendances natives Python autonome, Sparkle et uv validées). Remplacera, dans l'ADR 0034, le lancement par `uv run` et la signature ad hoc.

## Contexte
La spec excluait la distribution (§3, §8) ; l'utilisateur veut partager Coulisses avec quelques amis et leur pousser des mises à jour. Aujourd'hui, l'app du Dock lance `uv run` depuis le dépôt (uv, Python 3.12, outils Xcode requis), compile le programme du son de l'ordinateur au premier usage, et est signée ad hoc : Gatekeeper la bloque ailleurs, et les permissions sont perdues à chaque recompilation. Le moteur est pris par étiquette depuis un chemin local, et il appelle `uv` (trouvé dans le PATH) pour installer l'environnement de diarisation (Python 3.10). L'environnement Python de l'app pèse 1,5 Go (torch 554 Mo) ; modèles et environnement font environ 6,7 Go de plus. Les deux dépôts GitHub sont privés. Principes touchés : P1 (réseau), P6 et P7 (inchangés), P8 (mises à jour visibles).

## Décision
- **Périmètre** : la distribution à quelques amis entre dans la V1. Chaque ami est l'unique utilisateur de son Mac (Apple Silicon, macOS 14.4 au moins).
- **Un `Coulisses.app` autonome**, construit sur ce Mac, sans uv ni Xcode chez l'ami. Il contient :
  - un Python 3.12 autonome (python-build-standalone) avec l'app et ses dépendances figées par `uv.lock`, dont le moteur à son étiquette ;
  - l'interface déjà construite ;
  - le programme du son de l'ordinateur précompilé ;
  - le binaire `uv`, mis dans le PATH du service pour l'installation de l'environnement de diarisation ;
  - les licences des dépendances.
  Les `.pyc` sont compilés à la construction, et rien ne s'écrit dans le .app.
- **Données de l'ami** : `~/Coulisses/` avec `Données/`, `Modèles/` et `Environnements/` (ADR 0010, 0016), sans `App/` ni `Moteur/`. Les Python et le cache de uv vont aussi sous `~/Coulisses/Environnements/`. Les modèles se téléchargent depuis Réglages, onglet « Transcription », sur demande (ADR 0036).
- **Signature** : un certificat auto-signé « Coulisses », valable 10 ans, gardé dans le Trousseau de ce Mac et sauvegardé hors du Mac. Il signe chaque binaire du .app. Il n'y a ni notarisation ni runtime renforcé. Les permissions micro et son de l'ordinateur sont ainsi gardées d'une version à l'autre. Au premier lancement, l'ami ouvre l'app par Réglages Système > Confidentialité et sécurité > « Ouvrir quand même ».
- **Mises à jour par Sparkle**, dans l'app Swift du Dock :
  - flux `appcast.xml` dans les releases GitHub ; chaque DMG est signé par une clé EdDSA, gardée dans le Trousseau ;
  - la vérification automatique (une fois par jour) ne commence qu'après l'accord de l'ami. Elle se coupe dans Réglages, onglet « Données », à côté de « Rechercher maintenant » ;
  - aucun profil système n'est envoyé. L'installation se fait toujours sur un clic, jamais pendant un enregistrement : les règles de ⌘Q de l'ADR 0034 s'appliquent, et la base est sauvegardée avant ses migrations.
- **P1 amendé** : en plus du téléchargement des modèles, seule la recherche de mises à jour de Coulisses sur GitHub sort de la machine. Elle se fait sur accord révocable ou sur demande, et le service Python n'y prend aucune part.
- **Publication** : le dépôt `coulisses` devient public (par l'utilisateur, après relecture de l'historique), sous licence MIT. Le moteur reste privé. `scripts/publier.py`, lancé à la main depuis une étiquette `vX.Y.Z` de `main`, fait les étapes suivantes :
  - construire et signer ;
  - faire le DMG, le signer en EdDSA et écrire l'appcast ;
  - le publier par `gh release`, avec les notes du `CHANGELOG.md`.
  `release.py` ne change pas.
- **Ollama chez l'ami** : l'onglet « Rédaction » dit si Ollama manque. Il donne le lien d'installation et la commande `ollama pull` d'un modèle conseillé, nommé dans `prompting/textes/reglages.toml` (P6). L'ADR 0039 ne change pas.
- **Sur ce Mac** :
  - l'app publiée sert l'usage réel ;
  - l'app de développement devient « Coulisses (dév) », avec un autre identifiant et le port 8766, sur `~/Coulisses/Données-dev`. Les deux ne partagent ni service ni permissions.

## Conséquences
- Chaque version pèse environ 600 Mo à télécharger (pas de mise à jour partielle) : on ne publie que les versions utiles.
- Si le certificat ou la clé EdDSA est perdu, les amis doivent réinstaller à la main et redonner les permissions : il faut les sauvegarder.
- Les amis voient l'avertissement de Gatekeeper une fois.
- L'app du Dock et le service changent de lancement : le parcours de l'ADR 0034 se revérifie à la main, et `scripts/essai-hors-ligne.sh` vérifie aussi qu'aucun appel ne part sans accord.
- Un clone public du dépôt ne peut pas reconstruire l'app sans le moteur. Le code du moteur est lisible dans le .app, sans licence : c'est à décider dans son dépôt.
- La mémoire minimale se mesure sur un Mac de 16 Go avant la première publication, et elle est écrite dans les prérequis.

## Alternatives écartées
- Developer ID (99 $ par an) : la notarisation n'est pas jugée nécessaire pour quelques amis.
- Signature ad hoc : Gatekeeper bloque l'app, et les permissions sont perdues à chaque mise à jour.
- Vérification seulement à la demande, ou hors de l'app (Homebrew, DMG à retélécharger) : jugée moins commode pour les amis.
- Un dépôt public dédié aux versions, ou des releases privées : l'utilisateur rend l'app publique ; Sparkle ne lit pas un dépôt privé.
- Construction sur GitHub Actions : elle exigerait de publier le moteur et de mettre le certificat dans le cloud.
- Téléchargement des modèles d'Ollama par l'app : il faudrait étendre P1 et l'ADR 0039 ; guider suffit.
