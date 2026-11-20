# Coulisses

**Enregistrez une répétition ou une réunion. Coulisses vous dit qui a dit quoi, mot pour mot, et en tire un compte rendu.** Tout se passe sur votre Mac : rien n'en sort, pas même le son.

![Une séance relue : qui a dit quoi, chapitre, lecteur](docs/captures/transcript.png)

- **Qui parle quand.** Chaque phrase transcrite, attribuée à sa voix et calée sur l'enregistrement, en français, anglais, allemand, espagnol, italien ou portugais.
- **Sur place ou en visio.** Enregistrez avec le micro du Mac et le son de l'ordinateur (Zoom, Teams, Meet…), ou importez un enregistrement existant, audio ou vidéo.
- **Relire et corriger.** Cliquez une phrase pour l'entendre, renommez les voix, corrigez le texte : vos corrections ne se perdent jamais.
- **Titres, chapitres et résumés**, rédigés par un modèle de langage local avec [Ollama](https://ollama.com). C'est facultatif : sans lui, vous avez déjà le texte et qui a dit quoi.
- **Aucun compte à créer.** Ni chez nous, ni ailleurs.

## Installer

Il faut un Mac Apple Silicon, sous macOS 14.4 ou plus récent.

1. Téléchargez le DMG de la [dernière version](https://github.com/Tibserre/coulisses/releases/latest) et glissez Coulisses dans Applications.
2. Au premier lancement, macOS bloque l'app, qui n'est pas notarisée : ouvrez-la par Réglages Système › Confidentialité et sécurité › « Ouvrir quand même ».
3. Coulisses vous guide : il montre ce qu'il faut télécharger pour écouter vos séances (quelques Go, une seule fois), vous choisissez les langues, et il s'en occupe.
4. Les mises à jour arrivent d'elles-mêmes si vous l'acceptez, et ne s'installent jamais sans un clic.

### Si macOS bloque l'ouverture

Sur un Mac géré par une entreprise, macOS peut refuser d'ouvrir Coulisses sans proposer « Ouvrir quand même ». Installez-la alors depuis le Terminal :

```bash
curl -fsSL https://raw.githubusercontent.com/Tibserre/coulisses/main/installer.sh | sh
```

Le script télécharge la dernière version, vérifie qu'elle est bien signée par Coulisses, puis l'installe. Il ne demande aucun mot de passe, et une ancienne version part à la Corbeille.

Cette méthode passe outre le contrôle de macOS (Gatekeeper). Sur un Mac géré, assurez-vous d'en avoir le droit. Le [script](installer.sh) est court : vous pouvez le lire avant de le lancer.

![La bienvenue de Coulisses](docs/captures/bienvenue.png)

Les auteurs des modèles utilisés sont cités dans Réglages › Avancé.

## Pour les développeurs

Architecture, lancement depuis les sources, tests, construction de l'app et publication : [`docs/developper.md`](docs/developper.md). Les décisions sont dans [`docs/decisions/`](docs/decisions/README.md).
