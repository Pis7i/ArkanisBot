import os
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import redis
from redis import Redis
from contextlib import contextmanager
from dotenv import load_dotenv
from utils.logger import logger

# Load environment variables
load_dotenv()

# SQLAlchemy setup
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

logger.info(f"Initializing database with URL: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis setup
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client: Optional[Redis] = None

def get_redis() -> Redis:
    """Get or create Redis connection"""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

@contextmanager
def get_db() -> Session:
    """Database session context manager"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    logger.info("Creating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {str(e)}")
        raise

class DatabaseManager:
    def __init__(self):
        self.redis = get_redis()
        self.engine = engine
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return SessionLocal()
    
    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations"""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def set_cache(self, key: str, value: str, expire: int = 3600):
        """Set a value in Redis cache"""
        self.redis.set(key, value, ex=expire)
    
    def get_cache(self, key: str) -> Optional[str]:
        """Get a value from Redis cache"""
        return self.redis.get(key)
    
    def delete_cache(self, key: str):
        """Delete a value from Redis cache"""
        self.redis.delete(key)
    
    def clear_cache(self, pattern: str = "*"):
        """Clear all cache entries matching pattern"""
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)

# Create a default database manager instance
db_manager = DatabaseManager() 