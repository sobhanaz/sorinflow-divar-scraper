"""
Test comprehensive data extraction from Divar property pages
This script tests the enhanced scraper with "Show all details" button clicking
"""
import asyncio
import logging
from app.scraper.divar_scraper import DivarScraper
from app.database import get_db
from app.models.property import Property
from sqlalchemy.ext.asyncio import AsyncSession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_scraper():
    """Test comprehensive data extraction"""
    
    # Test URL - use a real Divar property URL
    test_url = "https://divar.ir/v/املاک-رهن-و-اجاره/آپارتمان/خ-شهید-بهشتی-24/QadxGfsx"
    
    logger.info("="*80)
    logger.info("Testing Comprehensive Divar Scraper")
    logger.info("="*80)
    
    # Get DB session
    async for db in get_db():
        try:
            # Initialize scraper
            scraper = DivarScraper(db_session=db, proxy_enabled=False)
            await scraper.initialize()
            
            logger.info(f"\n📍 Test URL: {test_url}")
            logger.info("-" * 80)
            
            # Scrape property
            property_data = await scraper.scrape_property_detail(test_url)
            
            if property_data:
                logger.info("\n✅ Scraping Successful!")
                logger.info("="*80)
                logger.info("📊 Extracted Data Summary:")
                logger.info("="*80)
                
                # Basic info
                logger.info(f"\n🏠 Basic Information:")
                logger.info(f"  Title: {property_data.get('title', 'N/A')}")
                logger.info(f"  Tag Number: {property_data.get('tag_number', 'N/A')}")
                logger.info(f"  Divar ID: {property_data.get('divar_id', 'N/A')}")
                
                # Pricing
                logger.info(f"\n💰 Pricing:")
                logger.info(f"  Total Price: {property_data.get('total_price', 'N/A')} تومان")
                logger.info(f"  Price per Meter: {property_data.get('price_per_meter', 'N/A')} تومان")
                logger.info(f"  Rent: {property_data.get('rent_price', 'N/A')} تومان")
                logger.info(f"  Deposit: {property_data.get('deposit', 'N/A')} تومان")
                
                # Property Details
                logger.info(f"\n📏 Property Details:")
                logger.info(f"  Area (Built): {property_data.get('area', 'N/A')} m²")
                logger.info(f"  Land Area: {property_data.get('land_area', 'N/A')} m²")
                logger.info(f"  Built Area: {property_data.get('built_area', 'N/A')} m²")
                logger.info(f"  Rooms: {property_data.get('rooms', 'N/A')}")
                logger.info(f"  Year Built: {property_data.get('year_built', 'N/A')}")
                logger.info(f"  Floor: {property_data.get('floor', 'N/A')} / {property_data.get('total_floors', 'N/A')}")
                
                # Building specs
                logger.info(f"\n🏗️ Building Specifications:")
                logger.info(f"  Frontage (بر): {property_data.get('frontage', 'N/A')} m")
                logger.info(f"  Direction: {property_data.get('building_direction', 'N/A')}")
                logger.info(f"  Unit Status: {property_data.get('unit_status', 'N/A')}")
                logger.info(f"  Document Type: {property_data.get('document_type', 'N/A')}")
                logger.info(f"  Usage Type: {property_data.get('usage_type', 'N/A')}")
                logger.info(f"  Building Age: {property_data.get('building_age', 'N/A')}")
                
                # Amenities
                logger.info(f"\n✨ Amenities:")
                logger.info(f"  Elevator: {'✓' if property_data.get('has_elevator') else '✗'}")
                logger.info(f"  Parking: {'✓' if property_data.get('has_parking') else '✗'}")
                logger.info(f"  Storage: {'✓' if property_data.get('has_storage') else '✗'}")
                logger.info(f"  Balcony: {'✓' if property_data.get('has_balcony') else '✗'}")
                
                # Features & Amenities Lists
                features = property_data.get('features', [])
                amenities = property_data.get('amenities', [])
                
                logger.info(f"\n🎯 Features ({len(features)} items):")
                for i, feature in enumerate(features[:10], 1):
                    logger.info(f"  {i}. {feature}")
                if len(features) > 10:
                    logger.info(f"  ... and {len(features) - 10} more")
                
                logger.info(f"\n🏆 Amenities ({len(amenities)} items):")
                for i, amenity in enumerate(amenities[:10], 1):
                    logger.info(f"  {i}. {amenity}")
                if len(amenities) > 10:
                    logger.info(f"  ... and {len(amenities) - 10} more")
                
                # Location
                logger.info(f"\n📍 Location:")
                logger.info(f"  City: {property_data.get('city_name', 'N/A')}")
                logger.info(f"  District: {property_data.get('district', 'N/A')}")
                logger.info(f"  Neighborhood: {property_data.get('neighborhood', 'N/A')}")
                logger.info(f"  Coordinates: {property_data.get('latitude', 'N/A')}, {property_data.get('longitude', 'N/A')}")
                
                # Images
                images = property_data.get('images', [])
                logger.info(f"\n📸 Images: {len(images)} photos")
                
                # Contact
                logger.info(f"\n📞 Contact:")
                logger.info(f"  Phone: {property_data.get('phone_number', 'N/A')}")
                logger.info(f"  Seller: {property_data.get('seller_name', 'N/A')}")
                
                # Description preview
                desc = property_data.get('description', '')
                if desc:
                    logger.info(f"\n📝 Description (first 200 chars):")
                    logger.info(f"  {desc[:200]}...")
                
                # Data completeness check
                logger.info("\n" + "="*80)
                logger.info("📊 Data Completeness Check:")
                logger.info("="*80)
                
                critical_fields = {
                    'title': property_data.get('title'),
                    'area': property_data.get('area'),
                    'land_area': property_data.get('land_area'),
                    'rooms': property_data.get('rooms'),
                    'year_built': property_data.get('year_built'),
                    'frontage': property_data.get('frontage'),
                    'building_direction': property_data.get('building_direction'),
                    'city_name': property_data.get('city_name'),
                    'phone_number': property_data.get('phone_number'),
                }
                
                filled_count = sum(1 for v in critical_fields.values() if v is not None)
                total_count = len(critical_fields)
                completeness = (filled_count / total_count) * 100
                
                logger.info(f"\n  Critical Fields Filled: {filled_count}/{total_count} ({completeness:.1f}%)")
                
                for field, value in critical_fields.items():
                    status = "✓" if value is not None else "✗"
                    logger.info(f"  {status} {field}: {value if value is not None else 'Missing'}")
                
                # Features/Amenities check
                logger.info(f"\n  Features extracted: {len(features)} items")
                logger.info(f"  Amenities extracted: {len(amenities)} items")
                logger.info(f"  Images extracted: {len(images)} images")
                
                if completeness >= 80:
                    logger.info(f"\n✅ EXCELLENT: {completeness:.1f}% data completeness!")
                elif completeness >= 60:
                    logger.info(f"\n⚠️  GOOD: {completeness:.1f}% data completeness")
                else:
                    logger.info(f"\n❌ NEEDS IMPROVEMENT: {completeness:.1f}% data completeness")
                
            else:
                logger.error("\n❌ Failed to scrape property")
            
            # Cleanup
            await scraper.close()
            
        except Exception as e:
            logger.error(f"\n❌ Error during test: {e}", exc_info=True)
        
        break  # Exit after first iteration

if __name__ == "__main__":
    asyncio.run(test_scraper())
