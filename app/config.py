from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = ""

    # Paths
    assets_dir: Path = Path("assets")
    templates_dir: Path = Path("assets/templates")
    fonts_dir: Path = Path("assets/fonts")
    output_dir: Path = Path("assets/output")

    # Renderer
    renderer_backend: str = "cairosvg"

    def ensure_dirs(self) -> None:
        for d in (self.templates_dir, self.fonts_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
