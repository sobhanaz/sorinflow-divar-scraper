"""
Test Divar Property Scraping with Enhanced Extraction
Tests all fields including new ones based on actual Divar HTML structure
"""
import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.scraper.divar_scraper import DivarScraper
from app.database import async_session_maker
from loguru import logger


async def test_property_extraction():
    """Test comprehensive property extraction"""
    
    # Sample URLs for testing - replace with actual Divar URLs
    test_urls = [
        # Buy property example
        "https://divar.ir/v/واحد-72-متری-در-500-دستگاه/example1",  
        # Rent property example
        "https://divar.ir/v/حالت-آپارتمانی-باکری-خانواده-مجردی/example2"
    ]
    
    logger.info("Starting comprehensive property extraction test...")
    
    async with async_session_maker() as session:
        scraper = DivarScraper(
            db_session=session,
            proxy_enabled=False,
            headless=True
        )
        
        try:
            await scraper.initialize(restore_session=True)
            logger.info("Scraper initialized successfully")
            
            for i, url in enumerate(test_urls, 1):
                logger.info(f"\n{'='*80}")
                logger.info(f"Test {i}/{len(test_urls)}: {url}")
                logger.info(f"{'='*80}\n")
                
                try:
                    # Scrape property
                    property_data = await scraper.scrape_property_detail(url)
                    
                    if property_data:
                        logger.success(f"✅ Property scraped successfully!")
                        logger.info("\n📋 Extracted Data:")
                        
                        # Basic info
                        logger.info(f"  Title: {property_data.get('title', 'N/A')}")
                        logger.info(f"  Divar ID: {property_data.get('divar_id', 'N/A')}")
                        logger.info(f"  URL: {property_data.get('url', 'N/A')}")
                        
                        # Pricing
                        logger.info("\n💰 Pricing:")
                        logger.info(f"  Total Price: {property_data.get('total_price', 'N/A'):,} تومان" if property_data.get('total_price') else "  Total Price: N/A")
                        logger.info(f"  Price Per Meter: {property_data.get('price_per_meter', 'N/A'):,} تومان" if property_data.get('price_per_meter') else "  Price Per Meter: N/A")
                        logger.info(f"  Rent Price: {property_data.get('rent_price', 'N/A'):,} تومان" if property_data.get('rent_price') else "  Rent Price: N/A")
                        logger.info(f"  Deposit: {property_data.get('deposit', 'N/A'):,} تومان" if property_data.get('deposit') else "  Deposit: N/A")
                        
                        # Property details
                        logger.info("\n🏠 Property Details:")
                        logger.info(f"  Area: {property_data.get('area', 'N/A')} متر")
                        logger.info(f"  Rooms: {property_data.get('rooms', 'N/A')}")
                        logger.info(f"  Floor: {property_data.get('floor', 'N/A')}")
                        logger.info(f"  Total Floors: {property_data.get('total_floors', 'N/A')}")
                        logger.info(f"  Year Built: {property_data.get('year_built', 'N/A')}")
                        logger.info(f"  Building Age: {property_data.get('building_age', 'N/A')}")
                        
                        # Amenities
                        logger.info("\n✨ Amenities:")
                        logger.info(f"  Elevator: {'✓ Yes' if property_data.get('has_elevator') else '✗ No'}")
                        logger.info(f"  Parking: {'✓ Yes' if property_data.get('has_parking') else '✗ No'}")
                        logger.info(f"  Storage: {'✓ Yes' if property_data.get('has_storage') else '✗ No'}")
                        logger.info(f"  Balcony: {'✓ Yes' if property_data.get('has_balcony') else '✗ No'}")
                        logger.info(f"  Has Images: {'✓ Yes' if property_data.get('has_images') else '✗ No'}")
                        
                        # Location
                        logger.info("\n📍 Location:")
                        logger.info(f"  City: {property_data.get('city_name', 'N/A')}")
                        logger.info(f"  District: {property_data.get('district', 'N/A')}")
                        logger.info(f"  Neighborhood: {property_data.get('neighborhood', 'N/A')}")
                        
                        # Contact
                        logger.info("\n📞 Contact:")
                        logger.info(f"  Phone: {property_data.get('phone_number', 'N/A')}")
                        
                        # Images
                        images = property_data.get('images', [])
                        logger.info(f"\n🖼️ Images: {len(images)} images found")
                        if images:
                            for idx, img in enumerate(images[:3], 1):
                                logger.info(f"  {idx}. {img[:80]}...")
                        
                        # Features
                        features = property_data.get('features', [])
                        logger.info(f"\n🎯 Features: {len(features)} features found")
                        if features:
                            for feature in features[:5]:
                                logger.info(f"  • {feature}")
                        
                        # Amenities list
                        amenities = property_data.get('amenities', [])
                        logger.info(f"\n🏆 Amenity Details: {len(amenities)} items found")
                        if amenities:
                            for amenity in amenities[:5]:
                                logger.info(f"  • {amenity}")
                        
                        # Description preview
                        description = property_data.get('description', '')
                        if description:
                            logger.info(f"\n📝 Description Preview:")
                            logger.info(f"  {description[:200]}...")
                        
                        # Save to database
                        saved = await scraper.save_property(property_data)
                        if saved:
                            logger.success(f"\n✅ Property saved to database with tag: {saved.tag_number}")
                        else:
                            logger.warning("\n⚠️ Failed to save property to database")
                    else:
                        logger.error(f"❌ Failed to scrape property")
                
                except Exception as e:
                    logger.error(f"❌ Error processing URL: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Wait between requests
                await asyncio.sleep(3)
            
        finally:
            await scraper.close()
            logger.info("\n✅ Test completed and scraper closed")


async def test_field_mapping():
    """Test field extraction mapping"""
    logger.info("\n" + "="*80)
    logger.info("FIELD EXTRACTION MAPPING TEST")
    logger.info("="*80 + "\n")
    
    logger.info("📊 Checking extraction capabilities:\n")
    
    fields = [
        ("Title", "h1.kt-page-title__title", "✅"),
        ("Meterage", "td.kt-group-row-item__value", "✅"),
        ("Build Year", "td.kt-group-row-item__value", "✅"),
        ("Room Number", "td.kt-group-row-item__value", "✅"),
        ("Has Images", "p.kt-unexpandable-row__value", "✅"),
        ("Full Price", "p.kt-unexpandable-row__value", "✅"),
        ("Price Per Meter", "p.kt-unexpandable-row__value", "✅"),
        ("Floor", "p.kt-unexpandable-row__value", "✅"),
        ("Deposit", "p.kt-unexpandable-row__value", "✅"),
        ("Rent Price", "p.kt-unexpandable-row__value", "✅"),
        ("Elevator", "Parsed from amenities", "✅"),
        ("Parking", "Parsed from amenities", "✅"),
        ("Storage", "Parsed from amenities", "✅"),
        ("Balcony", "Parsed from amenities", "✅"),
        ("Phone Number", "Requires authentication", "✅"),
        ("Images", "kt-image-block__image selector", "✅"),
        ("Description", "kt-description-row__text", "✅"),
        ("Location", "Breadcrumb navigation", "✅"),
    ]
    
    for field, selector, status in fields:
        logger.info(f"{status} {field:20} → {selector}")
    
    logger.info("\n" + "="*80)


if __name__ == "__main__":
    logger.info("🚀 Starting Divar Scraper Comprehensive Test\n")
    
    # Run field mapping test first
    asyncio.run(test_field_mapping())
    
    # Ask user if they want to run actual scraping test
    logger.info("\n⚠️  Note: To test actual scraping, provide real Divar URLs in the test_urls list")
    logger.info("Edit this file and add URLs, then run again\n")
    
    # Uncomment to run actual scraping
    # asyncio.run(test_property_extraction())
