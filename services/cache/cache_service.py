from typing import Optional, Any, Dict
import aioredis
import json
import hashlib
from datetime import timedelta
from loguru import logger

class CacheService:
    """Redis-based caching service for web scraping results"""
    
    def __init__(self, redis_url: str = "redis://redis:6379"):
        """Initialize cache service"""
        self.redis = None
        self.redis_url = redis_url
        self.default_ttl = timedelta(hours=24)  # Default cache TTL

    async def connect(self):
        """Establish Redis connection"""
        if not self.redis:
            try:
                self.redis = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                logger.info("Successfully connected to Redis")
            except Exception as e:
                logger.error(f"Redis connection failed: {str(e)}")
                raise

    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            self.redis = None

    def _generate_cache_key(self, url: str, options: Dict[str, Any]) -> str:
        """Generate unique cache key based on URL and scraping options"""
        # Create a string combining URL and relevant options
        cache_key_parts = [url]
        
        # Add relevant options that affect content
        relevant_options = {
            'onlyMainContent': options.get('only_main', True),
            'waitFor': options.get('wait_for_selector'),
            'mobile': options.get('mobile', False),
            'includeScreenshot': options.get('include_screenshot', False),
            'includeRawHtml': options.get('include_raw_html', False)
        }
        
        cache_key_parts.append(json.dumps(relevant_options, sort_keys=True))
        
        # Generate hash
        key_string = '|'.join(str(part) for part in cache_key_parts)
        return f"scrape:{hashlib.sha256(key_string.encode()).hexdigest()}"

    async def get_cached_result(self, url: str, options: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Retrieve cached scraping result"""
        if not self.redis:
            await self.connect()
            
        try:
            cache_key = self._generate_cache_key(url, options)
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                logger.info(f"Cache hit for URL: {url}")
                return json.loads(cached_data)
            
            logger.info(f"Cache miss for URL: {url}")
            return None
            
        except Exception as e:
            logger.warning(f"Error retrieving from cache: {str(e)}")
            return None

    async def cache_result(self, url: str, options: Dict[str, Any], 
                          result: Dict[str, Any], ttl: Optional[timedelta] = None) -> bool:
        """Cache scraping result"""
        if not self.redis:
            await self.connect()
            
        try:
            cache_key = self._generate_cache_key(url, options)
            ttl = ttl or self.default_ttl
            
            # Store result
            await self.redis.set(
                cache_key,
                json.dumps(result),
                ex=int(ttl.total_seconds())
            )
            
            logger.info(f"Successfully cached result for URL: {url}")
            return True
            
        except Exception as e:
            logger.error(f"Error caching result: {str(e)}")
            return False

    async def invalidate_cache(self, url: str, options: Dict[str, Any]) -> bool:
        """Invalidate cached result for specific URL and options"""
        if not self.redis:
            await self.connect()
            
        try:
            cache_key = self._generate_cache_key(url, options)
            await self.redis.delete(cache_key)
            logger.info(f"Invalidated cache for URL: {url}")
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")
            return False