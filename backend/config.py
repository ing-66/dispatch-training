from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./dispatch_training.db"
    app_env: str = "development"
    cors_origins: str = "http://127.0.0.1:3100,http://localhost:3100"
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TRAINING_", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
