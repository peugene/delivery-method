# Qualification report <incr>

<!-- Rapport de recette de l'incrément <incr>, rédigé par le qualification-lead dans la langue
     du projet ; le qualification-runner y porte ses résultats. Tree et Spec sont remplis par
     le moteur ; Env décrit l'environnement réellement monté. -->

Tree: <tree>
Spec: <spec>
Env: <machine, système, navigateur, version installée, commande d'installation suivie>

## Results

<!-- Une ligne par contrôle du plan. Result : pass | fail | blocked | not-run (dire pourquoi).
     Proof : une ligne, commande → résultat ; jamais un chemin sous /tmp. -->

| Q | Mode | Result | Proof |
|---|---|---|---|
| <Q1> | <run, negative> | <pass> | <commande → résultat> |

## Anomalies

<!-- A-<n> : contrôle, observé, attendu, reproduction, severity (blocking | to-decide | note),
     et la carte a<nnn> écrite dans backlog/ au moment du constat (verdict du réfuteur ajouté
     pour une anomalie de lecture), ou le contrôle run Q<n> qu'elle est devenue. Une anomalie
     de sécurité est blocking par défaut. « none » s'il n'y en a pas. -->

- <A-1 — Q1 — observé : … — attendu : … — carte : a001 — severity : blocking>

## Not covered

<!-- Points d'entrée de la Surface sans contrôle, avec leur raison. « none » s'il n'y en a pas. -->

## Read

<!-- Lecture critique : chaque promesse de la doc (refuse, rejette, garantit) revérifiée dans
     le code, avec path:line. Une section vide dit pourquoi. -->

## Run

<!-- Exécution : chemin nominal, puis cas négatifs. Échecs du matériel de recette (material)
     réparés et déclarés ici. Une section vide dit pourquoi. -->

<!-- Verdict proposé : accepted | accepted-with-reserves | rejected. L'approbation de la
     demande de fusion par le decision owner vaut verdict. Evidence : chemin commité, facultatif. -->
Verdict: <accepted | accepted-with-reserves | rejected>
Tree: <tree>
Command: <commande qui rejoue le contrôle décisif>
Result: <comptes pass, fail, blocked, not-run>
By: qualification-lead
