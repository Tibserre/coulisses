# 0091 — « Jeu et personnages » : ce qui est propre au théâtre, un réglage de l'espace

Statut : Acceptée (2026-11-19, décisions de l'utilisateur transmises par le rôle Design : « un personnage joué… c'est spécifique au théâtre… réserver ça pour un mode "théâtre" à activer ou non dans l'espace, pour éviter de confuser tout le monde », puis pour Jeu / Discussion « oui ça aussi par espace ! ça va ensemble ! » ; le nom, « Jeu et personnages » sous « Théâtre » ; « Éteint » pour les espaces existants ; une séance déjà faite ne change pas). Précise 0020 (pas de type d'espace), 0088 (la bascule Jeu ⇄ Discussion de l'écran d'enregistrement), 0061 (le genre des chapitres) et 0090 (les personnages au nommage). Les planches qui le montrent (`EspaceReglageTheatre`, `EnregD5aSansJeu`, `SeanceEnteteSansJeu`, `NommerCasPersonnage…`) restaient à valider avant tout code ; `EspaceReglageTheatre` est validée et la migration acceptée par l'utilisateur le 2026-11-19 (« Oui, la migration ») : `space.theatre`, migration 0013.

## Contexte
Jeu ⇄ Discussion et le personnage joué viennent de la troupe d'impro. Dans un espace de réunions de travail, ils n'ont pas de sens et embrouillent : une bascule qu'on ne comprend pas pendant l'enregistrement, un genre sur chaque chapitre, une question « est un personnage » en nommant les voix.

## Décision
- **Un seul réglage par espace**, « Jeu et personnages », dans les réglages de l'espace sous un titre de section « Théâtre » (après « Voix »). Il porte les deux ensemble.
- **Allumé** : pendant l'enregistrement, la bascule « Jeu depuis… » / « Discussion » et la marque du jeu au-dessus de l'onde ; sur une séance, le genre (Jeu ou Discussion) des chapitres ; en nommant les voix, « est un personnage » et « joué par ».
- **Éteint** : rien de tout cela. Les chapitres n'ont que leur titre (l'infobulle donne l'heure et la durée) ; l'enregistrement n'a pas de bascule ; un nom nouveau est une personne, jamais un personnage.
- **Éteint au départ dans tous les espaces**, ceux qui existent déjà compris : après la mise à jour, Jeu / Discussion disparaît de l'enregistrement et des chapitres des espaces actuels tant que le réglage n'y est pas allumé. Choix de l'utilisateur, contre l'avis du rôle Design (allumé pour les espaces existants) : il n'est pas à rouvrir.
- **Une séance déjà faite ne change pas** : ses chapitres Jeu / Discussion et ses personnages restent, réglage éteint ou non. L'éteindre ne change que ce qui se fait ensuite (P5 : rien n'est perdu ni réécrit).
- Ce n'est pas un type d'espace (0020) : un réglage comme la reconnaissance des voix, que le modèle de départ « Troupe d'impro » pourra allumer.

## Conséquences
- Spec §7.1, §7.2, §7.5 et §7.6 mises à jour.
- Le réglage se garde avec l'espace : un champ de plus dans les réglages de l'espace, donc un changement du schéma de données, à faire valider par l'utilisateur avant de le coder (rôle Service).
- La détection des chapitres n'est pas touchée ; seul l'affichage du genre et les marqueurs posés à la main dépendent du réglage.

## Alternatives écartées
- Allumé pour les espaces existants (proposé par Design) : écarté par l'utilisateur.
- Deux réglages, un pour Jeu / Discussion, un pour les personnages : « ça va ensemble ».
- Un type d'espace « théâtre » : 0020 n'en veut pas.
