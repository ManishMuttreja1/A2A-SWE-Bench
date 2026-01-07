"""Caching layer for synthesis engine"""

import json
import hashlib
import time
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import aiofiles
import redis.asyncio as redis
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class CachedFix:
    """Represents a cached fix for an error"""
    error_hash: str
    fix_type: str
    fix_commands: List[str]
    success_rate: float
    last_used: float
    use_count: int
    metadata: Dict[str, Any]


class SynthesisCache:
    """
    Intelligent caching for synthesis engine fixes.
    Stores successful fixes and patterns for reuse.
    """
    
    def __init__(
        self,
        cache_dir: Path = Path("/tmp/synthesis_cache"),
        redis_url: Optional[str] = "redis://localhost:6379",
        ttl_hours: int = 168  # 1 week
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.redis_url = redis_url
        self.ttl_hours = ttl_hours
        
        # Redis client for distributed cache
        self.redis_client: Optional[redis.Redis] = None
        
        # Local memory cache for fast access
        self.memory_cache: Dict[str, CachedFix] = {}
        
        # Pattern database for ML-based matching
        self.error_patterns: Dict[str, List[str]] = {}
        
        # Statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "saves": 0,
            "evictions": 0
        }
    
    async def initialize(self):
        """Initialize cache connections"""
        try:
            if self.redis_url:
                self.redis_client = await redis.from_url(self.redis_url)
                await self.redis_client.ping()
                logger.info("Redis cache connected")
        except Exception as e:
            logger.warning(f"Redis unavailable, using local cache only: {e}")
            self.redis_client = None
        
        # Load local cache
        await self._load_local_cache()
    
    async def _load_local_cache(self):
        """Load cache from disk"""
        cache_file = self.cache_dir / "synthesis_cache.json"
        
        if cache_file.exists():
            try:
                async with aiofiles.open(cache_file, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)
                    
                    for key, value in data.items():
                        self.memory_cache[key] = CachedFix(**value)
                    
                    logger.info(f"Loaded {len(self.memory_cache)} cached fixes")
            except Exception as e:
                logger.error(f"Failed to load cache: {e}")
    
    async def save_cache(self):
        """Persist cache to disk"""
        cache_file = self.cache_dir / "synthesis_cache.json"
        
        try:
            # Convert to serializable format
            data = {
                key: asdict(fix) 
                for key, fix in self.memory_cache.items()
            }
            
            async with aiofiles.open(cache_file, 'w') as f:
                await f.write(json.dumps(data, indent=2))
            
            logger.info(f"Saved {len(self.memory_cache)} fixes to cache")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def _compute_error_hash(self, error_text: str) -> str:
        """Compute hash for error text"""
        # Normalize error text
        normalized = self._normalize_error(error_text)
        
        # Compute hash
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
    
    def _normalize_error(self, error_text: str) -> str:
        """Normalize error text for better matching"""
        import re
        
        # Remove file paths
        normalized = re.sub(r'/[\w/\-\.]+', '/PATH', error_text)
        
        # Remove version numbers
        normalized = re.sub(r'\d+\.\d+\.\d+', 'VERSION', normalized)
        
        # Remove timestamps
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', normalized)
        
        # Remove line numbers
        normalized = re.sub(r'line \d+', 'line N', normalized)
        
        # Lowercase and strip
        normalized = normalized.lower().strip()
        
        return normalized
    
    async def get_fix(
        self,
        error_text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached fix for an error.
        
        Args:
            error_text: Error message
            context: Additional context (repo, language, etc.)
            
        Returns:
            Cached fix or None
        """
        error_hash = self._compute_error_hash(error_text)
        
        # Check memory cache first
        if error_hash in self.memory_cache:
            fix = self.memory_cache[error_hash]
            
            # Check if expired
            if self._is_expired(fix):
                del self.memory_cache[error_hash]
                self.stats["evictions"] += 1
                return None
            
            # Update usage
            fix.last_used = time.time()
            fix.use_count += 1
            
            self.stats["hits"] += 1
            logger.debug(f"Cache hit for error hash {error_hash}")
            
            return {
                "type": fix.fix_type,
                "commands": fix.fix_commands,
                "confidence": fix.success_rate,
                "metadata": fix.metadata
            }
        
        # Check Redis if available
        if self.redis_client:
            redis_fix = await self._get_from_redis(error_hash)
            if redis_fix:
                # Add to memory cache
                self.memory_cache[error_hash] = redis_fix
                self.stats["hits"] += 1
                return {
                    "type": redis_fix.fix_type,
                    "commands": redis_fix.fix_commands,
                    "confidence": redis_fix.success_rate,
                    "metadata": redis_fix.metadata
                }
        
        # Try pattern matching
        pattern_fix = await self._find_pattern_match(error_text)
        if pattern_fix:
            self.stats["hits"] += 1
            return pattern_fix
        
        self.stats["misses"] += 1
        return None
    
    async def save_fix(
        self,
        error_text: str,
        fix: Dict[str, Any],
        success: bool,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Save a successful fix to cache.
        
        Args:
            error_text: Original error
            fix: Fix that was applied
            success: Whether fix was successful
            context: Additional context
        """
        if not success:
            return  # Only cache successful fixes
        
        error_hash = self._compute_error_hash(error_text)
        
        # Create or update cached fix
        if error_hash in self.memory_cache:
            cached = self.memory_cache[error_hash]
            # Update success rate
            cached.success_rate = (
                (cached.success_rate * cached.use_count + 1) /
                (cached.use_count + 1)
            )
            cached.use_count += 1
            cached.last_used = time.time()
        else:
            cached = CachedFix(
                error_hash=error_hash,
                fix_type=fix.get("type", "unknown"),
                fix_commands=fix.get("commands", []),
                success_rate=1.0,
                last_used=time.time(),
                use_count=1,
                metadata=context or {}
            )
            self.memory_cache[error_hash] = cached
        
        # Save to Redis if available
        if self.redis_client:
            await self._save_to_redis(error_hash, cached)
        
        # Update patterns
        await self._update_patterns(error_text, error_hash)
        
        self.stats["saves"] += 1
        
        # Persist to disk periodically
        if self.stats["saves"] % 10 == 0:
            await self.save_cache()
    
    async def _get_from_redis(self, error_hash: str) -> Optional[CachedFix]:
        """Get fix from Redis cache"""
        try:
            key = f"synthesis:fix:{error_hash}"
            data = await self.redis_client.get(key)
            
            if data:
                fix_data = json.loads(data)
                return CachedFix(**fix_data)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
        
        return None
    
    async def _save_to_redis(self, error_hash: str, fix: CachedFix):
        """Save fix to Redis cache"""
        try:
            key = f"synthesis:fix:{error_hash}"
            data = json.dumps(asdict(fix))
            
            # Set with TTL
            await self.redis_client.setex(
                key,
                self.ttl_hours * 3600,
                data
            )
        except Exception as e:
            logger.error(f"Redis save error: {e}")
    
    async def _find_pattern_match(
        self,
        error_text: str,
        threshold: float = 0.7
    ) -> Optional[Dict[str, Any]]:
        """Find similar error patterns"""
        normalized = self._normalize_error(error_text)
        
        # Simple pattern matching (could be enhanced with ML)
        best_match = None
        best_score = 0.0
        
        for pattern_hash, patterns in self.error_patterns.items():
            for pattern in patterns:
                score = self._calculate_similarity(normalized, pattern)
                
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = pattern_hash
        
        if best_match and best_match in self.memory_cache:
            fix = self.memory_cache[best_match]
            return {
                "type": fix.fix_type,
                "commands": fix.fix_commands,
                "confidence": fix.success_rate * best_score,
                "metadata": {
                    **fix.metadata,
                    "pattern_match": True,
                    "similarity": best_score
                }
            }
        
        return None
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two error texts"""
        # Simple Jaccard similarity
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    async def _update_patterns(self, error_text: str, error_hash: str):
        """Update error patterns database"""
        normalized = self._normalize_error(error_text)
        
        if error_hash not in self.error_patterns:
            self.error_patterns[error_hash] = []
        
        if normalized not in self.error_patterns[error_hash]:
            self.error_patterns[error_hash].append(normalized)
            
            # Limit pattern storage
            if len(self.error_patterns[error_hash]) > 10:
                self.error_patterns[error_hash].pop(0)
    
    def _is_expired(self, fix: CachedFix) -> bool:
        """Check if cached fix is expired"""
        age_hours = (time.time() - fix.last_used) / 3600
        return age_hours > self.ttl_hours
    
    async def cleanup(self):
        """Clean up expired entries"""
        expired = []
        
        for key, fix in self.memory_cache.items():
            if self._is_expired(fix):
                expired.append(key)
        
        for key in expired:
            del self.memory_cache[key]
            self.stats["evictions"] += 1
            
            # Remove from Redis
            if self.redis_client:
                try:
                    await self.redis_client.delete(f"synthesis:fix:{key}")
                except Exception:
                    pass
        
        logger.info(f"Cleaned up {len(expired)} expired entries")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = self.stats["hits"] / total_requests if total_requests > 0 else 0
        
        return {
            **self.stats,
            "hit_rate": hit_rate,
            "cache_size": len(self.memory_cache),
            "pattern_count": len(self.error_patterns),
            "redis_available": self.redis_client is not None
        }
    
    async def close(self):
        """Close cache connections"""
        # Save cache before closing
        await self.save_cache()
        
        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()