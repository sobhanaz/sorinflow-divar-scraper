"""
SorinFlow Divar Scraper - Main Scraper Module
Handles scraping property listings from Divar.ir
"""
import asyncio
import random
import re
import os
import hashlib
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from bs4 import BeautifulSoup
import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.config import get_settings, CITIES, CATEGORIES
from app.models.property import Property, City, Category
from app.models.scraping_job import ScrapingJob, ScrapingLog
from app.models.proxy import Proxy
from app.scraper.stealth import StealthConfig, STEALTH_JS, get_browser_args, get_context_options
from app.scraper.auth import DivarAuth

settings = get_settings()


class DivarScraper:
    """Main scraper class for Divar.ir real estate listings"""
    
    BASE_URL = "https://divar.ir"
    
    def __init__(
        self,
        db_session: AsyncSession,
        proxy_enabled: bool = False,
        headless: bool = True
    ):
        self.db_session = db_session
        self.proxy_enabled = proxy_enabled
        self.headless = headless
        self.stealth_config = StealthConfig()
        self.auth = DivarAuth(db_session)
        
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        self.images_dir = Path(settings.images_path)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_job: Optional[ScrapingJob] = None
        self.request_count = 0
        self.session_start = datetime.now()
    
    async def initialize(self, restore_session: bool = True) -> bool:
        """Initialize scraper with browser and optional session restoration"""
        try:
            self.playwright = await async_playwright().start()
            
            # Get proxy if enabled
            proxy = None
            if self.proxy_enabled:
                proxy = await self._get_working_proxy()
            
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=get_browser_args()
            )
            
            context_options = get_context_options(self.stealth_config, proxy)
            self.context = await self.browser.new_context(**context_options)
            
            # Add stealth script
            await self.context.add_init_script(STEALTH_JS)
            
            self.page = await self.context.new_page()
            
            # Restore authentication session
            if restore_session:
                phone_number = settings.divar_phone_number
                if phone_number:
                    self.auth.context = self.context
                    self.auth.page = self.page
                    self.auth.browser = self.browser
                    
                    restored = await self.auth.restore_session(phone_number)
                    if not restored:
                        logger.warning("Session not restored. Some features may require login.")
                        return False
                    logger.info("Session restored successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize scraper: {e}")
            return False
    
    async def close(self):
        """Close browser and cleanup resources"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("Scraper closed successfully")
        except Exception as e:
            logger.error(f"Error closing scraper: {e}")
    
    async def _get_working_proxy(self) -> Optional[str]:
        """Get a working proxy from the database"""
        try:
            result = await self.db_session.execute(
                select(Proxy).where(
                    and_(Proxy.is_active == True, Proxy.is_working == True)
                ).order_by(Proxy.success_count.desc()).limit(1)
            )
            proxy = result.scalar_one_or_none()
            if proxy:
                return proxy.url
            return None
        except Exception as e:
            logger.error(f"Failed to get proxy: {e}")
            return None
    
    async def _human_like_delay(self, min_delay: float = None, max_delay: float = None):
        """Add human-like random delay"""
        min_d = min_delay or self.stealth_config.min_delay
        max_d = max_delay or self.stealth_config.max_delay
        delay = random.uniform(min_d, max_d)
        await asyncio.sleep(delay)
    
    async def _simulate_scroll(self):
        """Simulate human-like scrolling"""
        try:
            for _ in range(self.stealth_config.scroll_steps):
                scroll_distance = self.stealth_config.get_random_scroll_distance()
                await self.page.evaluate(f"window.scrollBy(0, {scroll_distance})")
                await asyncio.sleep(self.stealth_config.scroll_delay)
        except Exception as e:
            logger.warning(f"Scroll simulation failed: {e}")
    
    async def _mouse_movement(self):
        """Simulate random mouse movements"""
        try:
            viewport = self.stealth_config.get_viewport()
            for _ in range(random.randint(2, 5)):
                x = random.randint(100, viewport["width"] - 100)
                y = random.randint(100, viewport["height"] - 100)
                await self.page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception as e:
            logger.warning(f"Mouse movement simulation failed: {e}")
    
    def _generate_tag_number(self) -> str:
        """Generate unique tag number for property"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = uuid.uuid4().hex[:6].upper()
        return f"SF-{timestamp}-{random_suffix}"
    
    def _extract_divar_id(self, url: str) -> Optional[str]:
        """Extract Divar listing ID from URL"""
        try:
            parts = url.rstrip('/').split('/')
            return parts[-1] if parts else None
        except:
            return None
    
    def _parse_persian_number(self, text: str) -> Optional[int]:
        """Convert Persian numbers to integer"""
        if not text:
            return None
        
        persian_digits = '۰۱۲۳۴۵۶۷۸۹'
        english_digits = '0123456789'
        
        translation_table = str.maketrans(persian_digits, english_digits)
        text = text.translate(translation_table)
        text = re.sub(r'[^\d]', '', text)
        
        try:
            return int(text) if text else None
        except ValueError:
            return None
    
    async def _check_rate_limit(self):
        """Check and enforce rate limiting"""
        self.request_count += 1
        
        # Check requests per minute
        elapsed = (datetime.now() - self.session_start).total_seconds()
        if elapsed > 0:
            rpm = (self.request_count / elapsed) * 60
            if rpm > self.stealth_config.max_requests_per_minute:
                wait_time = 60 - (elapsed % 60)
                logger.info(f"Rate limit reached. Waiting {wait_time:.1f} seconds...")
                await asyncio.sleep(wait_time)
        
        # Check requests per session
        if self.request_count >= self.stealth_config.max_requests_per_session:
            logger.info("Session request limit reached. Restarting browser...")
            await self.close()
            await asyncio.sleep(10)
            await self.initialize()
            self.request_count = 0
            self.session_start = datetime.now()
    
    async def scrape_listing_page(
        self,
        city: str,
        category: str,
        page_num: int = 1
    ) -> List[Dict[str, Any]]:
        """Scrape a listing page to get property cards"""
        listings = []
        
        try:
            url = f"{self.BASE_URL}/s/{city}/{category}"
            if page_num > 1:
                url += f"?page={page_num}"
            
            logger.info(f"Scraping listing page: {url}")
            
            await self._check_rate_limit()
            await self.page.goto(url, wait_until="networkidle", timeout=settings.scraper_timeout)
            await self._human_like_delay(2, 4)
            await self._simulate_scroll()
            
            # Wait for listings to load
            await self.page.wait_for_selector('a.kt-post-card__action', timeout=10000)
            
            # Get page content
            content = await self.page.content()
            soup = BeautifulSoup(content, 'lxml')
            
            # Find all property cards
            cards = soup.select('a.kt-post-card__action')
            
            for card in cards:
                try:
                    listing = self._parse_listing_card(card)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"Failed to parse listing card: {e}")
            
            logger.info(f"Found {len(listings)} listings on page {page_num}")
            
        except Exception as e:
            logger.error(f"Failed to scrape listing page: {e}")
        
        return listings
    
    def _parse_listing_card(self, card) -> Optional[Dict[str, Any]]:
        """Parse a listing card element"""
        try:
            href = card.get('href', '')
            if not href:
                return None
            
            url = urljoin(self.BASE_URL, href)
            divar_id = self._extract_divar_id(url)
            
            # Extract basic info
            title_elem = card.select_one('.kt-post-card__title')
            title = title_elem.get_text(strip=True) if title_elem else None
            
            # Extract descriptions (price, rooms, area)
            descriptions = card.select('.kt-post-card__description')
            desc_texts = [d.get_text(strip=True) for d in descriptions]
            
            # Extract thumbnail
            img_elem = card.select_one('.kt-image-block__image')
            thumbnail_url = img_elem.get('src') if img_elem else None
            
            # Extract bottom info
            bottom_desc = card.select_one('.kt-post-card__bottom-description')
            category_hint = bottom_desc.get_text(strip=True) if bottom_desc else None
            
            return {
                "url": url,
                "divar_id": divar_id,
                "title": title,
                "descriptions": desc_texts,
                "thumbnail_url": thumbnail_url,
                "category_hint": category_hint
            }
            
        except Exception as e:
            logger.warning(f"Failed to parse card: {e}")
            return None
    
    async def scrape_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape detailed information from a property page"""
        try:
            logger.info(f"Scraping property detail: {url}")
            
            await self._check_rate_limit()
            await self.page.goto(url, wait_until="networkidle", timeout=settings.scraper_timeout)
            await self._human_like_delay(2, 4)
            await self._mouse_movement()
            await self._simulate_scroll()
            
            # Get page content
            content = await self.page.content()
            soup = BeautifulSoup(content, 'lxml')
            
            property_data = {
                "url": url,
                "divar_id": self._extract_divar_id(url),
                "scraped_at": datetime.now().isoformat()
            }
            
            # Extract title
            title_elem = soup.select_one('h1.kt-page-title__title')
            if title_elem:
                property_data["title"] = title_elem.get_text(strip=True)
            
            # Extract description
            desc_elem = soup.select_one('.kt-description-row__text')
            if desc_elem:
                property_data["description"] = desc_elem.get_text(strip=True)
            
            # Extract price info
            property_data.update(self._extract_price_info(soup))
            
            # Extract property details
            property_data.update(self._extract_property_details(soup))
            
            # Extract location
            property_data.update(self._extract_location(soup))
            
            # Extract amenities/features
            property_data["features"] = self._extract_features(soup)
            property_data["amenities"] = self._extract_amenities(soup)
            
            # Extract images
            property_data["images"] = self._extract_images(soup)
            
            # Get phone number (requires login)
            phone_number = await self._get_phone_number()
            if phone_number:
                property_data["phone_number"] = phone_number
            
            return property_data
            
        except Exception as e:
            logger.error(f"Failed to scrape property detail: {e}")
            return None
    
    def _extract_price_info(self, soup) -> Dict[str, Any]:
        """Extract price information from property page"""
        price_info = {}
        
        try:
            # Look for price rows
            rows = soup.select('.kt-base-row')
            
            for row in rows:
                title = row.select_one('.kt-base-row__title, .kt-unexpandable-row__title')
                value = row.select_one('.kt-unexpandable-row__value, .kt-base-row__end')
                
                if not title or not value:
                    continue
                
                title_text = title.get_text(strip=True)
                value_text = value.get_text(strip=True)
                
                if 'قیمت کل' in title_text or 'قیمت' in title_text:
                    price_info['total_price'] = self._parse_persian_number(value_text)
                elif 'قیمت هر متر' in title_text:
                    price_info['price_per_meter'] = self._parse_persian_number(value_text)
                elif 'اجاره' in title_text or 'اجارهٔ ماهانه' in title_text:
                    price_info['rent_price'] = self._parse_persian_number(value_text)
                elif 'ودیعه' in title_text or 'رهن' in title_text:
                    price_info['deposit'] = self._parse_persian_number(value_text)
            
        except Exception as e:
            logger.warning(f"Failed to extract price info: {e}")
        
        return price_info
    
    def _extract_property_details(self, soup) -> Dict[str, Any]:
        """Extract property details like area, rooms, floor, etc."""
        details = {}
        
        try:
            # Look for info table/rows
            info_rows = soup.select('.kt-group-row-item, .kt-base-row')
            
            for row in info_rows:
                title = row.select_one('.kt-group-row-item__title, .kt-base-row__title')
                value = row.select_one('.kt-group-row-item__value, .kt-base-row__end')
                
                if not title or not value:
                    continue
                
                title_text = title.get_text(strip=True)
                value_text = value.get_text(strip=True)
                
                if 'متراژ' in title_text:
                    details['area'] = self._parse_persian_number(value_text)
                elif 'اتاق' in title_text:
                    rooms = self._parse_persian_number(value_text)
                    if rooms is None and 'بدون اتاق' in value_text:
                        rooms = 0
                    details['rooms'] = rooms
                elif 'ساخت' in title_text or 'سال' in title_text:
                    details['year_built'] = self._parse_persian_number(value_text)
                elif 'طبقه' in title_text:
                    if 'از' in value_text:
                        parts = value_text.split('از')
                        details['floor'] = self._parse_persian_number(parts[0])
                        details['total_floors'] = self._parse_persian_number(parts[1])
                    else:
                        details['floor'] = self._parse_persian_number(value_text)
                elif 'آسانسور' in title_text:
                    details['has_elevator'] = 'دارد' in value_text
                elif 'پارکینگ' in title_text:
                    details['has_parking'] = 'دارد' in value_text
                elif 'انباری' in title_text:
                    details['has_storage'] = 'دارد' in value_text
                elif 'بالکن' in title_text:
                    details['has_balcony'] = 'دارد' in value_text
                elif 'جهت ساختمان' in title_text:
                    details['building_direction'] = value_text
                elif 'وضعیت واحد' in title_text:
                    details['unit_status'] = value_text
                elif 'سند' in title_text:
                    details['document_type'] = value_text
        
        except Exception as e:
            logger.warning(f"Failed to extract property details: {e}")
        
        return details
    
    def _extract_location(self, soup) -> Dict[str, Any]:
        """Extract location information"""
        location = {}
        
        try:
            # Look for breadcrumb or location info
            breadcrumb = soup.select('.kt-page-title__subtitle a, .kt-breadcrumb a')
            if breadcrumb:
                locations = [b.get_text(strip=True) for b in breadcrumb]
                if len(locations) >= 1:
                    location['city_name'] = locations[0]
                if len(locations) >= 2:
                    location['district'] = locations[1]
                if len(locations) >= 3:
                    location['neighborhood'] = locations[2]
            
            # Look for map coordinates
            map_elem = soup.select_one('[data-lat][data-lng]')
            if map_elem:
                location['latitude'] = float(map_elem.get('data-lat', 0))
                location['longitude'] = float(map_elem.get('data-lng', 0))
            
            # Look for address
            address_elem = soup.select_one('.kt-unexpandable-row__value a[href^="geo:"]')
            if address_elem:
                location['address'] = address_elem.get_text(strip=True)
        
        except Exception as e:
            logger.warning(f"Failed to extract location: {e}")
        
        return location
    
    def _extract_features(self, soup) -> List[str]:
        """Extract property features"""
        features = []
        
        try:
            feature_elems = soup.select('.kt-chip, .kt-group-row-item--feature')
            for elem in feature_elems:
                text = elem.get_text(strip=True)
                if text and text not in features:
                    features.append(text)
        except Exception as e:
            logger.warning(f"Failed to extract features: {e}")
        
        return features
    
    def _extract_amenities(self, soup) -> List[str]:
        """Extract property amenities"""
        amenities = []
        
        try:
            amenity_section = soup.select_one('.kt-base-row__title:contains("امکانات")')
            if amenity_section:
                parent = amenity_section.find_parent()
                if parent:
                    chips = parent.select('.kt-chip')
                    amenities = [c.get_text(strip=True) for c in chips]
        except Exception as e:
            logger.warning(f"Failed to extract amenities: {e}")
        
        return amenities
    
    def _extract_images(self, soup) -> List[str]:
        """Extract all image URLs from property page"""
        images = []
        
        try:
            img_elems = soup.select('.kt-image-block__image, .post-image img, picture img')
            for img in img_elems:
                src = img.get('src') or img.get('data-src')
                if src and 'divarcdn.com' in src and src not in images:
                    # Get higher resolution version
                    src = src.replace('thumbnail', 'main').replace('webp_thumbnail', 'webp')
                    images.append(src)
        except Exception as e:
            logger.warning(f"Failed to extract images: {e}")
        
        return images
    
    async def _get_phone_number(self) -> Optional[str]:
        """Click contact button and extract phone number"""
        try:
            # Look for contact button
            contact_button = await self.page.query_selector('button:has-text("اطلاعات تماس")')
            
            if contact_button:
                await self._human_like_delay(0.5, 1)
                await contact_button.click()
                await asyncio.sleep(2)
                
                # Wait for phone number to appear
                phone_elem = await self.page.wait_for_selector('a[href^="tel:"]', timeout=5000)
                
                if phone_elem:
                    phone_text = await phone_elem.inner_text()
                    # Convert Persian numbers
                    phone = self._parse_persian_number(phone_text)
                    if phone:
                        return f"0{phone}" if not str(phone).startswith('0') else str(phone)
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get phone number: {e}")
            return None
    
    async def download_images(
        self,
        images: List[str],
        divar_id: str
    ) -> List[str]:
        """Download images and return local paths"""
        local_paths = []
        
        try:
            property_dir = self.images_dir / divar_id
            property_dir.mkdir(parents=True, exist_ok=True)
            
            async with httpx.AsyncClient() as client:
                for i, url in enumerate(images):
                    try:
                        response = await client.get(url, timeout=30)
                        if response.status_code == 200:
                            # Generate filename
                            ext = 'webp' if 'webp' in url else 'jpg'
                            filename = f"img_{i+1}.{ext}"
                            filepath = property_dir / filename
                            
                            with open(filepath, 'wb') as f:
                                f.write(response.content)
                            
                            local_paths.append(str(filepath))
                            logger.debug(f"Downloaded image: {filename}")
                            
                            await asyncio.sleep(0.5)  # Rate limit downloads
                    except Exception as e:
                        logger.warning(f"Failed to download image {i+1}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to download images: {e}")
        
        return local_paths
    
    async def property_exists(self, divar_id: str) -> bool:
        """Check if property already exists in database"""
        try:
            result = await self.db_session.execute(
                select(Property).where(Property.divar_id == divar_id)
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Failed to check property existence: {e}")
            return False
    
    async def save_property(self, property_data: Dict[str, Any]) -> Optional[Property]:
        """Save property to database"""
        try:
            divar_id = property_data.get('divar_id')
            
            # Check if exists
            result = await self.db_session.execute(
                select(Property).where(Property.divar_id == divar_id)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing
                for key, value in property_data.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
                existing.updated_at = datetime.now()
                await self.db_session.commit()
                logger.info(f"Updated property: {divar_id}")
                return existing
            else:
                # Create new
                property_data['tag_number'] = self._generate_tag_number()
                property_data['scraped_at'] = datetime.now()
                
                # Remove non-model fields
                property_data.pop('descriptions', None)
                property_data.pop('category_hint', None)
                
                new_property = Property(**property_data)
                self.db_session.add(new_property)
                await self.db_session.commit()
                logger.info(f"Saved new property: {divar_id} with tag {property_data['tag_number']}")
                return new_property
                
        except Exception as e:
            logger.error(f"Failed to save property: {e}")
            await self.db_session.rollback()
            return None
    
    async def start_scraping_job(
        self,
        city: str,
        category: str,
        max_pages: int = 10,
        download_images: bool = True
    ) -> ScrapingJob:
        """Start a complete scraping job for a city and category"""
        
        # Create job record
        job = ScrapingJob(
            status="running",
            started_at=datetime.now()
        )
        
        # Get city and category IDs
        city_result = await self.db_session.execute(
            select(City).where(City.slug == city)
        )
        city_obj = city_result.scalar_one_or_none()
        if city_obj:
            job.city_id = city_obj.id
        
        cat_result = await self.db_session.execute(
            select(Category).where(Category.slug == category)
        )
        cat_obj = cat_result.scalar_one_or_none()
        if cat_obj:
            job.category_id = cat_obj.id
        
        self.db_session.add(job)
        await self.db_session.commit()
        self.current_job = job
        
        try:
            logger.info(f"Starting scraping job for {city}/{category}")
            
            # Scrape listing pages
            all_listings = []
            for page_num in range(1, max_pages + 1):
                listings = await self.scrape_listing_page(city, category, page_num)
                
                if not listings:
                    logger.info(f"No more listings found at page {page_num}")
                    break
                
                all_listings.extend(listings)
                job.scraped_pages = page_num
                job.total_items = len(all_listings)
                await self.db_session.commit()
                
                await self._human_like_delay()
            
            logger.info(f"Found {len(all_listings)} total listings")
            
            # Scrape each property detail
            for i, listing in enumerate(all_listings):
                try:
                    # Check if already scraped
                    if await self.property_exists(listing['divar_id']):
                        logger.info(f"Property already exists: {listing['divar_id']}")
                        job.updated_items += 1
                        continue
                    
                    # Scrape detail page
                    detail = await self.scrape_property_detail(listing['url'])
                    
                    if detail:
                        # Merge with listing data
                        property_data = {**listing, **detail}
                        property_data['city_name'] = CITIES.get(city, {}).get('name', city)
                        property_data['category_name'] = CATEGORIES.get(category, {}).get('name', category)
                        property_data['listing_type'] = CATEGORIES.get(category, {}).get('type', 'unknown')
                        
                        # Download images if enabled
                        if download_images and property_data.get('images'):
                            local_images = await self.download_images(
                                property_data['images'],
                                property_data['divar_id']
                            )
                            if local_images:
                                property_data['images_downloaded'] = True
                        
                        # Save to database
                        saved = await self.save_property(property_data)
                        if saved:
                            job.new_items += 1
                        else:
                            job.failed_items += 1
                    else:
                        job.failed_items += 1
                    
                    job.scraped_items = i + 1
                    await self.db_session.commit()
                    
                    await self._human_like_delay()
                    
                except Exception as e:
                    logger.error(f"Failed to process listing: {e}")
                    job.failed_items += 1
                    await self.db_session.commit()
            
            # Complete job
            job.status = "completed"
            job.completed_at = datetime.now()
            await self.db_session.commit()
            
            logger.info(f"Scraping job completed. New: {job.new_items}, Updated: {job.updated_items}, Failed: {job.failed_items}")
            
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.now()
            await self.db_session.commit()
            logger.error(f"Scraping job failed: {e}")
        
        return job
    
    async def scrape_all_categories(
        self,
        city: str,
        categories: List[str] = None,
        max_pages: int = 10,
        download_images: bool = True
    ) -> List[ScrapingJob]:
        """Scrape all categories for a city"""
        
        if categories is None:
            categories = list(CATEGORIES.keys())
        
        jobs = []
        
        for category in categories:
            try:
                job = await self.start_scraping_job(
                    city=city,
                    category=category,
                    max_pages=max_pages,
                    download_images=download_images
                )
                jobs.append(job)
                
                # Longer delay between categories
                await asyncio.sleep(random.uniform(10, 20))
                
            except Exception as e:
                logger.error(f"Failed to scrape category {category}: {e}")
        
        return jobs
