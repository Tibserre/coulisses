# 0037 — Un mix d'écoute qui baisse le micro quand personne n'y parle

Statut : Acceptée (2026-10-12, choix de l'utilisateur). Précise l'ADR 0032 pour l'écoute ; le traitement n'en change pas.

## Contexte
Pour une réunion en ligne ou hybride, l'ADR 0032 réunit le micro et le son de l'ordinateur en une piste, avec un seul gain : le moteur la traite, et la page de la séance la fait entendre. À l'écoute, c'est pénible : le micro du Mac est à quelques centimètres du clavier, et chaque frappe ressort au premier plan, y compris quand personne ne parle.

Baisser le micro par moments touche à ce que le moteur entend. Une personne qui parle doucement, loin du Mac (en hybride), pourrait être prise pour du silence et baissée, et le moteur perdrait ses mots. Ce risque n'est pas mesuré.

## Décision
- **Deux mixes**, faits dans les mêmes passages, sur la même horloge, de la même longueur :
  - `mix.wav`, la somme simple, avec un seul gain (ADR 0032) : **le moteur l'entend, comme avant** ;
  - `listening.wav`, le **mix d'écoute** : **la page de la séance le fait entendre**.
- Dans le mix d'écoute, le son de l'ordinateur reste tel quel, et le gain du micro varie dans le temps :
  - **0 dB** quand quelqu'un parle dans le micro ;
  - **-15 dB** quand seul l'ordinateur parle (quelqu'un à distance) ;
  - **-12 dB** sinon (le clavier, la pièce).

  Le micro n'est jamais coupé. Le tout est ensuite baissé d'un seul gain, juste assez pour ne pas saturer.
- **Parler, ce n'est pas taper.** Le niveau est mesuré toutes les 10 ms. Est actif ce qui dépasse le bruit de fond de la piste (son dixième le plus calme) de 10 dB. On retire d'abord ce qui dure moins de 120 ms (une frappe, un coup), puis on relie les blancs de moins de 250 ms (entre les syllabes).
- **Aucun mot coupé.** Le micro remonte 150 ms avant que la parole commence (l'enregistrement entier est connu) et reste levé 400 ms après. Le gain change en douceur (60 ms). Rien ne bouge dans le temps (P2).
- **Traçabilité (P7).** `mix.json` décrit les deux mixes : les gains, la règle, les paramètres, l'empreinte de chacun. Un mix fait avant cet ADR reçoit son mix d'écoute en arrière-plan à la première écoute ; d'ici là, la page fait entendre la somme simple.
- Les deux fichiers vivent dans `sources/`, et sont purgés et supprimés avec l'audio (ADR 0029).

## Conséquences
- Ce qu'on entend sur la page n'est plus exactement ce que le moteur a entendu : on entend les mêmes voix, aux mêmes instants, mais le micro est plus bas entre les paroles. L'infobulle sous le titre de la séance le dit.
- Une voix très faible dans le micro (quelqu'un loin du Mac) peut être prise pour du silence, et elle s'entend alors 12 dB plus bas. Elle reste audible, et le moteur, lui, l'entend entière.
- Le son de l'ordinateur est un silence numérique quand rien ne joue : le moindre son (une notification) y compte comme quelqu'un qui parle, et le micro est alors baissé de 15 dB au lieu de 12. Choix assumé : rien n'est perdu.
- Un mix fait avant cet ADR reçoit seulement son mix d'écoute : la somme simple que le moteur a entendue reste la même, octet pour octet. Si sa fabrication échoue, l'erreur va au journal, la page fait entendre la somme simple, l'infobulle le dit, et c'est retenté à l'écoute suivante.
- Rien n'est refait après une suppression de l'audio : la page ne prépare plus rien, et le mix refuse d'écrire.
- Le mix d'écoute coûte un passage de plus sur les deux pistes, à la fin de l'enregistrement, en arrière-plan.
- Donner au moteur le mix d'écoute, ou un mix fait de la même façon, demanderait de comparer les deux sur de vraies réunions. C'est un autre ADR.

## Alternatives écartées
- Le même mix pour l'écoute et le traitement : le risque de perdre des mots en hybride n'est pas mesuré.
- Une porte de bruit en temps réel, sans regard en avant : elle couperait le début des mots.
- Un réducteur de bruit : il modifie le son des voix, et la captation reste brute (spec §7.2).
