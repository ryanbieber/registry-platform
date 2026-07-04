from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg://registry:registry@localhost:5432/registry"
    raw_payload_bucket: str = "local-audit-store"
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
