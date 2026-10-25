from functools import lru_cache

from pydantic import field_validator

from memorial_common.config import CommonSettings

DARAJA_HOSTS = {"sandbox": "https://sandbox.safaricom.co.ke", "production": "https://api.safaricom.co.ke"}


class Settings(CommonSettings):
    service_name: str = "contributions"

    mpesa_enabled: bool = False
    mpesa_env: str = "sandbox"
    mpesa_consumer_key: str = ""
    mpesa_consumer_secret: str = ""
    mpesa_shortcode: str = ""
    mpesa_passkey: str = ""
    # CustomerPayBillOnline for a Paybill, CustomerBuyGoodsOnline for a Till.
    mpesa_transaction_type: str = "CustomerPayBillOnline"
    # For a Till, the till number goes here; for a Paybill leave empty (uses the shortcode).
    mpesa_party_b: str = ""
    mpesa_account_reference: str = "MarthaOngosi"
    # Secret path segment Safaricom calls back on. Long and random.
    mpesa_callback_token: str = ""
    # Optional comma-separated list of Safaricom callback source IPs.
    mpesa_callback_allowed_ips: str = ""

    min_amount: int = 10
    max_amount: int = 250_000
    pending_timeout_minutes: int = 15
    phone_hash_pepper: str = "change-me"

    public_show_amounts: bool = False
    display_paybill: str = ""
    display_account: str = ""

    @field_validator("mpesa_env")
    @classmethod
    def _env(cls, v: str) -> str:
        if v not in DARAJA_HOSTS:
            raise ValueError("MPESA_ENV must be 'sandbox' or 'production'")
        return v

    @property
    def daraja_base(self) -> str:
        return DARAJA_HOSTS[self.mpesa_env]

    @property
    def callback_url(self) -> str:
        return f"{self.site_origin}/api/contributions/mpesa/callback/{self.mpesa_callback_token}"

    @property
    def allowed_ips(self) -> set[str]:
        return {ip.strip() for ip in self.mpesa_callback_allowed_ips.split(",") if ip.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
