import { useEffect, useState } from "react";

import { apiClient, type SourceSummary } from "../api/client";
import { SourceStatusPanel } from "../components/SourceStatusPanel";

export function SourceStatusPage() {
  const [sources, setSources] = useState<SourceSummary[]>([]);

  useEffect(() => {
    apiClient.getSources().then(setSources).catch(() => setSources([]));
  }, []);

  return (
    <div className="app-grid">
      <SourceStatusPanel
        sources={sources}
        onIngest={(source) => {
          void apiClient.ingestSource(source);
        }}
      />
    </div>
  );
}
