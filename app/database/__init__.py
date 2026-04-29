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

# Clean up 'sslmode' from URL as it's not supported by asyncpg in the connection string
# This is common on platforms like Render/Heroku
connect_args = {}
if "sslmode" in ASYNC_DATABASE_URL:
    import re
    # Remove sslmode=... from the URL string
    ASYNC_DATABASE_URL = re.sub(r"[?&]sslmode=[^&]*", "", ASYNC_DATABASE_URL)
    # If we removed a param that was at the start, we might have ? replaced by nothing but followed by &
    # Ensure the URL still has a ? if there are other params left
    if "?" not in ASYNC_DATABASE_URL and "=" in ASYNC_DATABASE_URL.split("/")[-1]:
         ASYNC_DATABASE_URL = ASYNC_DATABASE_URL.replace("&", "?", 1)
    
    # For asyncpg on Render, we need SSL.
    # We use a custom SSL context to allow self-signed certificates (common on managed DBs)
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ctx

# create_async_engine is the async version of create_engine
engine = create_async_engine(
    ASYNC_DATABASE_URL, 
    echo=False,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    connect_args=connect_args
)

# async_sessionmaker returns an AsyncSession
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
Base = declarative_base()

# ฟังก์ชันสำหรับให้ FastAPI ดึง Database Session ไปใช้แบบ Async
async def get_db():
    async with SessionLocal() as db:
        yield db
