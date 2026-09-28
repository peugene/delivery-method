# Qualification plan

<!-- Plan de recette de cette implémentation : vivant, versionné, rejoué en entier à chaque
     recette. Rédigé par le qualification-lead dans la langue du projet.
     Les numéros de contrôle sont stables : un numéro retiré n'est jamais réattribué.
     Contrôle du format : deliveryctl qualify lint <incrément>. -->

## Surface

<!-- Dressée en lisant le code, pas la doc : routes, commandes, tâches planifiées,
     déclencheurs, installation, retrait, mise à jour. Une ligne par point d'entrée, avec ses
     contrôles (Q<n>) ou « not covered — <raison> ». À refaire à chaque recette : l'écart
     entre le code et ce tableau donne les trous. -->

| Entry point | Kind | Controls |
|---|---|---|
| <GET /lists/{id}> | <route> | <Q1> |
| <installation depuis le guide> | <install> | <Q2> |
| <purge planifiée> | <scheduled> | <not covered — raison> |

## Controls

<!-- Un contrôle par section, titre au format ci-dessous.
     Mode : read (une promesse de la doc revérifiée dans le code) ou run (exécution) ;
     ajouter « , negative » pour un cas qui doit être refusé. Des négatifs par défaut sur
     chaque risque déclaré des cartes de l'incrément (authz : un compte tiers ; migration :
     une base déjà peuplée ; scheduling : l'horloge et le redémarrage).
     Mise en place et retrait sont des contrôles comme les autres ; le retrait vérifie qu'il
     ne reste rien (conteneurs, volumes, fichiers, secrets).
     Targets : stories de spec et points d'entrée visés.
     Touches (facultatif) : chemins du code dont un changement rend le contrôle suspect
     entre deux recettes.
     Do : les gestes, par les voies publiques (interface, API, ligne de commande).
     Expect : le résultat observable qui tranche. -->

### Q1 — <un compte non invité ne lit pas une liste partagée>   [run, negative]
Targets: <s004 · GET /lists/{id}>
Touches: <src/**/share/**>
Do: <créer une liste avec le compte A, la partager avec B, la lire avec le compte C>
Expect: <refus 404, aucune donnée de la liste dans la réponse>
