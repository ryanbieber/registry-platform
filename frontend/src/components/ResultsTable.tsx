import { Link } from "react-router-dom";

import type { RegistrantSummary } from "../api/client";

type ResultsTableProps = {
  rows: RegistrantSummary[];
};

export function ResultsTable({ rows }: ResultsTableProps) {
  return (
    <section className="panel">
      <h2>Search results</h2>
      <table className="results-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>External ID</th>
            <th>Risk level</th>
            <th>Last seen</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={4}>No registrants loaded yet.</td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <Link to={`/registrants/${row.id}`}>{row.full_name}</Link>
                </td>
                <td>{row.external_id}</td>
                <td>{row.risk_level ?? "Unknown"}</td>
                <td>{new Date(row.last_seen).toLocaleString()}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
