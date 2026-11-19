# 0090 — « Qui parle ? » : nommer les voix comme on dit qui est là

Statut : Acceptée (2026-11-19, maquettes de la page 5 de la toile validées par l'utilisateur ; puis, sur les trois écarts avec 0062 : « La plus bavarde d'abord », « Invité d'office », « L'onde de la séance »). Remplace, dans l'ADR 0062, la forme du nommage guidé (le voile, la carte, la frise et le champ du bas) ; le reste de 0062 (les détails de la séance à leur place) est inchangé.

## Contexte
Deux façons de nommer cohabitaient, qui ne se ressemblaient pas : la liste sous la réplique et la carte guidée sous un voile. Et un nom nouveau posait une question (l'ajouter à l'espace, ou juste ce nom), alors qu'à l'enregistrement on a décidé : invité d'office, membre si l'on veut (0088). Rien ne reprenait les pastilles, les grands avatars ni la feuille « Qui est là ? ».

## Décision
- **« N voix à nommer »** ouvre « Qui parle ? », une fenêtre en deux colonnes, une voix à la fois.
- **En haut**, la pile des voix qui ont un nom (ronds superposés, un invité en contour), puis la pastille grise « +N » pour celles qui restent (et les nommées au-delà de huit), comme les présents de l'écran d'enregistrement. La pile est un seul bouton : il ouvre la liste des voix, d'abord celles à nommer (la voix en cours en tête), un trait, puis celles qui ont un nom, chacune avec son temps de parole. Un clic y va, y compris pour renommer une voix nommée.
- **À gauche, on écoute** : un grand rond cerné pour la voix (vide tant que personne n'est choisi, puis le visage de la personne choisie), « Voix 7 sur 18 », son temps de parole et ses répliques ; la réplique en grand, ▶ (Espace), ‹ › pour ses autres répliques (les plus longues d'abord), et l'onde de la séance, foncée là où cette voix parle, la réplique en cours marquée. Un clic sur l'onde prend la réplique la plus proche.
- **À droite, on choisit**, exactement comme dans « Qui est là ? » : la recherche, les grands avatars, ici sur quatre colonnes (les noms sur deux lignes au plus, entiers au survol), un invité en contour avec son « + » pour le passer membre. Viennent d'abord la personne reconnue (0057), puis les présents sans voix, puis le reste de l'espace, et à la fin les personnes qui ont déjà une voix, marquées d'une petite onde sur leur avatar (le survol dit « … a déjà une voix dans cette séance », jamais un petit texte sous le nom).
- **Une question oui / non, sans mots dessous** (cas particuliers validés le 2026-11-19) : une voix reconnue ouvre la fenêtre sur « C'est Marie ? », la personne en grand, deux ronds, non et oui (Entrée) ; non dit « ce n'est pas elle » (une correction comme une autre, qui s'annule) et ouvre la liste. Choisir quelqu'un qui a déjà une voix pose tout de suite « C'est aussi Marie ? », les deux voix côte à côte, mêmes ronds : oui réunit les deux voix (P3), non revient à la liste. Pendant la question, pas de bouton en bas à droite.
- **Un nom nouveau** : la même ligne « Ajouter « … » · Nouvelle personne, en invité ». Aucune question : invité d'office. Le nom libre n'est plus proposé ici.
- **L'ordre des voix** : de la plus bavarde à la moins bavarde (plus l'ordre où on les entend).
- **En bas**, « Passer cette voix » et le bouton « C'est Paul » (Entrée), qui nomme et passe à la voix suivante. Échap ferme.

## L'onde
Le service ne garde pas encore l'enveloppe du son d'une séance. En attendant, l'onde est celle de la parole mesurée : une barre par tranche de temps, haute selon la part de la tranche où quelqu'un parle (temps des répliques du moteur, P2), jamais un niveau inventé. Une vraie enveloppe viendra du Service.

## Conséquences
- Spec §7.6 mise à jour. Le voile, la carte du nommage guidé et sa frise disparaissent, avec « Écouter les 5 plus longues à la suite ».
- La grille des personnes de « Qui est là ? » devient un morceau partagé par les deux feuilles.
- Pas encore redessinés, donc inchangés : nommer depuis une réplique (le champ en place, avec le nom libre et « Personnage joué… »), donner une réplique, le personnage joué. L'en-tête de la séance (page 4) attend la confirmation de son ordre.

## Alternatives écartées
- Garder l'ordre d'écoute (0062) : les voix les plus bavardes sont celles qui comptent pour lire la séance.
- Demander « l'ajouter à l'espace ou juste ce nom » : un invité fait le même travail, et s'archive.
- Une file de voix à nommer en ronds vides (« en file ») : onze ronds vides ne disent rien de plus que « +11 ».
