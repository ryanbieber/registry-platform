from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg://registry:registry@localhost:5432/registry"
    raw_payload_bucket: str = "local-audit-store"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    census_geocoder_url: str = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
    census_enrichment_ttl_days: int = 365
    census_error_ttl_days: int = 7
    fbi_api_base_url: str = "https://api.usa.gov/crime/fbi/ucr"
    fbi_api_key: str = "DEMO_KEY"
    fbi_enrichment_ttl_days: int = 30
    fbi_error_ttl_days: int = 7

    @property
    def fbi_state_estimates_url_template(self) -> str:
        return f"{self.fbi_api_base_url}/estimates/states/{{state_abbr}}"

    @property
    def fbi_state_geo_url_template(self) -> str:
        return f"{self.fbi_api_base_url}/geo/states/{{state_abbr}}"

    @property
    def fbi_state_context_url_template(self) -> str:
        return f"{self.fbi_api_base_url}/geo/states/{{state_abbr}}"


settings = Settings()
