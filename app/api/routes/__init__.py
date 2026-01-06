"""
SorinFlow Divar Scraper - API Routes
"""
from fastapi import APIRouter
from app.api.routes import properties, scraper, auth, stats, proxies

router = APIRouter()

# Include all route modules
router.include_router(properties.router, prefix="/properties", tags=["Properties"])
router.include_router(scraper.router, prefix="/scraper", tags=["Scraper"])
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
router.include_router(stats.router, prefix="/stats", tags=["Statistics"])
router.include_router(proxies.router, prefix="/proxies", tags=["Proxies"])
