# Architecture
<!-- Une page, dans la langue du projet, écrite par le technical-lead au cadrage et relue par le decision owner. -->
<!-- Décrit le présent : ce qui est, pas comment on y est arrivé. Le pourquoi de chaque choix structurant va dans une ADR de docs/adr/. -->

## Context
<Ce que livre ce dépôt : l'implémentation de quelle spec (spec.lock), pour quels usages, sous quelles contraintes (hébergement, données, volumes).>

## Stack
<Langage, framework, base de données, outillage de build et de test, avec leur version. Chaque choix structurant renvoie à son ADR.>

## Structure
<Les modules ou couches, ce que contient chacun, et la règle de dépendance entre eux.>

## Data
<Les entités principales, où elles vivent, comment le schéma évolue (migrations).>

## Interfaces
<Routes, API, écrans, tâches planifiées. Les routes du harnais de test (reset, users, login-as, tick), servies en mode test seulement.>

## Cross-cutting
<Droits d'accès, erreurs, configuration et secrets, journaux, temps et fuseaux horaires.>

## Tests
<Quelle couche teste quoi ; les commandes check, acceptance et serve de delivery.toml ; la commande des tests ciblés.>

## Decisions
<Index des ADR : numéro, titre, statut.>
