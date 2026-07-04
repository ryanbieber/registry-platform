import type { SourceSummary } from "../api/client";

type SourceStatusPanelProps = {
  sources: SourceSummary[];
  onIngest?: (source: string) => void;
};

export function SourceStatusPanel({ sources, onIngest }: SourceStatusPanelProps) {
  return (
    <section className="panel">
      <h2>Source ingestion status</h2>
      <div className="status-grid">
        {sources.map((source) => (
          <article key={source.name} className="panel">
            <h3>
              {source.name} {source.state ? `(${source.state})` : ""}
            </h3>
            <p>{source.notes}</p>
            <p>Enabled: {source.enabled ? "yes" : "no"}</p>
            <button type="button" onClick={() => onIngest?.(source.name)}>
              Dry-run ingest
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
