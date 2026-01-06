"""
SorinFlow Divar Scraper - Application Configuration
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # App Info
    app_name: str = "SorinFlow Divar Scraper"
    app_version: str = "1.0.0"
    environment: str = Field(default="production", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Server
    server_ip: str = Field(default="171.22.182.91", env="SERVER_IP")
    domain: str = Field(default="scc.sorinflow.com", env="DOMAIN")
    domain_dns_only: str = Field(default="sc.sorinflow.com", env="DOMAIN_DNS_ONLY")
    
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://sorinflow:sorinflow_secret_2024@db:5432/divar_scraper",
        env="DATABASE_URL"
    )
    
    # Redis
    redis_url: str = Field(
        default="redis://:redis_secret_2024@redis:6379/0",
        env="REDIS_URL"
    )
    
    # Security
    secret_key: str = Field(
        default="your-super-secret-key-change-in-production",
        env="SECRET_KEY"
    )
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    
    # Scraper Settings
    scraper_headless: bool = Field(default=True, env="SCRAPER_HEADLESS")
    scraper_timeout: int = Field(default=60000, env="SCRAPER_TIMEOUT")
    scraper_delay_min: float = Field(default=2.0, env="SCRAPER_DELAY_MIN")
    scraper_delay_max: float = Field(default=5.0, env="SCRAPER_DELAY_MAX")
    
    # Proxy Settings
    proxy_enabled: bool = Field(default=False, env="PROXY_ENABLED")
    proxy_list: str = Field(default="", env="PROXY_LIST")
    
    # Divar Login
    divar_phone_number: str = Field(default="", env="DIVAR_PHONE_NUMBER")
    
    # Paths
    cookies_path: str = "/app/data/cookies"
    images_path: str = "/app/data/images"
    logs_path: str = "/app/logs"
    
    # Divar URLs
    divar_base_url: str = "https://divar.ir"
    divar_login_url: str = "https://divar.ir/my-divar/my-posts"
    
    # Cities Configuration
    default_city: str = "urmia"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables
    
    @property
    def proxy_servers(self) -> List[str]:
        """Parse proxy list into individual proxies"""
        if not self.proxy_list:
            return []
        return [p.strip() for p in self.proxy_list.split(",") if p.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# City slugs mapping
CITIES = {
    "urmia": {"name": "ارومیه", "province": "آذربایجان غربی"},
    "tehran": {"name": "تهران", "province": "تهران"},
    "tabriz": {"name": "تبریز", "province": "آذربایجان شرقی"},
    "isfahan": {"name": "اصفهان", "province": "اصفهان"},
    "shiraz": {"name": "شیراز", "province": "فارس"},
    "mashhad": {"name": "مشهد", "province": "خراسان رضوی"},
    "karaj": {"name": "کرج", "province": "البرز"},
    "ahvaz": {"name": "اهواز", "province": "خوزستان"},
    "qom": {"name": "قم", "province": "قم"},
    "kermanshah": {"name": "کرمانشاه", "province": "کرمانشاه"},
    "rasht": {"name": "رشت", "province": "گیلان"},
    "kerman": {"name": "کرمان", "province": "کرمان"},
    "sari": {"name": "ساری", "province": "مازندران"},
    "yazd": {"name": "یزد", "province": "یزد"},
    "ardabil": {"name": "اردبیل", "province": "اردبیل"},
    "bandar-abbas": {"name": "بندرعباس", "province": "هرمزگان"},
    "zanjan": {"name": "زنجان", "province": "زنجان"},
    "sanandaj": {"name": "سنندج", "province": "کردستان"},
    "hamadan": {"name": "همدان", "province": "همدان"},
    "gorgan": {"name": "گرگان", "province": "گلستان"},
}

# Categories configuration
CATEGORIES = {
    "buy-residential": {"name": "خرید مسکونی", "type": "buy"},
    "buy-apartment": {"name": "خرید آپارتمان", "type": "buy"},
    "buy-villa": {"name": "خرید ویلا", "type": "buy"},
    "buy-old-house": {"name": "خرید خانه کلنگی", "type": "buy"},
    "rent-residential": {"name": "اجاره مسکونی", "type": "rent"},
    "rent-apartment": {"name": "اجاره آپارتمان", "type": "rent"},
    "rent-villa": {"name": "اجاره ویلا", "type": "rent"},
    "buy-commercial-property": {"name": "خرید اداری و تجاری", "type": "buy"},
    "buy-office": {"name": "خرید دفتر کار", "type": "buy"},
    "buy-store": {"name": "خرید مغازه", "type": "buy"},
    "buy-industrial-agricultural-property": {"name": "خرید صنعتی و کشاورزی", "type": "buy"},
    "rent-commercial-property": {"name": "اجاره اداری و تجاری", "type": "rent"},
    "rent-office": {"name": "اجاره دفتر کار", "type": "rent"},
    "rent-store": {"name": "اجاره مغازه", "type": "rent"},
    "rent-industrial-agricultural-property": {"name": "اجاره صنعتی و کشاورزی", "type": "rent"},
    "rent-temporary": {"name": "اجاره کوتاه مدت", "type": "rent"},
    "real-estate-services": {"name": "خدمات املاک", "type": "service"},
}
