# 0040 — Distribuer Coulisses à quelques amis : une app autonome, signée par un certificat à soi, mise à jour par Sparkle

Statut : Acceptée (2026-10-13, choix de l'utilisateur : distribution dans la V1, vérification automatique des mises à jour avec accord, certificat auto-signé, dépôt de l'app public sous licence MIT, construction sur ce Mac, l'app guide pour Ollama, dépendances natives Python autonome, Sparkle et uv validées ; deux apps sur ce Mac et un passage testé de l'une à l'autre). ffmpeg et ffprobe embarqués : précisé par 0041. Place des mises à jour dans les Réglages (onglet « Ce Mac ») : précisée par 0051. Noms des essais, dossier des publications, envoi tel quel et `--premiere` : précisés par le lot 11f du plan. Remplace, dans l'ADR 0034, le lancement par `uv run`, la signature ad hoc, l'app sans réseau et l'empaquetage écarté. Ajoute une exception au hors-ligne de 0001. Précise 0016 (dossiers) et 0036 (mention du réseau).

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
  - le téléchargement et l'installation se font toujours sur un clic, jamais pendant un enregistrement ni pendant un traitement, pour qu'une chaîne ne mêle pas deux versions du moteur (P5, P7). La base est sauvegardée avant ses migrations ;
  - le `Info.plist` grave `SUAllowsAutomaticUpdates`, `SUAutomaticallyUpdate` et `SUEnableSystemProfiling` à `NO`, ce qu'un test vérifie.
- **P1 amendé** : en plus du téléchargement des modèles, seules les mises à jour de Coulisses sortent de la machine :
  - par l'app du Dock seule, jamais par le service Python ;
  - seulement l'appcast et le DMG, depuis GitHub, sans aucun profil système ;
  - la recherche se fait sur accord révocable ou sur demande, le téléchargement seulement sur clic.
- **Publication** : le dépôt `coulisses` devient public (par l'utilisateur, après relecture de l'historique), sous licence MIT. Le moteur reste privé. `release.py` ne change pas.
- **Passer de dév à publiée**, toujours dans cet ordre, chaque étape bloquant la suivante :
  1. fusion dans `main` : `release.py` pose l'étiquette `vX.Y.Z` ;
  2. `scripts/publier.py vX.Y.Z`, lancé à la main, refuse si l'arbre n'est pas propre ou si l'étiquette manque. Il passe ensuite tous les tests (Python, interface, types), construit et signe le .app, puis passe l'essai du paquet (`scripts/essai-paquet.py`) :
     - le .app construit est lancé réseau coupé, sur un dossier de données temporaire ;
     - il migre une base synthétique de la version publiée précédente, puis traite jusqu'au bout une séance synthétique ;
     - l'essai vérifie que rien ne s'écrit dans le .app et que la signature est valide, avec la même exigence désignée que la version publiée précédente.
     Un échec arrête tout ;
  3. il publie une **pré-version** sur GitHub (DMG signé en EdDSA, notes du `CHANGELOG.md`), hors de l'appcast. L'utilisateur l'installe sur son Mac et s'en sert ;
  4. `scripts/publier.py --confirmer vX.Y.Z` refuse si le DMG n'a plus l'empreinte de la pré-version ; sinon il la publie pour de bon et met l'appcast à jour : les amis la reçoivent. Une version ratée se corrige par une suivante, puisque Sparkle ne revient pas en arrière et que la base est déjà migrée.
- **Ollama chez l'ami** : l'onglet « Rédaction » dit si Ollama manque. Il donne le lien d'installation et la commande `ollama pull` d'un modèle conseillé, nommé dans `prompting/textes/reglages.toml` (P6). L'ADR 0039 ne change pas.
- **Sur ce Mac**, deux apps qui ne partagent ni service, ni permissions, ni données :
  - **Coulisses**, la version publiée, installée comme chez les amis, sert l'usage réel ;
  - **Coulisses (dév)**, avec un autre identifiant et le port 8766, est lancée depuis le dépôt sur `~/Coulisses/Données-dev`. Elle refuse le dossier de données réel. Elle n'a ni flux de mises à jour ni recherche : aucun réseau.

## Conséquences
- Chaque version pèse environ 600 Mo à télécharger (pas de mise à jour partielle) : on ne publie que les versions utiles.
- Si le certificat ou la clé EdDSA est perdu, les amis doivent réinstaller à la main et redonner les permissions : il faut les sauvegarder.
- Les amis voient l'avertissement de Gatekeeper une fois.
- L'app du Dock et le service changent de lancement : le parcours de l'ADR 0034 se revérifie à la main, et `scripts/essai-hors-ligne.sh` vérifie aussi qu'aucun appel ne part sans accord.
- Un clone public du dépôt ne peut pas reconstruire l'app sans le moteur. Le code du moteur est lisible dans le .app, sans licence : à décider dans son dépôt avant la première release (lot 11h).
- La mémoire minimale se mesure sur un Mac de 16 Go avant la première publication, et elle est écrite dans les prérequis.

## Alternatives écartées
- Developer ID (99 $ par an) : la notarisation n'est pas jugée nécessaire pour quelques amis.
- Signature ad hoc : Gatekeeper bloque l'app, et les permissions sont perdues à chaque mise à jour.
- Vérification seulement à la demande, ou hors de l'app (Homebrew, DMG à retélécharger) : jugée moins commode pour les amis.
- Un dépôt public dédié aux versions, ou des releases privées : l'utilisateur rend l'app publique ; Sparkle ne lit pas un dépôt privé.
- Construction sur GitHub Actions : elle exigerait de publier le moteur et de mettre le certificat dans le cloud.
- Téléchargement des modèles d'Ollama par l'app : il faudrait étendre P1 et l'ADR 0039 ; guider suffit.
