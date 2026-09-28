---
id: t<nnn>
kind: task
title: <titre court>        # 3 à 8 mots : ce que l'utilisateur ou l'équipe obtient
status: draft               # draft ; le passage en ready est un commit du decision owner
depends_on: []              # cartes à fusionner avant celle-ci
risks: []                   # authz | data-write | file-upload | data-leak | migration | api-contract | new-screen | scheduling | realtime | dependency
spec: ""                    # facultatif : la story de spec servie, s'il y en a une
code: true                  # false : carte sans code (documentation, chapeau) ; l'Oracle devient facultatif
show_plan: false            # true par exception : l'exécutant s'arrête sur son plan
---
<!-- Carte de tâche : travail technique hors spec (outillage, CI, harnais de test, enquête, documentation). -->
<!-- Partout ailleurs, la carte se nomme « t<nnn> : <titre court> », jamais par son seul identifiant. -->
## Objective
<Le résultat observable attendu, en une ou deux phrases.>

## Context and scope
<Où ça se passe : fichiers, commandes, composants nommés. Ce qui reste hors de la carte.>

## Oracle
<!-- Obligatoire si code: true. Une ligne par résultat vérifiable, avec son seuil et la commande qui le mesure. -->
<!-- Puis la ligne « Not tested by this card: ». L'Oracle est figé une fois la carte prête. -->
- <résultat> : <seuil> — `<commande>`
- Not tested by this card: <ce que cette carte ne teste pas, ou none>

## Technical notes
<Approche envisagée, points de vigilance, ADR liées. Facultatif.>
