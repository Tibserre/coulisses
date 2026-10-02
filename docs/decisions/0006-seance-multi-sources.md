# 0006 — Une séance a N sources audio dès la V1

Statut : Acceptée (2026-09-24)

## Contexte
À terme, une séance sera captée par le Mac et un ou plusieurs téléphones en même temps : meilleur son, et différences de niveau entre appareils comme indice de qui parle. Ajouter cette dimension après coup obligerait à refondre le stockage, les étapes et l'interface.

## Décision
- Modèle : `session` 1 → N `audio_source`. Chaque source a : appareil, origine (captée / importée), format, durée, empreinte SHA-256, décalage temporel par rapport à la référence (0 en V1), dérive estimée (nulle en V1).
- Toutes les étapes reçoivent **la liste des sources** et la **source de référence**. En V1, il n'y en a qu'une et les étapes l'utilisent directement.
- Les horodatages du transcript sont exprimés dans le temps de la source de référence.
- La purge supprime **toutes** les sources et leurs dérivés.

## Plus tard (hors V1)
Étape `sync` (alignement par intercorrélation et correction de dérive d'horloge), choix ou mixage de la meilleure source par passage, indices spatiaux pour la diarisation.

## Conséquences
En V1, le coût se limite à une table, une clé étrangère et une liste à un élément.
