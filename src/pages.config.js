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
import AIAssistant from './pages/AIAssistant';
import AIInsights from './pages/AIInsights';
import Analyses from './pages/Analyses';
import AuditTrail from './pages/AuditTrail';
import Dashboard from './pages/Dashboard';
import Explainability from './pages/Explainability';
import Frameworks from './pages/Frameworks';
import GapsRisks from './pages/GapsRisks';
import Home from './pages/Home';
import MappingReview from './pages/MappingReview';
import Policies from './pages/Policies';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import Simulation from './pages/Simulation';
import __Layout from './Layout.jsx';


export const PAGES = {
    "Home": Home,
    "AIAssistant": AIAssistant,
    "AIInsights": AIInsights,
    "Analyses": Analyses,
    "AuditTrail": AuditTrail,
    "Dashboard": Dashboard,
    "Explainability": Explainability,
    "Frameworks": Frameworks,
    "GapsRisks": GapsRisks,
    "MappingReview": MappingReview,
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
