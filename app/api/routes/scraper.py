"""
SorinFlow Divar Scraper - Scraper API Routes
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from datetime import datetime
import asyncio
import logging

from app.database import get_db, get_redis
from app.models.scraping_job import ScrapingJob
from app.scraper.divar_scraper import DivarScraper
from app.config import get_settings, CITIES, CATEGORIES
from app.schemas import ScrapingJobCreate, ScrapingJobResponse, ScrapingJobList

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

# Store active scraping job IDs for tracking
active_tasks = {}


async def run_scraping_job(
    job_id: str,
    city: str,
    category: str,
    max_pages: int,
    download_images: bool,
    db_url: str
):
    """Background task to run scraping job"""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        scraper = DivarScraper(
            db_session=session,
            proxy_enabled=settings.proxy_enabled,
            headless=settings.scraper_headless
        )
        
        try:
            await scraper.initialize()
            await scraper.start_scraping_job(
                job_id=job_id,
                city=city,
                category=category,
                max_pages=max_pages,
                download_images=download_images
            )
        finally:
            await scraper.close()
            if job_id in active_tasks:
                del active_tasks[job_id]


@router.post("/start", response_model=ScrapingJobResponse)
async def start_scraping_job(
    job_config: ScrapingJobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Start a new scraping job"""
    
    # Validate city and category
    if job_config.city not in CITIES:
        raise HTTPException(status_code=400, detail=f"Invalid city: {job_config.city}")
    
    if job_config.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {job_config.category}")
    
    # Check for existing running jobs
    result = await db.execute(
        select(ScrapingJob).where(ScrapingJob.status == "running")
    )
    running_jobs = result.scalars().all()
    
    if len(running_jobs) >= 3:
        raise HTTPException(
            status_code=429,
            detail="Too many running jobs. Please wait for existing jobs to complete."
        )
    
    # Create job record
    job = ScrapingJob(
        status="pending",
        created_at=datetime.now()
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    # Start background task
    job_id = str(job.job_id)
    
    # Create background task that will run the scraping
    # Store a placeholder to track active jobs
    active_tasks[job_id] = {"status": "starting"}
    
    # Use background_tasks to run the job
    background_tasks.add_task(
        run_scraping_job,
        job_id,
        job_config.city,
        job_config.category,
        job_config.max_pages,
        job_config.download_images,
        settings.database_url
    )
    
    return ScrapingJobResponse(
        id=job.id,
        job_id=job_id,
        status="pending",
        created_at=job.created_at
    )


@router.get("/jobs", response_model=ScrapingJobList)
async def get_scraping_jobs(
    status: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Get list of scraping jobs"""
    query = select(ScrapingJob).order_by(ScrapingJob.created_at.desc())
    
    if status:
        query = query.where(ScrapingJob.status == status)
    
    query = query.limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return ScrapingJobList(
        items=[ScrapingJobResponse(
            id=j.id,
            job_id=str(j.job_id),
            city_id=j.city_id,
            category_id=j.category_id,
            status=j.status,
            total_pages=j.total_pages,
            scraped_pages=j.scraped_pages,
            total_items=j.total_items,
            scraped_items=j.scraped_items,
            new_items=j.new_items,
            updated_items=j.updated_items,
            failed_items=j.failed_items,
            error_message=j.error_message,
            progress=j.progress,
            started_at=j.started_at,
            completed_at=j.completed_at,
            created_at=j.created_at
        ) for j in jobs],
        total=len(jobs)
    )


@router.get("/jobs/{job_id}", response_model=ScrapingJobResponse)
async def get_scraping_job(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get scraping job status"""
    result = await db.execute(
        select(ScrapingJob).where(ScrapingJob.job_id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return ScrapingJobResponse(
        id=job.id,
        job_id=str(job.job_id),
        city_id=job.city_id,
        category_id=job.category_id,
        status=job.status,
        total_pages=job.total_pages,
        scraped_pages=job.scraped_pages,
        total_items=job.total_items,
        scraped_items=job.scraped_items,
        new_items=job.new_items,
        updated_items=job.updated_items,
        failed_items=job.failed_items,
        error_message=job.error_message,
        progress=job.progress,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_scraping_job(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Cancel a running scraping job"""
    result = await db.execute(
        select(ScrapingJob).where(ScrapingJob.job_id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "running":
        raise HTTPException(status_code=400, detail="Job is not running")
    
    job.status = "cancelled"
    job.completed_at = datetime.now()
    await db.commit()
    
    # Remove from active tasks tracking
    # The scraper will check job status in the database and stop
    if job_id in active_tasks:
        del active_tasks[job_id]
        logger.info(f"Job {job_id} marked for cancellation")
    
    return {"message": "Job cancelled successfully"}


@router.get("/cities")
async def get_available_cities():
    """Get list of available cities for scraping"""
    return [
        {"slug": slug, "name": info["name"], "province": info["province"]}
        for slug, info in CITIES.items()
    ]


@router.get("/categories")
async def get_available_categories():
    """Get list of available categories for scraping"""
    return [
        {"slug": slug, "name": info["name"], "type": info["type"]}
        for slug, info in CATEGORIES.items()
    ]


from pydantic import BaseModel

class SingleScrapeRequest(BaseModel):
    url: str

@router.post("/scrape-single")
async def scrape_single_property(
    request: SingleScrapeRequest,
    db: AsyncSession = Depends(get_db)
):
    """Scrape a single property by URL"""
    url = request.url
    
    if "divar.ir/v/" not in url:
        raise HTTPException(status_code=400, detail="Invalid Divar property URL")
    
    scraper = DivarScraper(
        db_session=db,
        proxy_enabled=settings.proxy_enabled,
        headless=settings.scraper_headless
    )
    
    try:
        await scraper.initialize()
        property_data = await scraper.scrape_property_detail(url)
        
        if property_data:
            saved = await scraper.save_property(property_data)
            if saved:
                return {"success": True, "property": saved.to_dict()}
        
        return {"success": False, "message": "Failed to scrape property"}
        
    finally:
        await scraper.close()


@router.get("/active-tasks")
async def get_active_tasks():
    """Get list of currently active scraping tasks"""
    return {
        "active_count": len(active_tasks),
        "task_ids": list(active_tasks.keys())
    }
