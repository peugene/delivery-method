---
id: s<nnn>
kind: story
title: <titre court>        # 3 à 8 mots, ce que l'utilisateur obtient : le titre de la story de spec
status: draft               # draft ; le passage en ready est un commit du decision owner
depends_on: []              # cartes à fusionner avant celle-ci
risks: []                   # authz | data-write | file-upload | data-leak | migration | api-contract | new-screen | scheduling | realtime | dependency
spec: s<nnn>                # la story de spec couverte, même numéro que la carte
code: true
show_plan: false            # true par exception : l'exécutant s'arrête sur son plan
---
<!-- Carte de story : exécutable par un agent de gamme moyenne, sans question ni décision. Langue du projet. -->
<!-- Partout ailleurs, la carte se nomme « s<nnn> : <titre court> », jamais par son seul identifiant. -->
## Objective
<Le résultat observable attendu, en une ou deux phrases.>

## Context and scope
<Où ça se passe : fichiers, routes, composants nommés. Ce qui reste hors de la carte.>
<!-- Si le schéma de données change : le schéma cible et la migration des données existantes. -->

## Oracle
<!-- Les critères fonctionnels sont un renvoi à la story de spec, jamais une copie. -->
<!-- Puis une ligne par mesure propre à l'implémentation, avec son seuil et la commande qui la mesure. -->
<!-- Puis la ligne « Not tested by this card: ». L'Oracle est figé une fois la carte prête. -->
- Functional: spec s<nnn> : <titre de la story de spec>, AC1 to AC<n>, tests @s<nnn>
- <mesure> : <seuil> — `<commande>`
- Not tested by this card: <ce que cette carte ne teste pas, ou none>

## Technical notes
<Approche envisagée, points de vigilance, ADR liées. Facultatif.>
