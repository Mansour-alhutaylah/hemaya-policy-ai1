/**
 * pages.config.js - Page routing configuration
 * 
 * This file is AUTO-GENERATED. Do not add imports or modify PAGES manually.
 * Pages are auto-registered when you create files in the ./pages/ folder.
 * 
 * THE ONLY EDITABLE VALUE: mainPage
 * This controls which page is the landing page (shown when users visit the app).
 * 
 * Example file structure:
 * 
 *   import HomePage from './pages/HomePage';
 *   import Dashboard from './pages/Dashboard';
 *   import Settings from './pages/Settings';
 *   
 *   export const PAGES = {
 *       "HomePage": HomePage,
 *       "Dashboard": Dashboard,
 *       "Settings": Settings,
 *   }
 *   
 *   export const pagesConfig = {
 *       mainPage: "HomePage",
 *       Pages: PAGES,
 *   };
 * 
 * Example with Layout (wraps all pages):
 *
 *   import Home from './pages/Home';
 *   import Settings from './pages/Settings';
 *   import __Layout from './Layout.jsx';
 *
 *   export const PAGES = {
 *       "Home": Home,
 *       "Settings": Settings,
 *   }
 *
 *   export const pagesConfig = {
 *       mainPage: "Home",
 *       Pages: PAGES,
 *       Layout: __Layout,
 *   };
 *
 * To change the main page from HomePage to Dashboard, use find_replace:
 *   Old: mainPage: "HomePage",
 *   New: mainPage: "Dashboard",
 *
 * The mainPage value must match a key in the PAGES object exactly.
 */
// Phase 14: lazy-load every page so each becomes its own Vite chunk.
// Heavy libs (recharts, framer-motion, jspdf via lib/policyReport,
// html2canvas, etc.) are pulled in only when their consuming page is
// first navigated to. Suspense fallback lives in App.jsx.
//
// Layout is NOT lazy-loaded — it wraps every route and is part of the
// initial shell.
import { lazy } from 'react';
import __Layout from './Layout.jsx';

const AIAssistant    = lazy(() => import('./pages/AIAssistant'));
const AIInsights     = lazy(() => import('./pages/AIInsights'));
const Analyses       = lazy(() => import('./pages/Analyses'));
const Dashboard      = lazy(() => import('./pages/Dashboard'));
const Explainability = lazy(() => import('./pages/Explainability'));
const Frameworks     = lazy(() => import('./pages/Frameworks'));
const GapsRisks      = lazy(() => import('./pages/GapsRisks'));
const Home           = lazy(() => import('./pages/Home'));
const MappingReview  = lazy(() => import('./pages/MappingReview'));
const PolicyVersions = lazy(() => import('./pages/PolicyVersions'));
const Policies       = lazy(() => import('./pages/Policies'));
const Reports        = lazy(() => import('./pages/Reports'));
const Settings       = lazy(() => import('./pages/Settings'));
const Simulation     = lazy(() => import('./pages/Simulation'));


export const PAGES = {
    "Home": Home,
    "AIAssistant": AIAssistant,
    "AIInsights": AIInsights,
    "Analyses": Analyses,
    "Dashboard": Dashboard,
    "Explainability": Explainability,
    "Frameworks": Frameworks,
    "GapsRisks": GapsRisks,
    "MappingReview": MappingReview,
    "PolicyVersions": PolicyVersions,
    "Policies": Policies,
    "Reports": Reports,
    "Settings": Settings,
    "Simulation": Simulation,
}

export const pagesConfig = {
    mainPage: "Home",
    Pages: PAGES,
    Layout: __Layout,
};
