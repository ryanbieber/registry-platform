import { useEffect, useState } from "react";

import { apiClient, type RegistrantSummary } from "../api/client";
import { ResultsTable } from "../components/ResultsTable";
import { SearchFilters } from "../components/SearchFilters";

export function SearchPage() {
  const [rows, setRows] = useState<RegistrantSummary[]>([]);

  useEffect(() => {
    apiClient.getRegistrants().then(setRows).catch(() => setRows([]));
  }, []);

  return (
    <div className="app-grid">
      <SearchFilters />
      <ResultsTable rows={rows} />
    </div>
  );
}
