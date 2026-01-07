"""
Debug script to see what HTML is being extracted
"""
import asyncio
import logging
from pathlib import Path
from app.scraper.divar_scraper import DivarScraper
from app.database import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_scraper():
    """Debug scraping to see HTML content"""
    
    test_url = "https://divar.ir/v/املاک-رهن-و-اجاره/آپارتمان/خ-شهید-بهشتی-24/QadxGfsx"
    
    async for db in get_db():
        try:
            scraper = DivarScraper(db_session=db, proxy_enabled=False)
            await scraper.initialize()
            
            logger.info(f"Navigating to: {test_url}")
            await scraper.page.goto(test_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            # Scroll
            await scraper._simulate_scroll()
            await asyncio.sleep(2)
            
            # Click show all details
            clicked = await scraper._click_show_all_details()
            logger.info(f"'Show all details' button clicked: {clicked}")
            await asyncio.sleep(2)
            
            # Get HTML content
            content = await scraper.page.content()
            
            # Save to file
            debug_file = Path("/app/debug_page.html")
            debug_file.write_text(content, encoding='utf-8')
            logger.info(f"HTML saved to: {debug_file}")
            logger.info(f"HTML size: {len(content)} bytes")
            
            # Take screenshot
            await scraper.page.screenshot(path="/app/debug_screenshot.png", full_page=True)
            logger.info("Screenshot saved to: /app/debug_screenshot.png")
            
            # Check for specific elements
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'lxml')
            
            logger.info("\n=== DEBUG INFO ===")
            title = soup.select_one('h1')
            logger.info(f"H1 title: {title.get_text(strip=True) if title else 'NOT FOUND'}")
            
            rows = soup.select('.kt-base-row, .kt-group-row-item, .kt-unexpandable-row')
            logger.info(f"Info rows found: {len(rows)}")
            
            for i, row in enumerate(rows[:5], 1):
                logger.info(f"  Row {i}: {row.get_text(strip=True)[:100]}")
            
            desc = soup.select_one('.kt-description-row__text')
            logger.info(f"Description: {desc.get_text(strip=True)[:100] if desc else 'NOT FOUND'}")
            
            await scraper.close()
            
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
        
        break

if __name__ == "__main__":
    asyncio.run(debug_scraper())
