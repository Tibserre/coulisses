# Installer Coulisses

Coulisses enregistre une séance (répétition d'impro, réunion de travail), reconnaît qui parle, et en rédige le compte rendu en français. **Tout reste sur ton Mac** : l'audio, les transcriptions et les résumés ne quittent jamais la machine.

Les versions sont sur la page [Releases](https://github.com/Tibserre/coulisses/releases) : prends la plus récente, celle marquée « Latest ».

## Ce qu'il faut

- Un Mac à puce Apple (M1 ou plus récent), avec macOS 14.4 ou plus récent.
- 16 Go de mémoire conseillés pour rédiger les comptes rendus (estimation, pas encore mesurée sur un Mac de 16 Go). La transcription demande environ 6 Go.
- Environ 10 Go d'espace libre pour les modèles de transcription, téléchargés une fois depuis l'app.
- [Ollama](https://ollama.com/download), installé à part, avec un modèle de langage, pour les titres, les chapitres et les résumés.

## Installer

1. Télécharge le DMG de la dernière version, ouvre-le, et glisse **Coulisses** dans **Applications**.
2. Au premier lancement, macOS bloque l'app : elle n'est pas distribuée par l'App Store. Ouvre **Réglages Système > Confidentialité et sécurité**, puis clique **Ouvrir quand même** en face de Coulisses. Ça ne se fait qu'une fois, y compris pour les mises à jour.
3. Dans Coulisses, va dans **Réglages > Transcription** et télécharge les modèles. Certains demandent d'accepter des conditions sur leur page : le lien est donné.
4. Installe Ollama, puis va dans **Réglages > Rédaction**. Quand un modèle est conseillé pour ton Mac, l'onglet le dit, avec la commande pour l'installer ; sinon, prends-en un dans la [bibliothèque d'Ollama](https://ollama.com/library). Choisis-le ensuite pour les titres, les chapitres et les résumés.
5. À ton premier enregistrement, macOS te demande l'accès au micro. Pour une réunion en ligne, il te demande aussi le son de l'ordinateur.

## Internet et mises à jour

Coulisses n'utilise internet que dans deux cas : pour télécharger ses modèles, quand tu le demandes, et pour chercher ses mises à jour sur la page des versions. Au deuxième lancement, l'app te demande si elle peut les chercher seule, une fois par jour ; tu peux changer d'avis dans **Réglages > Données**. Une mise à jour ne s'installe jamais sans ton clic, ni pendant un enregistrement ou un traitement.

## Vérifier le fichier

Chaque version donne l'empreinte SHA-256 de son DMG ; je te l'envoie aussi par un autre moyen. Pour la comparer, dans le Terminal :

```bash
shasum -a 256 ~/Downloads/Coulisses-*.dmg
```
