from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    openai_api_key: str = os.environ["OPENAI_API_KEY"]

    printify_api_key: str = os.environ["PRINTIFY_API_KEY"]
    printify_shop_id: str = os.environ["PRINTIFY_SHOP_ID"]
    printify_blueprint_id: int = int(os.getenv("PRINTIFY_BLUEPRINT_ID", "5"))
    printify_print_provider_id: int = int(os.getenv("PRINTIFY_PRINT_PROVIDER_ID", "99"))

    etsy_api_key: str = os.getenv("ETSY_API_KEY", "")
    etsy_access_token: str = os.getenv("ETSY_ACCESS_TOKEN", "")
    etsy_refresh_token: str = os.getenv("ETSY_REFRESH_TOKEN", "")
    etsy_shop_id: str = os.getenv("ETSY_SHOP_ID", "")
    etsy_webhook_secret: str = os.getenv("ETSY_WEBHOOK_SECRET", "")

    base_price_usd: float = float(os.getenv("BASE_PRICE_USD", "24.99"))
    webhook_host: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    webhook_port: int = int(os.getenv("WEBHOOK_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
