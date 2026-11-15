# Rapport de sécurité — injections SQL et XSS

**Projet :** EnviroMesh  
**Date :** 6 novembre 2026  
**Périmètre :** revue statique ciblée du backend Core, des requêtes PostgreSQL et du dashboard React. Aucun payload actif n'a été exécuté et aucune base ou instance externe n'a été testée.

## Résumé

La revue du code actuel n'a pas confirmé de vulnérabilité exploitable par injection SQL ou XSS dans les surfaces examinées. Les requêtes PostgreSQL utilisent des paramètres séparés des instructions SQL ; le rendu du dashboard utilise React sans sink HTML dangereux détecté dans le code source du dashboard.

Cette conclusion est limitée au code et au périmètre inspectés. Elle ne constitue ni une certification de sécurité ni la preuve qu'aucune vulnérabilité n'existe dans les autres composants, dépendances, configurations ou versions déployées.

| Risque | Résultat de la revue | Protections constatées |
|---|---|---|
| Injection SQL | Aucune injection confirmée dans les accès SQL examinés. | Paramètres psycopg séparés ; colonnes dynamiques d'édition utilisateur limitées par liste blanche. |
| XSS | Aucune injection de script confirmée dans le dashboard examiné. | Rendu JSX/React normal ; aucune utilisation trouvée de `dangerouslySetInnerHTML`, `innerHTML`, `document.write`, `eval` ou `new Function`. |

## 1. Injection SQL

### Risque théorique

Une injection SQL peut survenir lorsqu'une donnée contrôlée par un utilisateur — identifiant d'appareil, filtre, e-mail, nom, groupe ou valeur reçue d'un autre système — est concaténée dans une instruction SQL. La base pourrait alors interpréter cette donnée comme une partie de la commande plutôt que comme une valeur.

### Protections constatées dans EnviroMesh

- Les lectures du registre et de la télémétrie passent par des requêtes paramétrées dans [`database_access.py`](../raspberry_pi/core/backend/services/database_access.py). Les filtres tels que `device_id`, `group_code`, dates et limite sont transmis à `cursor.execute(sql, params)`.
- Les accès aux utilisateurs et aux groupes utilisent également des paramètres SQL dans [`user_store.py`](../raspberry_pi/core/backend/services/user_store.py) et [`group_store.py`](../raspberry_pi/core/backend/services/group_store.py).
- Lors de la mise à jour d'un utilisateur, les noms de colonnes ne viennent pas directement de la requête HTTP : ils sont parcourus depuis une liste blanche dans [`user_store.py`](../raspberry_pi/core/backend/services/user_store.py). C'est important, car les paramètres SQL protègent les valeurs, pas les noms de colonnes ou autres fragments structurels.
- Les écritures de télémétrie utilisent des paramètres dans [`database_writer.py`](../raspberry_pi/core/backend/services/database_writer.py).
- L'API borne certains champs avec Pydantic, notamment `limit` sur la route de télémétrie et les formats de groupe/utilisateur. Cette validation complète les paramètres SQL, mais ne les remplace pas.
- Les tests de périmètre et d'accès sont dans [`test_auth_scoping.py`](../tests/core/test_auth_scoping.py). Ils vérifient notamment que les filtres de groupe sont transmis comme paramètres.

### Vérifications recommandées

1. Ajouter des tests unitaires avec une fonction de base simulée (`monkeypatch`) qui vérifient que toute valeur reçue reste dans le dictionnaire de paramètres et n'est pas incorporée au texte SQL.
2. Garder les tests des champs structurels (colonnes, ordre, direction) basés sur une liste blanche.
3. Exécuter les tests d'intégration SQL uniquement sur une base de test jetable, avec des données synthétiques, et vérifier que les résultats restent limités au périmètre autorisé.
4. Réexaminer toute nouvelle requête SQL lors de l'ajout d'une route ou d'un filtre ; éviter toute interpolation de valeur utilisateur dans une chaîne SQL.

### Mesures complémentaires recommandées

