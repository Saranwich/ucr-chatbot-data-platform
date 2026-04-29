import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func
from app.models import CompletedReport
from app.database import ASYNC_DATABASE_URL
from geoalchemy2.functions import ST_AsText

async def check_db():
    engine = create_async_engine(ASYNC_DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Test generic fetch
        result = await session.execute(select(
            CompletedReport.report_id, 
            CompletedReport.created_at, 
            ST_AsText(CompletedReport.location_data).label("loc")
        ).limit(10))
        reports = result.all()
        print(f"Total reports found (no filter): {len(reports)}")
        
        # Test date filter
        today = "2026-04-30"
        target_date = datetime.strptime(today, "%Y-%m-%d").date()
        filter_query = select(CompletedReport.report_id).where(func.date(CompletedReport.created_at) == target_date)
        filter_result = await session.execute(filter_query)
        filtered = filter_result.all()
        print(f"Reports found for {today}: {len(filtered)}")

if __name__ == "__main__":
    from datetime import datetime
    asyncio.run(check_db())
