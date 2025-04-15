from redis.asyncio import Redis, ConnectionPool
from typing import Optional
import json
from utils.logger import logger
import os
import aioredis

class RedisManager:
    def __init__(self):
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[Redis] = None
        self._enabled = False
    
    async def init(self):
        """Initialize Redis connection"""
        try:
            if not os.getenv('REDIS_ENABLED', 'false').lower() == 'true':
                logger.info("Redis is disabled by configuration")
                return

            host = os.getenv('REDIS_HOST', 'localhost')
            port = int(os.getenv('REDIS_PORT', 6379))
            db = int(os.getenv('REDIS_DB', 0))
            
            self._redis = aioredis.from_url(
                f"redis://{host}:{port}/{db}",
                encoding="utf-8",
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
    
    async def health_check(self) -> bool:
        """Check Redis connection health"""
        if not self._enabled or not self._redis:
            return False
        
        try:
            await self._redis.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {str(e)}")
            return False
    
    async def shutdown(self):
        """Gracefully close Redis connections"""
        if self._redis:
            await self._redis.close()
            await self._pool.disconnect()
            logger.info("Redis connections closed")
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    @property
    def client(self) -> Optional[Redis]:
        return self._redis if self._enabled else None

    async def set_json(self, key: str, value: dict, ex: Optional[int] = None) -> bool:
        """Store JSON data in Redis with optional expiry"""
        if not self._enabled or not self._redis:
            return False
        
        try:
            await self._redis.set(key, json.dumps(value), ex=ex)
            return True
        except Exception as e:
            logger.error(f"Error setting Redis key {key}: {str(e)}")
            return False
    
    async def get_json(self, key: str) -> Optional[dict]:
        """Get and parse JSON data from Redis"""
        if not self._enabled or not self._redis:
            return None
        
        try:
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Error getting Redis key {key}: {str(e)}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete a key from Redis"""
        if not self._enabled or not self._redis:
            return False
        
        try:
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting Redis key {key}: {str(e)}")
            return False

# Global Redis manager instance
redis_manager = RedisManager() 