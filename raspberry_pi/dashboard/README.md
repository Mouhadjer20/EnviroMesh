# Dashboard EnviroMesh (React + Vite)

```
npm install        # une fois (génère package-lock.json, requis par le Dockerfile)
npm run dev        # http://localhost:5173, /api est transmis à VITE_API_PROXY
docker compose up --build -d dashboard nginx   # version servie par nginx
```

- `src/pages/` : Overview (vue d'ensemble), Device (détail d'un nœud), Alerts
- `src/components/` : Chart, Stat
- `src/hooks/useApi.js` : lecture périodique de l'API
- `src/context/DataContext.jsx` : nœuds, groupes et dernières mesures partagés
- `src/lib.js` : métriques, seuils d'alerte, formats, exports
- La vue d’ensemble utilise les API réelles des nœuds et de télémétrie pour ses indicateurs, mesures, graphiques et événements récents.
- La navigation indique « À venir » pour les modules dont l’API/backend n’est pas opérationnel ; aucune donnée fictive n’est présentée comme réelle.
- L’affichage du MQ-2 en ppm dépend de son étalonnage et les seuils d’alerte restent provisoires. La gestion des utilisateurs et les commandes d’actionneurs restent désactivées sans autorisation côté serveur.

Routage par `#` (HashRouter) : aucune configuration nginx supplémentaire.
