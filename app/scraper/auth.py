"""
SorinFlow Divar Scraper - Authentication Handler
Handles login, cookies, and session management for Divar.ir
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.cookie import Cookie
from app.scraper.stealth import StealthConfig, STEALTH_JS, get_browser_args, get_context_options

settings = get_settings()


class DivarAuth:
    """Handle Divar.ir authentication with cookies and session management"""
    
    def __init__(self, db_session: Optional[AsyncSession] = None):
        self.db_session = db_session
        self.cookies_dir = Path(settings.cookies_path)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        self.stealth_config = StealthConfig()
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
    
    async def initialize_browser(self, proxy: Optional[str] = None, headless: bool = True):
        """Initialize browser with stealth settings"""
        playwright = await async_playwright().start()
        
        self.browser = await playwright.chromium.launch(
            headless=headless,
            args=get_browser_args()
        )
        
        context_options = get_context_options(self.stealth_config, proxy)
        self.context = await self.browser.new_context(**context_options)
        
        # Add stealth script
        await self.context.add_init_script(STEALTH_JS)
        
        self.page = await self.context.new_page()
        return self.page
    
    async def close_browser(self):
        """Close browser and cleanup"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
    
    def get_cookie_file_path(self, phone_number: str) -> Path:
        """Get path for cookie file"""
        return self.cookies_dir / f"cookies_{phone_number}.json"
    
    async def save_cookies_to_file(self, phone_number: str, cookies: List[Dict]) -> bool:
        """Save cookies to file"""
        try:
            cookie_file = self.get_cookie_file_path(phone_number)
            with open(cookie_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "phone_number": phone_number,
                    "cookies": cookies,
                    "saved_at": datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"Cookies saved to file for {phone_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to save cookies to file: {e}")
            return False
    
    async def load_cookies_from_file(self, phone_number: str) -> Optional[List[Dict]]:
        """Load cookies from file"""
        try:
            cookie_file = self.get_cookie_file_path(phone_number)
            if cookie_file.exists():
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("cookies", [])
            return None
        except Exception as e:
            logger.error(f"Failed to load cookies from file: {e}")
            return None
    
    async def save_cookies_to_db(self, phone_number: str, cookies: List[Dict], token: Optional[str] = None) -> bool:
        """Save cookies to database"""
        if not self.db_session:
            return False
        
        try:
            # Find token expiry
            expires_at = None
            for cookie in cookies:
                if cookie.get("name") == "token":
                    if "expires" in cookie:
                        expires_at = datetime.fromtimestamp(cookie["expires"])
                    break
            
            # Check if cookie exists for this phone
            result = await self.db_session.execute(
                select(Cookie).where(Cookie.phone_number == phone_number)
            )
            existing_cookie = result.scalar_one_or_none()
            
            if existing_cookie:
                existing_cookie.cookies = cookies
                existing_cookie.token = token
                existing_cookie.is_valid = True
                existing_cookie.expires_at = expires_at
                existing_cookie.updated_at = datetime.now()
            else:
                new_cookie = Cookie(
                    phone_number=phone_number,
                    cookies=cookies,
                    token=token,
                    is_valid=True,
                    expires_at=expires_at
                )
                self.db_session.add(new_cookie)
            
            await self.db_session.commit()
            logger.info(f"Cookies saved to database for {phone_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to save cookies to database: {e}")
            await self.db_session.rollback()
            return False
    
    async def load_cookies_from_db(self, phone_number: str) -> Optional[List[Dict]]:
        """Load cookies from database"""
        if not self.db_session:
            return None
        
        try:
            result = await self.db_session.execute(
                select(Cookie).where(
                    Cookie.phone_number == phone_number,
                    Cookie.is_valid == True
                )
            )
            cookie = result.scalar_one_or_none()
            
            if cookie:
                # Check if expired (handle timezone-aware vs naive datetime)
                if cookie.expires_at:
                    expires_at = cookie.expires_at
                    now = datetime.utcnow()
                    # Make comparison timezone-naive if needed
                    if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is not None:
                        expires_at = expires_at.replace(tzinfo=None)
                    
                    if expires_at < now:
                        cookie.is_valid = False
                        await self.db_session.commit()
                        logger.warning(f"Cookies expired for {phone_number}")
                        return None
                return cookie.cookies
            return None
        except Exception as e:
            logger.error(f"Failed to load cookies from database: {e}")
            return None
    
    async def check_cookies_validity(self, cookies: List[Dict]) -> bool:
        """Check if cookies are still valid"""
        try:
            token_cookie = next((c for c in cookies if c.get("name") == "token"), None)
            if token_cookie:
                if "expires" in token_cookie:
                    expires = datetime.fromtimestamp(token_cookie["expires"])
                    if expires > datetime.now():
                        return True
            return False
        except Exception as e:
            logger.error(f"Failed to check cookie validity: {e}")
            return False
    
    async def apply_cookies(self, cookies: List[Dict]) -> bool:
        """Apply cookies to current browser context"""
        if not self.context:
            logger.error("Browser context not initialized")
            return False
        
        try:
            await self.context.add_cookies(cookies)
            logger.info("Cookies applied to browser context")
            return True
        except Exception as e:
            logger.error(f"Failed to apply cookies: {e}")
            return False
    
    async def get_current_cookies(self) -> List[Dict]:
        """Get current cookies from browser context"""
        if not self.context:
            return []
        
        try:
            cookies = await self.context.cookies()
            return cookies
        except Exception as e:
            logger.error(f"Failed to get current cookies: {e}")
            return []
    
    async def login_with_phone(self, phone_number: str, wait_for_code: bool = True) -> Dict[str, Any]:
        """
        Login to Divar with phone number
        Returns status and instructions for OTP verification
        """
        result = {
            "success": False,
            "message": "",
            "requires_code": False,
            "cookies": None
        }
        
        try:
            if not self.page:
                await self.initialize_browser(headless=settings.scraper_headless)
            
            # Navigate to login page
            logger.info("Navigating to Divar login page...")
            await self.page.goto(settings.divar_login_url, wait_until="networkidle")
            await asyncio.sleep(self.stealth_config.get_random_delay())
            
            # Click on login button
            logger.info("Looking for login button...")
            login_button = await self.page.query_selector('button:has-text("ورود")')
            if login_button:
                await login_button.click()
                await asyncio.sleep(2)
            
            # Enter phone number
            logger.info(f"Entering phone number: {phone_number}")
            phone_input = await self.page.wait_for_selector('input[name="mobile"]', timeout=10000)
            await phone_input.fill("")
            
            # Type phone number with human-like delays
            for char in phone_number:
                await phone_input.type(char, delay=self.stealth_config.typing_delay * 1000)
                await asyncio.sleep(0.05)
            
            await asyncio.sleep(1)
            
            # Click confirm button
            logger.info("Clicking confirm button...")
            confirm_button = await self.page.query_selector('button:has-text("تأیید")')
            if confirm_button:
                await confirm_button.click()
                await asyncio.sleep(3)
            
            result["requires_code"] = True
            result["message"] = f"OTP code sent to {phone_number}. Please provide the 6-digit code."
            logger.info(result["message"])
            
            return result
            
        except Exception as e:
            result["message"] = f"Login failed: {str(e)}"
            logger.error(result["message"])
            return result
    
    async def submit_otp_code(self, code: str, phone_number: str = None) -> Dict[str, Any]:
        """Submit OTP verification code"""
        result = {
            "success": False,
            "message": "",
            "cookies": None,
            "phone_number": phone_number
        }
        
        try:
            if not self.page:
                result["message"] = "Browser not initialized. Please start login again."
                return result
            
            # Enter verification code
            logger.info("Entering verification code...")
            code_input = await self.page.wait_for_selector('input[name="code"]', timeout=10000)
            await code_input.fill("")
            
            # Type code with delays
            for char in code:
                await code_input.type(char, delay=self.stealth_config.typing_delay * 1000)
                await asyncio.sleep(0.05)
            
            await asyncio.sleep(1)
            
            # Click login button
            logger.info("Clicking login button...")
            login_button = await self.page.query_selector('button:has-text("ورود")')
            if login_button:
                await login_button.click()
                await asyncio.sleep(5)
            
            # Check if login successful
            cookies = await self.get_current_cookies()
            token_cookie = next((c for c in cookies if c.get("name") == "token"), None)
            
            if token_cookie:
                result["success"] = True
                result["message"] = "Login successful!"
                result["cookies"] = cookies
                
                # Save cookies - use passed phone_number or fall back to settings
                save_phone = phone_number or settings.divar_phone_number
                if save_phone:
                    await self.save_cookies_to_file(save_phone, cookies)
                    if self.db_session:
                        await self.save_cookies_to_db(save_phone, cookies, token_cookie.get("value"))
                    logger.info(f"Login successful, cookies saved for {save_phone}!")
                else:
                    logger.warning("No phone number provided, cookies not saved")
            else:
                result["message"] = "Login failed. Token cookie not found."
                logger.error(result["message"])
            
            return result
            
        except Exception as e:
            result["message"] = f"OTP verification failed: {str(e)}"
            logger.error(result["message"])
            return result
    
    async def restore_session(self, phone_number: str) -> bool:
        """Restore session from saved cookies"""
        try:
            # Try database first
            cookies = await self.load_cookies_from_db(phone_number)
            
            # Fall back to file
            if not cookies:
                cookies = await self.load_cookies_from_file(phone_number)
            
            if not cookies:
                logger.warning(f"No saved cookies found for {phone_number}")
                return False
            
            # Check validity
            is_valid = await self.check_cookies_validity(cookies)
            if not is_valid:
                logger.warning(f"Cookies expired for {phone_number}")
                return False
            
            # Initialize browser if needed
            if not self.page:
                await self.initialize_browser(headless=settings.scraper_headless)
            
            # Apply cookies
            await self.apply_cookies(cookies)
            
            # Navigate and verify
            await self.page.goto("https://divar.ir", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # Check if logged in
            current_cookies = await self.get_current_cookies()
            token_cookie = next((c for c in current_cookies if c.get("name") == "token"), None)
            
            if token_cookie:
                logger.info(f"Session restored successfully for {phone_number}")
                return True
            
            logger.warning("Session restoration failed - token not found")
            return False
            
        except Exception as e:
            logger.error(f"Failed to restore session: {e}")
            return False
    
    async def invalidate_cookies(self, phone_number: str) -> bool:
        """Invalidate stored cookies"""
        try:
            # Remove from database
            if self.db_session:
                result = await self.db_session.execute(
                    select(Cookie).where(Cookie.phone_number == phone_number)
                )
                cookie = result.scalar_one_or_none()
                if cookie:
                    cookie.is_valid = False
                    await self.db_session.commit()
            
            # Remove file
            cookie_file = self.get_cookie_file_path(phone_number)
            if cookie_file.exists():
                os.remove(cookie_file)
            
            logger.info(f"Cookies invalidated for {phone_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to invalidate cookies: {e}")
            return False
    
    async def get_cookie_status(self, phone_number: str) -> Dict[str, Any]:
        """Get status of stored cookies"""
        status = {
            "has_cookies": False,
            "is_valid": False,
            "expires_at": None,
            "phone_number": phone_number,
            "message": "No cookies found"
        }
        
        try:
            # Check database
            cookies = await self.load_cookies_from_db(phone_number)
            if not cookies:
                cookies = await self.load_cookies_from_file(phone_number)
            
            if cookies:
                status["has_cookies"] = True
                is_valid = await self.check_cookies_validity(cookies)
                status["is_valid"] = is_valid
                
                token_cookie = next((c for c in cookies if c.get("name") == "token"), None)
                if token_cookie and "expires" in token_cookie:
                    expires = datetime.fromtimestamp(token_cookie["expires"])
                    status["expires_at"] = expires.isoformat()
                    
                    if is_valid:
                        days_left = (expires - datetime.now()).days
                        status["message"] = f"Cookies valid. Expires in {days_left} days."
                    else:
                        status["message"] = "Cookies expired. Please login again."
                else:
                    status["message"] = "Cookie status unknown"
            
            return status
        except Exception as e:
            status["message"] = f"Error checking cookie status: {str(e)}"
            return status
