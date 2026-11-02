import React from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import App from './App.jsx'
import './styles.css'
// HashRouter : les liens fonctionnent sans configuration nginx (pas de /device/G11 à rediriger)
createRoot(document.getElementById('root')).render(<HashRouter><App /></HashRouter>)
