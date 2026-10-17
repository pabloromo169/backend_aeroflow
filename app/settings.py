from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongodb_uri: str = "mongodb://mongodb.monolith.dynamic-dns.net:443/?tls=true&authSource=admin"
    mongodb_username: str | None = None
    mongodb_password: str | None = None
    mongodb_database: str = "aeroflow"
    kafka_bootstrap_servers: str = "kafka.monolith.dynamic-dns.net:443"
    kafka_security_protocol: str = "SSL"
    kafka_ssl_ca_location: str | None = None
    kafka_flights_topic: str = "aeroflow.vuelos"
    kafka_configuration_topic: str = "aeroflow.configuracion"
    kafka_delivery_timeout_seconds: int = 30
    kafka_retries: int = 3
    kafka_producer_pool_size: int = 5
    cors_origins: str = "*"

    @property
    def allowed_origins(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
