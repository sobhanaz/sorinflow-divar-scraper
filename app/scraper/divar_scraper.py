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
            
            # Use domcontentloaded for faster loading, then wait for content
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)  # Wait for JS to render
            await self._simulate_scroll()
            await asyncio.sleep(2)  # Wait after scroll
            
            # Wait for listings to load - try multiple selectors
            try:
                await self.page.wait_for_selector('a[href*="/v/"]', timeout=10000)
            except Exception:
                logger.warning("Primary selector not found, waiting more...")
                await asyncio.sleep(5)
            
            # Get page content
            content = await self.page.content()
            soup = BeautifulSoup(content, 'lxml')
            
            # Find all property cards - try multiple selectors
            cards = soup.select('a.kt-post-card__action')
            if not cards:
                cards = soup.select('div.post-card-item a')
            if not cards:
                cards = soup.select('article a[href*="/v/"]')
            if not cards:
                # Try finding any links to property pages
                cards = soup.select('a[href*="/v/"]')
            
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
            if not href or '/v/' not in href:
                return None
            
            url = urljoin(self.BASE_URL, href)
            divar_id = self._extract_divar_id(url)
            
            # Extract basic info - try multiple selectors
            title_elem = card.select_one('.kt-post-card__title, .post-title, h2, h3')
            title = title_elem.get_text(strip=True) if title_elem else None
            
            # Extract descriptions (price, rooms, area)
            descriptions = card.select('.kt-post-card__description, .post-description, span.description')
            desc_texts = [d.get_text(strip=True) for d in descriptions]
            
            # Extract thumbnail
            img_elem = card.select_one('.kt-image-block__image, img')
            thumbnail_url = img_elem.get('src') or img_elem.get('data-src') if img_elem else None
            
            # Extract bottom info
            bottom_desc = card.select_one('.kt-post-card__bottom-description, .post-location')
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
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await self._simulate_scroll()
            await asyncio.sleep(1)
            
            # Click "Show all details" button if it exists
            await self._click_show_all_details()
            
            # Get page content
            content = await self.page.content()
            soup = BeautifulSoup(content, 'lxml')
            
            property_data = {
                "url": url,
                "divar_id": self._extract_divar_id(url),
                "scraped_at": datetime.now()
            }
            
            # Extract title - try multiple selectors
            title_elem = soup.select_one('h1.kt-page-title__title, h1, .post-title')
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
            # Look for info table/rows - check both expanded and collapsed views
            info_rows = soup.select('.kt-group-row-item, .kt-base-row, .kt-unexpandable-row')
            
            for row in info_rows:
                title = row.select_one('.kt-group-row-item__title, .kt-base-row__title, .kt-unexpandable-row__title')
                value = row.select_one('.kt-group-row-item__value, .kt-base-row__end, .kt-unexpandable-row__value')
                
                if not title or not value:
                    continue
                
                title_text = title.get_text(strip=True)
                value_text = value.get_text(strip=True)
                
                # Building/land measurements
                if 'متراژ زمین' in title_text:
                    details['land_area'] = self._parse_persian_number(value_text)
                elif 'متراژ' in title_text and 'زمین' not in title_text:
                    details['area'] = self._parse_persian_number(value_text)
                elif 'زیربنا' in title_text:
                    details['built_area'] = self._parse_persian_number(value_text)
                
                # Building specs
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
                
                # Amenities
                elif 'آسانسور' in title_text:
                    details['has_elevator'] = 'دارد' in value_text
                elif 'پارکینگ' in title_text:
                    details['has_parking'] = 'دارد' in value_text
                elif 'انباری' in title_text:
                    details['has_storage'] = 'دارد' in value_text
                elif 'بالکن' in title_text:
                    details['has_balcony'] = 'دارد' in value_text
                
                # Building info
                elif 'جهت' in title_text:
                    details['building_direction'] = value_text
                elif 'بر' in title_text and 'متر' in value_text:
                    details['frontage'] = self._parse_persian_number(value_text)
                elif 'وضعیت' in title_text:
                    details['unit_status'] = value_text
                elif 'سند' in title_text:
                    details['document_type'] = value_text
                elif 'نوع کاربری' in title_text:
                    details['usage_type'] = value_text
                elif 'سن بنا' in title_text:
                    details['building_age'] = value_text
                elif 'نوع ملک' in title_text:
                    details['property_type'] = value_text
        
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
        """Extract property features (NOT navigation breadcrumbs)"""
        features = []
        
        try:
            # Only extract features from feature sections, NOT from navigation/search chips
            # Feature rows are inside property details section
            feature_elems = soup.select('.kt-group-row-item__value, .kt-feature-row__title')
            for elem in feature_elems:
                text = elem.get_text(strip=True)
                if text and text not in features:
                    features.append(text)
            
            # Also check for feature icons with text
            icon_features = soup.select('.kt-group-row-item .kt-body--stable')
            for elem in icon_features:
                text = elem.get_text(strip=True)
                # Filter out common non-property categories from navigation
                unwanted_keywords = [
                    'خودرو', 'موبایل', 'تلویزیون', 'کالای دیجیتال',
                    'وسایل شخصی', 'خدمات', 'استخدام', 'حیوانات',
                    'صندلی', 'نیمکت', 'اسباب', 'گوشی', 'لامپ',
                    'پرنده', 'عروس', 'یخچال', 'میز', 'رایانه',
                    'آموزش', 'نظافت', 'باغبانی', 'تعمیر', 'حمل',
                    'فروشگاه', 'مغازه', 'کافه', 'رستوران'
                ]
                if text and text not in features:
                    # Skip if it contains unwanted keywords
                    if not any(keyword in text for keyword in unwanted_keywords):
                        features.append(text)
        except Exception as e:
            logger.warning(f"Failed to extract features: {e}")
        
        return features
    
    def _extract_amenities(self, soup) -> List[str]:
        """Extract property amenities (parking, elevator, storage, etc.)"""
        amenities = []
        
        try:
            # Look for the amenities/features section title
            amenity_titles = ['امکانات', 'ویژگی', 'مشخصات', 'توضیحات بیشتر']
            
            for title in amenity_titles:
                # Find section with this title
                amenity_section = soup.find('span', class_='kt-section-title__title', string=lambda x: x and title in x)
                if amenity_section:
                    # Get parent container
                    section_parent = amenity_section.find_parent('div', class_='kt-section-title')
                    if section_parent:
                        # Find next sibling which should contain the features
                        next_elem = section_parent.find_next_sibling()
                        if next_elem:
                            # Extract feature row items
                            feature_items = next_elem.select('.kt-group-row-item__value, .kt-feature-row__title, .kt-unexpandable-row__value')
                            for item in feature_items:
                                text = item.get_text(strip=True)
                                if text and text not in amenities and len(text) > 1:
                                    amenities.append(text)
            
            # Comprehensive list of property amenity keywords
            amenity_keywords = [
                # Basic amenities
                'پارکینگ', 'انباری', 'آسانسور', 'بالکن', 'لابی', 'سرایدار',
                # Luxury features 
                'استخر', 'سونا', 'جکوزی', 'سالن ورزش', 'روف گاردن',
                # Heating/Cooling
                'کولر', 'شوفاژ', 'پکیج', 'رادیاتور', 'اسپلیت', 'چیلر',
                # Flooring & Interior
                'کف', 'پارکت', 'سرامیک', 'موزاییک', 'سنگ', 'کاشی',
                'کمد', 'دیواری', 'شومینه',
                # Kitchen & Bathroom
                'سرویس', 'آشپزخانه', 'هود', 'کابینت', 'گاز',
                # Building features
                'اسکلت', 'فلزی', 'بتنی', 'نورگیر', 'حیاط', 'مشجر',
                # Utilities
                'برق', 'آب', 'گاز', 'تلفن', 'فاضلاب',
                # Direction
                'شمالی', 'جنوبی', 'شرقی', 'غربی',
                # Status
                'نوساز', 'بازسازی', 'نقاشی', 'کناف'
            ]
            
            # Extract from all value elements
            all_text_elements = soup.select('.kt-group-row-item__value, .kt-unexpandable-row__value, .kt-unexpandable-row__title')
            for elem in all_text_elements:
                text = elem.get_text(strip=True)
                # Check if contains any amenity keyword
                if any(keyword in text for keyword in amenity_keywords):
                    if text and text not in amenities and len(text) > 1:
                        amenities.append(text)
            
            # Also extract from description if it contains structured amenity info
            desc_elem = soup.select_one('.kt-description-row__text')
            if desc_elem:
                desc_text = desc_elem.get_text()
                # Extract line-by-line amenities from description
                for line in desc_text.split('\n'):
                    line = line.strip()
                    if line and any(keyword in line for keyword in amenity_keywords):
                        # Only add short lines that look like amenities
                        if len(line) < 50 and line not in amenities:
                            amenities.append(line)
                        
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
    
    async def _click_show_all_details(self) -> bool:
        """Click 'Show all details' button to reveal hidden features"""
        try:
            # Selectors for "Show all details" button
            show_all_selectors = [
                'button:has-text("نمایش همهٔ جزئیات")',
                'button:has-text("نمایش همه")',
                'button:has-text("مشاهده بیشتر")',
                '.kt-show-more-button',
                'button.kt-button--secondary:has-text("جزئیات")',
            ]
            
            for selector in show_all_selectors:
                try:
                    button = await self.page.query_selector(selector)
                    if button:
                        is_visible = await button.is_visible()
                        if is_visible:
                            logger.info(f"Found 'Show all details' button with selector: {selector}")
                            await button.scroll_into_view_if_needed()
                            await asyncio.sleep(0.3)
                            await button.click(force=True, timeout=3000)
                            logger.info("'Show all details' button clicked successfully")
                            await asyncio.sleep(1.5)  # Wait for content to expand
                            return True
                except Exception as e:
                    logger.debug(f"Failed with selector {selector}: {e}")
                    continue
            
            logger.info("No 'Show all details' button found (content may already be expanded)")
            return False
            
        except Exception as e:
            logger.warning(f"Failed to click 'Show all details' button: {e}")
            return False
    
    async def _get_phone_number(self) -> Optional[str]:
        """Click contact button and extract phone number"""
        try:
            # Try multiple selectors for contact button
            contact_selectors = [
                '.post-actions__get-contact',  # Most specific first
                'button.kt-button--primary:has-text("اطلاعات تماس")',
                'button:has-text("اطلاعات تماس")',
                'button:has-text("شماره تماس")',
                'button:has-text("تماس")',
                '[data-testid="contact-button"]',
                '.kt-contact-row button',
                'button.kt-button--primary:has-text("تماس")',
            ]
            
            contact_button = None
            for selector in contact_selectors:
                try:
                    contact_button = await self.page.query_selector(selector)
                    if contact_button:
                        is_visible = await contact_button.is_visible()
                        if is_visible:
                            logger.info(f"Found visible contact button with selector: {selector}")
                            break
                        contact_button = None
                except Exception:
                    continue
            
            if contact_button:
                await self._human_like_delay(0.3, 0.8)
                
                # Use force click and scroll into view
                try:
                    # Scroll button into view first
                    await contact_button.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    
                    # Try regular click with force
                    await contact_button.click(force=True, timeout=5000)
                    logger.info("Contact button clicked successfully with force")
                except Exception as click_err:
                    logger.warning(f"Force click failed, trying dispatchEvent: {click_err}")
                    try:
                        # Try dispatching a click event directly
                        await self.page.evaluate('''(el) => {
                            el.dispatchEvent(new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            }));
                        }''', contact_button)
                        logger.info("dispatchEvent click executed")
                    except Exception as dispatch_err:
                        logger.warning(f"dispatchEvent also failed: {dispatch_err}")
                
                # Wait for network to settle after click
                try:
                    await self.page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    pass
                
                await asyncio.sleep(3)  # Wait longer for modal/response to load
                
                # Save screenshot for debugging
                try:
                    debug_screenshot = self.images_dir / "debug_after_click.png"
                    await self.page.screenshot(path=str(debug_screenshot))
                    logger.info(f"Debug screenshot saved to {debug_screenshot}")
                except Exception:
                    pass
                
                # Log current page content for debugging
                try:
                    page_content = await self.page.content()
                    if 'tel:' in page_content:
                        logger.info("Phone number link found in page content")
                    else:
                        logger.info("No tel: link found in page content after click")
                        # Check for modal or overlay
                        if 'kt-new-modal' in page_content or 'kt-modal' in page_content:
                            logger.info("Modal detected on page")
                        # Check for any 09 phone patterns (Persian or English)
                        import re
                        phone_patterns = re.findall(r'[۰-۹0-9]{10,11}', page_content)
                        if phone_patterns:
                            logger.info(f"Found phone-like patterns: {phone_patterns[:5]}")
                except Exception:
                    pass
                
                # Try multiple selectors for phone number - expanded list
                phone_selectors = [
                    'a[href^="tel:"]',
                    '.kt-unexpandable-row__action a[href^="tel:"]',
                    '[data-testid="phone-number"]',
                    '.kt-base-row a[href^="tel:"]',
                    'a.kt-unexpandable-row__action-btn',
                    '.post-actions__phone a',
                    'a[class*="phone"]',
                    # Modal-based selectors
                    '.kt-new-modal a[href^="tel:"]',
                    '.kt-modal a[href^="tel:"]',
                    '.kt-dimmer a[href^="tel:"]',
                    '[role="dialog"] a[href^="tel:"]',
                    # Text-based selectors
                    'span:has-text("09")',
                    'p:has-text("09")',
                    'div:has-text("۰۹")',
                ]
                
                phone_found = False
                for selector in phone_selectors:
                    try:
                        phone_elem = await self.page.wait_for_selector(selector, timeout=2000)
                        if phone_elem:
                            logger.info(f"Found phone element with selector: {selector}")
                            # Get href attribute for cleaner phone extraction
                            href = await phone_elem.get_attribute('href')
                            if href and href.startswith('tel:'):
                                phone_text = href.replace('tel:', '').strip()
                            else:
                                phone_text = await phone_elem.inner_text()
                            
                            logger.info(f"Raw phone text: {phone_text}")
                            
                            # Convert Persian numbers
                            phone = self._parse_persian_number(phone_text)
                            if phone:
                                phone_str = str(phone)
                                # Ensure proper format
                                if len(phone_str) == 10 and not phone_str.startswith('0'):
                                    logger.info(f"Extracted phone number: 0{phone_str}")
                                    return f"0{phone_str}"
                                elif len(phone_str) == 11 and phone_str.startswith('0'):
                                    logger.info(f"Extracted phone number: {phone_str}")
                                    return phone_str
                                elif len(phone_str) >= 10:
                                    logger.info(f"Extracted phone number: {phone_str}")
                                    return phone_str
                            phone_found = True
                            break
                    except Exception as e:
                        continue
                
                # Last resort: try to extract phone from page content using regex
                if not phone_found:
                    try:
                        page_content = await self.page.content()
                        import re
                        # Look for Persian phone numbers (۰۹ pattern)
                        persian_pattern = r'[۰۹]{2}[۰-۹]{9}'
                        english_pattern = r'0?9[0-9]{9}'
                        
                        matches = re.findall(persian_pattern, page_content)
                        if matches:
                            phone = self._parse_persian_number(matches[0])
                            if phone:
                                logger.info(f"Extracted phone from regex (Persian): {phone}")
                                return f"0{phone}" if not str(phone).startswith('0') else str(phone)
                        
                        matches = re.findall(english_pattern, page_content)
                        if matches:
                            phone = matches[0]
                            if not phone.startswith('0'):
                                phone = '0' + phone
                            logger.info(f"Extracted phone from regex (English): {phone}")
                            return phone
                    except Exception as regex_err:
                        logger.warning(f"Regex extraction failed: {regex_err}")
                
                if not phone_found:
                    logger.warning("No phone element found after clicking contact button")
            else:
                logger.warning("No contact button found on page - phone cannot be extracted")
            
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
            
            # Validate required fields
            if not divar_id:
                logger.warning("Cannot save property: missing divar_id")
                return None
            
            if not property_data.get('title'):
                logger.warning(f"Cannot save property {divar_id}: missing title")
                return None
            
            if not property_data.get('url'):
                logger.warning(f"Cannot save property {divar_id}: missing url")
                return None
            
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
        download_images: bool = True,
        job_id: Optional[str] = None
    ) -> ScrapingJob:
        """Start a complete scraping job for a city and category"""
        
        # Get or create job record
        if job_id:
            # Use existing job
            result = await self.db_session.execute(
                select(ScrapingJob).where(ScrapingJob.job_id == job_id)
            )
            job = result.scalar_one_or_none()
            if not job:
                raise ValueError(f"Job {job_id} not found")
            job.status = "running"
            job.started_at = datetime.now()
        else:
            # Create new job record
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
                # Check if job was cancelled
                await self.db_session.refresh(job)
                if job.status == "cancelled":
                    logger.info(f"Job {job.job_id} was cancelled, stopping scraping")
                    return job
                
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
                    # Check if job was cancelled
                    await self.db_session.refresh(job)
                    if job.status == "cancelled":
                        logger.info(f"Job {job.job_id} was cancelled, stopping scraping")
                        return job
                    
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
