# Le certificat qui signe Coulisses.app

L'ADR 0040 prévoit un certificat auto-signé, gardé dans le trousseau de ce Mac. Il signe chaque version de l'app : macOS reconnaît ainsi la même app d'une version à l'autre, et les amis gardent leurs permissions (micro, son de l'ordinateur). Il se crée une seule fois, à la main. Il n'entre jamais dans git.

**Le perdre, c'est obliger chaque ami à réinstaller l'app à la main et à redonner ses permissions.** La sauvegarde de l'étape 3 n'est pas facultative.

## 1. Le créer
1. Ouvrez **Trousseau d'accès** (Spotlight : « Trousseau »).
2. Menu **Trousseau d'accès > Assistant de certification > Créer un certificat…**
3. Remplissez :
   - **Nom** : `Coulisses`. C'est exactement le nom écrit dans `scripts/construction.toml`, section `[signature]`.
   - **Type d'identité** : Racine auto-signée.
   - **Type de certificat** : Signature de code.
   - Cochez **Me laisser remplacer les valeurs par défaut**.
4. **Continuer**. À **Période de validité (jours)**, mettez `3650` (dix ans).
5. **Continuer** jusqu'au bout, en gardant les valeurs proposées. À la question du trousseau, choisissez **session**. Puis **Créer**.

## 2. Lui faire confiance pour signer
1. Dans Trousseau d'accès, trousseau **session**, catégorie **Mes certificats**, double-cliquez sur « Coulisses ».
2. Dépliez **Se fier**. À **Signature de code**, choisissez **Toujours approuver**. Fermez la fenêtre : macOS demande le mot de passe de la session.
3. Vérifiez dans le Terminal :

   ```bash
   security find-identity -v -p codesigning
   ```

   La liste doit contenir `"Coulisses"`.

À la première construction, macOS demande si `codesign` peut utiliser la clé. Répondez **Toujours autoriser**, avec le mot de passe de la session. Sinon, il le redemande pour chacun des quelque 390 binaires.

## 3. Le sauvegarder hors du Mac
1. Dans **Mes certificats**, dépliez « Coulisses » pour voir sa clé privée, puis sélectionnez le certificat **et** sa clé.
2. Menu **Fichier > Exporter des éléments…**, au format **Échange d'informations personnelles (.p12)**.
3. Choisissez un mot de passe solide, et rangez-le dans un gestionnaire de mots de passe.
4. Rangez le `.p12` hors de ce Mac (clé USB, gestionnaire de mots de passe), jamais dans un dépôt git.

Sur un autre Mac, il suffit de double-cliquer sur le `.p12`, puis de refaire l'étape 2.

## Ensuite

```bash
uv run python scripts/construire.py
scripts/essai-paquet.sh dist/Coulisses.app
```

L'essai vérifie que l'app et chacun de ses binaires sont signés par « Coulisses ».
