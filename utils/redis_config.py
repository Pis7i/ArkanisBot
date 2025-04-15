import os
import json
from typing import Optional, Any
from datetime import datetime
from utils.logger import logger
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError

class RedisManager:
    def __init__(self):
        self._redis: Optional[Redis] = None
        self._enabled = False
    
    @property
    def enabled(self) -> bool:
        return self._enabled and self._redis is not None
    
    async def init(self):
        """Initialize Redis connection"""
        try:
            if not os.getenv('REDIS_ENABLED', 'false').lower() == 'true':
                logger.info("Redis is disabled by configuration")
                return

            host = os.getenv('REDIS_HOST', 'localhost')
            port = int(os.getenv('REDIS_PORT', 6379))
            db = int(os.getenv('REDIS_DB', 0))
            
            self._redis = Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True
            )
            
            # Test connection and check persistence
            info = await self._redis.info()
            if info.get("persistence", {}).get("loading") == 0:
                logger.warning("Redis appears to be running without persistence! Old messages may not be cleaned after restart.")
            if not info.get("persistence", {}).get("rdb_last_save_time"):
                logger.warning("No recent RDB saves detected. Redis persistence may not be properly configured.")
                
            self._enabled = True
            logger.info(f"Redis connection established to {host}:{port} db={db}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {str(e)}")
            self._enabled = False
    
    async def get_json(self, key: str) -> Optional[Any]:
        """Get JSON data from Redis"""
        if not self.enabled:
            return None
        try:
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Error getting JSON from Redis for key {key}: {str(e)}")
            return None
    
    async def set_json(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set JSON data in Redis with optional expiry"""
        if not self.enabled:
            return False
        try:
            data = json.dumps(value)
            await self._redis.set(key, data, ex=ex)
            return True
        except Exception as e:
            logger.error(f"Error setting JSON in Redis for key {key}: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a key from Redis"""
        if not self.enabled:
            return False
        try:
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting key {key} from Redis: {str(e)}")
            return False
    
    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            self._enabled = False
            logger.info("Redis connection closed")

# Global Redis manager instance
redis_manager = RedisManager() 