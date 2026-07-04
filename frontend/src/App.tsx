import { NavLink, Route, Routes } from "react-router-dom";

import { RegistrantDetailPage } from "./pages/RegistrantDetailPage";
import { SearchPage } from "./pages/SearchPage";
import { SourceStatusPage } from "./pages/SourceStatusPage";

export default function App() {
  return (
    <main className="app-shell">
      <div className="app-grid">
        <header className="panel">
          <p>Unified U.S. Sex Offender Registry Data Platform</p>
          <h1>Registry platform skeleton</h1>
          <nav className="nav">
            <NavLink to="/">Search</NavLink>
            <NavLink to="/sources">Sources</NavLink>
          </nav>
        </header>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/registrants/:id" element={<RegistrantDetailPage />} />
          <Route path="/sources" element={<SourceStatusPage />} />
        </Routes>
      </div>
    </main>
  );
}
