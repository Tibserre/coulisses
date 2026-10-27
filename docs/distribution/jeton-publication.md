# Jeton de publication limité au dépôt de l'App (reste du lot 11h)

C'est l'utilisateur qui crée le jeton et le saisit. Il ne passe jamais par une conversation,
un fichier du dépôt ni l'historique du terminal.

## Pourquoi, et ce qui ne change pas
- Aujourd'hui, `gh` est connecté avec un jeton qui couvre tout le compte (`repo`, `workflow`,
  `gist`, `read:org`). Il sert aussi à `git` pour **tous** les dépôts GitHub de ce Mac (aide
  aux identifiants `gh auth git-credential`), y compris `coulisses-moteur` (privé) et les
  projets personnels.
- Le nouveau jeton ne sert **qu'à publier** : il est passé à `scripts/publier.py` par la
  variable `GH_TOKEN`, que `gh` et `git push` (par la même aide) prennent alors à la place de
  la connexion habituelle (vérifié avec `gh` 2.101.0).
- La connexion habituelle de `gh` reste en place : la retirer couperait `git` sur les autres
  dépôts et l'accès au moteur privé (`uv lock`, étiquettes du Moteur). La remplacer est un
  autre choix, à faire à part.

## 1. Créer le jeton (sur github.com, connecté au compte Tibserre)
1. Settings > Developer settings > Personal access tokens > **Fine-grained tokens** >
   Generate new token.
2. Nom : `coulisses-publication`. Expiration : 90 jours (une date dans le calendrier pour le
   renouveler).
3. Resource owner : `Tibserre`. Repository access : **Only select repositories** >
   `Tibserre/coulisses`, seul.
4. Permissions > Repository permissions :
   - **Contents : Read and write** (pousser l'étiquette, créer la version, déposer DMG et
     appcast, la rendre « Latest ») ;
   - Metadata : Read-only (ajoutée d'office).
   Rien d'autre : ni Workflows, ni Administration, ni permission de compte.
5. Generate token, puis copier la valeur (elle ne se réaffiche plus).

## 2. Le ranger dans le trousseau de macOS
Dans un Terminal, la commande demande la valeur sans l'afficher ni la garder dans
l'historique (coller, Entrée, recoller, Entrée) :

```bash
security add-generic-password -a Tibserre -s coulisses-publication -w
```

Puis vider le presse-papiers (copier n'importe quel autre texte).

## 3. Vérifier, sans rien publier
```bash
GH_TOKEN=$(security find-generic-password -s coulisses-publication -w) gh repo view Tibserre/coulisses --json visibility
```
Doit répondre `{"visibility":"PUBLIC"}`. Et la limite :
```bash
GH_TOKEN=$(security find-generic-password -s coulisses-publication -w) gh repo view Tibserre/coulisses-moteur
```
Doit échouer (dépôt introuvable) : le jeton ne voit pas le reste du compte.

## 4. Publier avec lui (avec l'accord de l'utilisateur, comme toujours)
Les trois temps de `scripts/publier.py vX.Y.Z` (préparation, `--envoyer`, `--confirmer`)
se lancent préfixés de `GH_TOKEN=$(security find-generic-password -s coulisses-publication -w)` ;
seuls les deux derniers parlent à GitHub. Pousser `main` se fait de la même façon :

```bash
GH_TOKEN=$(security find-generic-password -s coulisses-publication -w) git push origin main --follow-tags
```

## Renouveler ou retirer
- À l'expiration : regénérer le jeton sur GitHub (même page, Regenerate), puis
  `security add-generic-password -U -a Tibserre -s coulisses-publication -w`.
- Le retirer : le supprimer sur GitHub, puis `security delete-generic-password -s coulisses-publication`.
