import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiClient, type RegistrantDetail } from "../api/client";
import { AddressSupportingInformationPanel } from "../components/AddressSupportingInformationPanel";

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "Unknown";
  }
  return new Date(value).toLocaleDateString();
}

export function RegistrantDetailPage() {
  const { id } = useParams();
  const [registrant, setRegistrant] = useState<RegistrantDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshingAddressId, setRefreshingAddressId] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setError("Registrant id is missing.");
      setLoading(false);
      return;
    }

    let ignore = false;
    setLoading(true);
    setError(null);

    apiClient
      .getRegistrant(id)
      .then((data) => {
        if (!ignore) {
          setRegistrant(data);
        }
      })
      .catch(() => {
        if (!ignore) {
          setRegistrant(null);
          setError("Registrant data could not be loaded.");
        }
      })
      .finally(() => {
        if (!ignore) {
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [id]);

  async function handleRefreshAddress(addressId: string) {
    setRefreshingAddressId(addressId);
    try {
      const updatedAddress = await apiClient.refreshAddress(addressId);
      setRegistrant((current) =>
        current
          ? {
              ...current,
              addresses: current.addresses.map((address) =>
                address.id === updatedAddress.id ? updatedAddress : address,
              ),
            }
          : current,
      );
    } catch {
      return;
    } finally {
      setRefreshingAddressId(null);
    }
  }

  return (
    <div className="detail-layout">
      <section className="panel detail-hero">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Registrant detail</p>
            <h1>{registrant?.full_name ?? "Loading registrant"}</h1>
          </div>
          <Link className="back-link" to="/">
            Back to search
          </Link>
        </div>
        {loading ? (
          <p>Loading registrant record…</p>
        ) : error ? (
          <p>{error}</p>
        ) : registrant ? (
          <div className="meta-grid">
            <div>
              <span>External ID</span>
              <strong>{registrant.external_id}</strong>
            </div>
            <div>
              <span>Risk level</span>
              <strong>{registrant.risk_level ?? "Unknown"}</strong>
            </div>
            <div>
              <span>Date of birth</span>
              <strong>{formatDate(registrant.date_of_birth)}</strong>
            </div>
            <div>
              <span>Sex</span>
              <strong>{registrant.sex ?? "Unknown"}</strong>
            </div>
          </div>
        ) : null}
      </section>
      {registrant ? (
        <AddressSupportingInformationPanel
          addresses={registrant.addresses}
          refreshingAddressId={refreshingAddressId}
          onRefreshAddress={handleRefreshAddress}
        />
      ) : null}
    </div>
  );
}
