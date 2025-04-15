import os
import sys

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from utils.database import init_db, db_manager
from utils.logger import logger
# Import models so SQLAlchemy knows about them
from models.whitelist import WhitelistedUser

def main():
    """Initialize database tables"""
    try:
        logger.info("Initializing database tables...")
        init_db()
        logger.info("Database tables created successfully")
        
        # Migrate existing whitelist data from Redis to PostgreSQL if any exists
        redis_data = db_manager.get_cache('controlbot:whitelist')
        if redis_data:
            logger.info("Found existing whitelist data in Redis, migrating to PostgreSQL...")
            from utils.whitelist import whitelist_manager
            whitelist_manager._save_whitelist()  # This will save to both PostgreSQL and Redis
            logger.info("Migration completed successfully")
    
    except Exception as e:
        logger.error("Failed to initialize database: {0}".format(str(e)), exc_info=True)
        raise

if __name__ == "__main__":
    main() 