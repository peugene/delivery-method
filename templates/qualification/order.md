---
increment: <incr>
issued-by: qualification-lead
base: <base>
---
<!-- Ordre de travail du qualification-runner, écrit par le qualification-lead dans la langue
     du projet, 60 lignes au plus. Le runner est une session jetable sans surveillance : il ne
     pose pas de question ; tout ce qu'il doit savoir est ici, dans le plan et dans le code.
     Objective, Controls to run et Environment sont remplis, puis le lead commite ce fichier :
     deliveryctl qualify run refuse un ordre non commité, et git garde chaque version reçue. -->
## Objective
<Une phrase : ce que cette passe doit établir.>

## Decisions
<Décisions du decision owner qui s'appliquent, citées mot pour mot avec leur date, ou « none ».>

## Controls to run
<Numéros du plan dans l'ordre (mise en place d'abord, retrait en dernier), ou « all run controls ».>

## Environment
<Montage d'un environnement vierge (guide d'installation suivi à la lettre, ou kit : bash, just --justfile ou docker compose -f sur qualification/kit/), ports, comptes, démontage.>

## Read by the lead — re-verify, do not trust
- <fait> (<path:line>, read | measured | inferred)

## Constraints
- Le produit ne change pas pendant la recette : aucune correction de code, aucun push.
- Données de test par les voies publiques (interface, API, ligne de commande).
- État de travail (pile, sondes, notes) dans qualification/work/, jamais sous /tmp.

## Deliverables
- Dans qualification/reports/<incr>.md, section Results : une ligne par contrôle joué
  (pass | fail | blocked | not-run) et sa preuve en une ligne, commande → résultat.
- Section Run du rapport : environnement réellement monté, matériel réparé.
- Une carte d'anomalie par défaut distinct, écrite dès le constat, et sa ligne A-<n>.
- Commits dans qualification/ et backlog/ seulement.

## Failure classification
- `material` : le matériel de recette est en cause (donnée, requête, script ou attendu
  périmé). Le réparer dans qualification/, le déclarer dans la section Run, rejouer.
- `product` : le produit se comporte mal, ou sa doc promet ce qu'il ne fait pas. Écrire
  aussitôt backlog/a<nnn>-<slug>.md (kind: anomaly, status: to-triage,
  found: <incr>/Q<n>@<commit court>, spec: la story visée) ; ne jamais corriger le produit.
- Un contrôle qui n'a pas pu se jouer est `blocked`, avec ce qui manque.
- Dans le doute entre `material` et `product` : `product`.
