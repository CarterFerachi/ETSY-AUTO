from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    openai_api_key: str = os.environ["OPENAI_API_KEY"]
    recraft_api_key: str = os.getenv("RECRAFT_API_KEY", "")
    ideogram_api_key: str = os.getenv("IDEOGRAM_API_KEY", "")
    higgsfield_api_key: str = os.getenv("HIGGSFIELD_API_KEY", "")

    printify_api_key: str = os.getenv("PRINTIFY_API_KEY", "")
    printify_shop_id: str = os.getenv("PRINTIFY_SHOP_ID", "")
    printify_blueprint_id: int = int(os.getenv("PRINTIFY_BLUEPRINT_ID", "12"))   # 12 = Comfort Colors 1717
    printify_print_provider_id: int = int(os.getenv("PRINTIFY_PRINT_PROVIDER_ID", "99"))

    printful_api_key: str = os.getenv("PRINTFUL_API_KEY", "")
    printful_store_id: str = os.getenv("PRINTFUL_STORE_ID", "18378139")
    imgbb_api_key: str = os.getenv("IMGBB_API_KEY", "")

    etsy_api_key: str = os.getenv("ETSY_API_KEY", "")
    etsy_api_secret: str = os.getenv("ETSY_API_SECRET", "")
    etsy_access_token: str = os.getenv("ETSY_ACCESS_TOKEN", "")
    etsy_refresh_token: str = os.getenv("ETSY_REFRESH_TOKEN", "")
    etsy_shop_id: str = os.getenv("ETSY_SHOP_ID", "")
    etsy_webhook_secret: str = os.getenv("ETSY_WEBHOOK_SECRET", "")

    base_price_usd: float = float(os.getenv("BASE_PRICE_USD", "29.99"))
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    discord_bot_token: str = os.getenv("DISCORD_BOT_TOKEN", "")
    discord_approval_channel_id: int = int(os.getenv("DISCORD_APPROVAL_CHANNEL_ID", "0"))
    discord_owner_id: str = os.getenv("DISCORD_OWNER_ID", "")  # Your Discord user ID
    approval_timeout_seconds: int = int(os.getenv("APPROVAL_TIMEOUT_SECONDS", "300"))
    webhook_host: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    webhook_port: int = int(os.getenv("WEBHOOK_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
