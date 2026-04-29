from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import DATABASE_URL
import json

# SQLAlchemy async with PostgreSQL requires 'asyncpg' driver instead of the default one
# Some platforms (like Render/Heroku) provide DATABASE_URL starting with 'postgres://'
# SQLAlchemy 1.4+ requires 'postgresql://' and for async we need 'postgresql+asyncpg://'
if DATABASE_URL.startswith("postgres://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# create_async_engine is the async version of create_engine
engine = create_async_engine(ASYNC_DATABASE_URL, echo=False,json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False))

# async_sessionmaker returns an AsyncSession
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
Base = declarative_base()

# ฟังก์ชันสำหรับให้ FastAPI ดึง Database Session ไปใช้แบบ Async
async def get_db():
    async with SessionLocal() as db:
        yield db
