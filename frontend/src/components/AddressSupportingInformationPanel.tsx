import type { Address } from "../api/client";

type AddressSupportingInformationPanelProps = {
  addresses: Address[];
  refreshingAddressId?: string | null;
  onRefreshAddress?: (addressId: string) => void;
};

function formatNumber(value: number | null | undefined): string {
  return value == null ? "—" : new Intl.NumberFormat("en-US").format(value);
}

function formatPercent(value: number | null | undefined): string {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString();
}

function addressLabel(address: Address): string {
  return [address.line1, address.line2, address.city, address.state, address.postal_code]
    .filter(Boolean)
    .join(", ");
}

export function AddressSupportingInformationPanel({
  addresses,
  refreshingAddressId,
  onRefreshAddress,
}: AddressSupportingInformationPanelProps) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Supporting information</p>
          <h2>Address context</h2>
        </div>
      </div>
      {addresses.length === 0 ? (
        <p>No address records are attached to this registrant yet.</p>
      ) : (
        <div className="address-list">
          {addresses.map((address) => {
            const census = address.supporting_information.census;
            const crime = address.supporting_information.fbi_crime;
            const isRefreshing = refreshingAddressId === address.id;

            return (
              <article key={address.id} className="address-card">
                <div className="address-card__header">
                  <div>
                    <p className="address-card__title">{addressLabel(address) || "Address not available"}</p>
                    <p className="address-card__meta">
                      Precision: {address.address_precision ?? "Unknown"}
                      {address.county ? ` · County: ${address.county}` : ""}
                    </p>
                  </div>
                  {onRefreshAddress ? (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => onRefreshAddress(address.id)}
                      disabled={isRefreshing}
                    >
                      {isRefreshing ? "Refreshing..." : "Refresh"}
                    </button>
                  ) : null}
                </div>

                <div className="info-grid">
                  <section className="info-block">
                    <h3>Census geography</h3>
                    {census ? (
                      <dl className="key-value-grid">
                        <div>
                          <dt>Status</dt>
                          <dd>{census.status}</dd>
                        </div>
                        <div>
                          <dt>Matched address</dt>
                          <dd>{census.matched_address ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Tract GEOID</dt>
                          <dd>{census.tract_geoid ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Block group</dt>
                          <dd>{census.block_group ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>County FIPS</dt>
                          <dd>{census.county_fips ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Coordinates</dt>
                          <dd>
                            {census.matched_latitude != null && census.matched_longitude != null
                              ? `${census.matched_latitude.toFixed(5)}, ${census.matched_longitude.toFixed(5)}`
                              : "—"}
                          </dd>
                        </div>
                        <div>
                          <dt>Retrieved</dt>
                          <dd>{formatDate(census.retrieved_at)}</dd>
                        </div>
                        <div>
                          <dt>Expires</dt>
                          <dd>{formatDate(census.expires_at)}</dd>
                        </div>
                      </dl>
                    ) : (
                      <p className="empty-state">No Census enrichment yet.</p>
                    )}
                    {census?.error_message ? <p className="note">{census.error_message}</p> : null}
                  </section>

                  <section className="info-block">
                    <h3>FBI crime context</h3>
                    {crime ? (
                      <dl className="key-value-grid">
                        <div>
                          <dt>Status</dt>
                          <dd>{crime.status}</dd>
                        </div>
                        <div>
                          <dt>State</dt>
                          <dd>{crime.state_name ?? crime.state_abbr ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Year</dt>
                          <dd>{crime.current_year ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Violent crime</dt>
                          <dd>{formatNumber(crime.violent_crime)}</dd>
                        </div>
                        <div>
                          <dt>Property crime</dt>
                          <dd>{formatNumber(crime.property_crime)}</dd>
                        </div>
                        <div>
                          <dt>Population</dt>
                          <dd>{formatNumber(crime.population)}</dd>
                        </div>
                        <div>
                          <dt>Agency participation</dt>
                          <dd>{formatPercent(crime.participation_pct)}</dd>
                        </div>
                        <div>
                          <dt>NIBRS participation</dt>
                          <dd>{formatPercent(crime.nibrs_participation_pct)}</dd>
                        </div>
                        <div>
                          <dt>Retrieved</dt>
                          <dd>{formatDate(crime.retrieved_at)}</dd>
                        </div>
                      </dl>
                    ) : (
                      <p className="empty-state">No FBI enrichment yet.</p>
                    )}
                    {crime?.error_message ? <p className="note">{crime.error_message}</p> : null}
                    {crime?.caveats ? <p className="note">{crime.caveats}</p> : null}
                  </section>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
