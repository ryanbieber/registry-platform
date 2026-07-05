export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type RegistrantSummary = {
  id: string;
  external_id: string;
  full_name: string;
  risk_level: string | null;
  last_seen: string;
};

export type H3Cell = {
  h3_index: string;
  count: number;
  person_ids: string[];
  center_latitude: number;
  center_longitude: number;
  boundary: Array<[number, number]>;
};

export type IowaH3Map = {
  state: "IA";
  resolution: number;
  total_people: number;
  cells: H3Cell[];
};

export type CensusGeography = {
  provider: "census";
  kind: "census_geography";
  status: string;
  source_url: string | null;
  retrieved_at: string | null;
  expires_at: string | null;
  error_message: string | null;
  matched_address: string | null;
  matched_latitude: number | null;
  matched_longitude: number | null;
  state_abbr: string | null;
  state_fips: string | null;
  county_fips: string | null;
  county_name: string | null;
  tract: string | null;
  tract_geoid: string | null;
  block_group: string | null;
  block_group_geoid: string | null;
  benchmark: string | null;
  vintage: string | null;
};

export type CrimeContext = {
  provider: "fbi";
  kind: "crime_context";
  status: string;
  source_url: string | null;
  retrieved_at: string | null;
  expires_at: string | null;
  error_message: string | null;
  state_abbr: string | null;
  state_name: string | null;
  current_year: number | null;
  population: number | null;
  violent_crime: number | null;
  homicide: number | null;
  rape_legacy: number | null;
  rape_revised: number | null;
  robbery: number | null;
  aggravated_assault: number | null;
  property_crime: number | null;
  burglary: number | null;
  larceny: number | null;
  motor_vehicle_theft: number | null;
  total_agencies: number | null;
  participating_agencies: number | null;
  participation_pct: number | null;
  nibrs_participating_agencies: number | null;
  nibrs_participation_pct: number | null;
  participating_population: number | null;
  participating_population_pct: number | null;
  caveats: string | null;
};

export type SupportingInformation = {
  census: CensusGeography | null;
  fbi_crime: CrimeContext | null;
};

export type Address = {
  id: string;
  line1: string | null;
  line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  county: string | null;
  latitude: number | null;
  longitude: number | null;
  address_precision: string | null;
  supporting_information: SupportingInformation;
};

export type Offense = {
  offense_name: string;
  offense_date: string | null;
  conviction_date: string | null;
  statute: string | null;
};

export type RegistrantDetail = RegistrantSummary & {
  date_of_birth: string | null;
  race: string | null;
  sex: string | null;
  addresses: Address[];
  offenses: Offense[];
};

export type SourceSummary = {
  name: string;
  state: string | null;
  enabled: boolean;
  supports_fetch: boolean;
  notes: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const apiClient = {
  getRegistrants: () => request<RegistrantSummary[]>("/registrants"),
  getRegistrant: (id: string) => request<RegistrantDetail>(`/registrants/${id}`),
  refreshAddress: (id: string) =>
    request<Address>(`/addresses/${id}/enrich`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }),
  getSources: () => request<SourceSummary[]>("/sources"),
  getIowaH3Map: (resolution = 10, init?: RequestInit) =>
    request<IowaH3Map>(`/spatial/iowa/h3?resolution=${resolution}`, init),
  ingestSource: (source: string) =>
    request(`/ingest/${source}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dry_run: true }),
    }),
};
