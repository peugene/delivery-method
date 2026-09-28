---
id: a<nnn>
kind: anomaly
title: <le défaut>          # 3 à 8 mots, par exemple : Le partage accepte un compte supprimé
status: to-triage           # non exécutable avant le tri du decision owner
depends_on: []
risks: []                   # les risques touchés par le défaut, par exemple [authz]
spec: ""                    # la story de spec visée par le test en échec, s'il y en a une
code: true
show_plan: false
found: "<où>@<commit>"      # par exemple story/s004@9c1e2a4, 0.2.0/Q17@9c1e2a4, nightly-<jour>@9c1e2a4
---
<!-- Carte d'anomalie : écrite tout de suite par qui constate le défaut, dans la langue du projet. Aucune correction avant le tri. -->
<!-- Partout ailleurs, la carte se nomme « a<nnn> : <titre court> », jamais par son seul identifiant. -->
## Objective
<Le comportement attendu, une fois le défaut corrigé.>

## Context and scope
<Constaté : ce qui se passe, avec sa preuve (commande et résultat, ou chemin:ligne), étiquetée measured ou read.>
<Attendu : ce qui devrait se passer, et d'où vient l'attente (story de spec, doc, contrat).>
<Reproduire : la commande ou les gestes, depuis un état neuf.>

## Oracle
<!-- Le test ou la reproduction qui échoue aujourd'hui et passe après la correction. Complété au tri si besoin. -->
- <test ou reproduction> — <résultat attendu>
- Not tested by this card: <ce que la correction ne couvre pas, ou none>

## Technical notes
<Pistes, sans correction. Sévérité proposée : blocking | to-decide | note.>