- Appliquer le principe du moindre privilège au rôle PostgreSQL utilisé par l'API : il ne devrait pas disposer de privilèges administrateur ni de droits de schéma inutiles.
- Conserver des limites et validations côté serveur pour les identifiants, dates, filtres et tailles de requêtes.
- Ne pas renvoyer les détails SQL ou les traces internes au client. Les erreurs DB de la couche de lecture sont journalisées côté serveur et transformées en réponse générique `503`.

## 2. Cross-Site Scripting (XSS)

### Risque théorique

Une XSS peut se produire si une donnée non fiable — par exemple un nom de capteur, une zone, une mesure ou un texte reçu via MQTT — est interprétée comme du HTML ou du JavaScript dans le navigateur. Les sources possibles incluent les formulaires, l'API, les messages MQTT et les données de la base.

### Protections constatées dans EnviroMesh

- Le dashboard affiche les valeurs observées par les composants React. Le rendu de texte normal de JSX échappe les caractères HTML au lieu de les interpréter.
- La recherche dans le code source du dashboard n'a trouvé aucune utilisation de `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`, `document.write`, `eval` ou `new Function`.
- Les noms de capteurs, zones, alertes et appareils affichés comme enfants JSX restent donc du texte selon le rendu standard React.
- Les modèles Pydantic valident plusieurs champs d'administration (tailles, formats d'e-mail et de groupe). Cela réduit les entrées invalides, mais la protection XSS principale reste l'encodage contextuel au moment de l'affichage.

### Limites et risques résiduels

- La validation d'entrée seule ne suffit pas à prévenir une XSS : une valeur valide pour la base peut rester dangereuse si elle est ultérieurement interprétée comme HTML.
- Le stockage du JWT dans `sessionStorage` signifie qu'un script exécuté dans l'origine du dashboard pourrait lire le jeton. `sessionStorage` limite sa durée de persistance par rapport à `localStorage`, mais ne protège pas contre une XSS.
- Une future fonctionnalité de rendu de HTML riche, de graphiques personnalisés ou de modèles doit faire l'objet d'une revue spécifique ; les sinks HTML bruts ne doivent pas être ajoutés sans assainissement approprié.
- Cette revue statique ne vérifie pas les extensions navigateur, dépendances exécutées, en-têtes HTTP réellement servis ni la configuration d'un proxy de production.

### Vérifications et mesures recommandées

1. Garder les valeurs non fiables dans le rendu textuel normal de React et éviter l'insertion de HTML brut.
2. Si une fonctionnalité exige du HTML riche, utiliser un assainisseur maintenu et limiter explicitement les balises et attributs autorisés ; compléter par une politique CSP adaptée.
3. Ajouter des tests de rendu avec des chaînes inertes contenant des caractères comme `<`, `>` et `&`, puis vérifier qu'elles apparaissent comme du texte et ne créent pas d'éléments HTML.
4. Valider les messages MQTT (schéma, types, tailles, clés de métriques) et les champs saisis par l'utilisateur côté serveur. Cette validation protège aussi la qualité des données et la disponibilité ; elle ne remplace pas l'encodage à l'affichage.
5. Pour réduire l'exposition du jeton au JavaScript, envisager une migration vers un cookie `HttpOnly`, `Secure`, `SameSite` avec des protections CSRF appropriées. Cela limite la lecture du jeton par script, mais ne neutralise pas une XSS : un script injecté pourrait toujours agir dans la session de la page.
6. Servir l'application sur HTTPS dès qu'elle est accessible au-delà du poste local et configurer des en-têtes de sécurité adaptés au déploiement.

## 3. État de validation et limites

- Aucun payload actif n'a été utilisé.
- Aucun test n'a été exécuté contre une instance publique, une base réelle ou un appareil connecté.
- La revue de code confirme les protections visibles dans les fichiers cités ; elle ne prouve pas l'absence de vulnérabilité dans l'ensemble du dépôt ou de la configuration de déploiement.
- Pour une validation dynamique, utiliser uniquement une instance locale isolée, des données synthétiques et des tests automatisés non destructifs.
