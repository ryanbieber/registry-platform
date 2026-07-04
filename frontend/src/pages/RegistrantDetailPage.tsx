import { useParams } from "react-router-dom";

import { AddressMapPlaceholder } from "../components/AddressMapPlaceholder";

export function RegistrantDetailPage() {
  const { id } = useParams();

  return (
    <div className="app-grid">
      <section className="panel">
        <h1>Registrant detail</h1>
        <p>Selected registrant ID: {id}</p>
        <p>Detailed data binding is intentionally left as a skeleton.</p>
      </section>
      <AddressMapPlaceholder />
    </div>
  );
}
