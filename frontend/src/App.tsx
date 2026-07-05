import { NavLink, Route, Routes, useLocation } from "react-router-dom";

import { STATIC_MAP_MODE } from "./config";
import { RegistrantDetailPage } from "./pages/RegistrantDetailPage";
import { UsaMapPage } from "./pages/UsaMapPage";
import { SearchPage } from "./pages/SearchPage";
import { SourceStatusPage } from "./pages/SourceStatusPage";

export default function App() {
  const location = useLocation();

  const staticRouteTree = (
    <Routes>
      <Route path="/" element={<UsaMapPage />} />
      <Route path="/map" element={<UsaMapPage />} />
      <Route path="*" element={<UsaMapPage />} />
    </Routes>
  );

  if (STATIC_MAP_MODE) {
    return staticRouteTree;
  }

  const routeTree = (
    <Routes>
      <Route path="/" element={<SearchPage />} />
      <Route path="/map" element={<UsaMapPage />} />
      <Route path="/search" element={<SearchPage />} />
      <Route path="/registrants/:id" element={<RegistrantDetailPage />} />
      <Route path="/sources" element={<SourceStatusPage />} />
    </Routes>
  );

  if (location.pathname === "/map") {
    return routeTree;
  }

  return (
    <main className="app-shell">
      <div className="app-grid">
        <header className="panel">
          <p>Unified U.S. Sex Offender Registry Data Platform</p>
          <h1>RegistryRadar</h1>
          <nav className="nav">
            <NavLink to="/">Search</NavLink>
            <NavLink to="/map">Map</NavLink>
            <NavLink to="/sources">Sources</NavLink>
          </nav>
        </header>
        {routeTree}
      </div>
    </main>
  );
}
