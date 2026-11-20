# 0085 — Installer Coulisses en une ligne, quand macOS ne propose pas « Ouvrir quand même »

Statut : Acceptée (2026-11-13, par l'utilisateur, après relecture du script et du texte ; proposée par Distribution à sa demande, relayée par Pilotage). Précise 0040.

## Contexte
- ADR 0040 : Coulisses est signée par un certificat à soi, sans notarisation. Au premier lancement d'une app téléchargée par un navigateur, macOS la bloque, et on l'ouvre par Réglages Système › Confidentialité et sécurité › « Ouvrir quand même ».
- Sur un Mac géré (Jamf), un profil peut retirer ce bouton (`DisableOverride`). C'est le cas chez une collègue de l'utilisateur : elle ne peut pas ouvrir Coulisses. Sur le Mac de l'utilisateur, `spctl` rejette aussi l'app, qui ne tourne que parce qu'elle n'a jamais été mise en quarantaine.
- Un fichier téléchargé par `curl` ne reçoit pas l'attribut de quarantaine : Gatekeeper ne l'examine pas à l'ouverture.

## Décision
- **Un script `installer.sh` à la racine du dépôt**, lancé par `curl -fsSL https://raw.githubusercontent.com/Tibserre/coulisses/main/installer.sh | sh`. Il installe ou met à jour Coulisses depuis la dernière version **confirmée** : il lit l'appcast de `releases/latest`, celui que Sparkle lit, qui n'existe que pour une version confirmée (0040).
- **Il remplace le contrôle de Gatekeeper par le sien, avant toute installation** : le DMG fait la taille annoncée par l'appcast ; l'app passe `codesign --verify --deep --strict` ; elle satisfait l'exigence désignée de chaque version publiée (identifiant `io.github.tibserre.coulisses` et feuille du certificat « Coulisses »), écrite dans le script ; sa version est celle de l'appcast. Sinon il refuse, sans rien installer. La copie installée est revérifiée avant de prendre la place de l'ancienne.
- **Rien n'est supprimé** (P8) : la nouvelle app est copiée et revérifiée à côté de l'ancienne ; ensuite seulement, l'ancienne part à la Corbeille, ou dans `~/Coulisses/Anciennes versions` si la Corbeille refuse (elle est protégée sans accès complet au disque). Une Coulisses ouverte (lanceur ou service) arrête le script, qui demande de la quitter.
- **Rien ne s'exécute avant que le script soit lu en entier** : tout est dans une fonction appelée à la dernière ligne, pour qu'un téléchargement coupé n'en exécute pas la moitié.
- **Pas de sudo** : `/Applications` s'il est inscriptible, sinon `~/Applications`. Le DMG et son point de montage sont nettoyés à la sortie, quoi qu'il arrive. Messages en français, arrêt à la première erreur. Coulisses s'ouvre à la fin.
- Le README le présente dans « Si macOS bloque l'ouverture », en disant que c'est un contournement de Gatekeeper, que sur un Mac géré le blocage est un choix de l'administrateur, et que la vérification vaut ce que vaut le dépôt, d'où viennent le script et l'app. Il ne donne pas d'autre méthode (pas de `xattr`, qui ne vérifie rien) : le script seul (2026-11-13, choix de l'utilisateur).

## Conséquences
- Le DMG et Sparkle restent la voie normale. Une fois installée par le script, Coulisses se met à jour par Sparkle comme les autres : Sparkle vérifie la signature EdDSA de chaque mise à jour (0040).
- Le script ne vérifie pas la signature EdDSA du DMG : macOS n'a pas d'outil pour le faire sans installation. Sa garantie, c'est le certificat de Coulisses, dont la clé privée ne quitte pas ce Mac.
- Si le certificat change un jour, l'exigence écrite dans `installer.sh` change avec lui, dans le même commit que la version qui l'introduit. `scripts/publier.py` refuse déjà de publier une version dont l'exigence désignée a changé sans le dire.
- Le script vit sur `main` : il est servi tel qu'il y est poussé. Une modification de `installer.sh` se pousse donc avec le même soin qu'une version.
