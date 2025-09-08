import json
import logging
from typing import Any, Optional, Union
from functools import wraps
from .database import redis_manager
from .config import config

logger = logging.getLogger(__name__)

class CacheManager:
    """Redis缓存管理器 - 使用全局Redis连接"""
    
    def __init__(self):
        self.default_ttl = config.get('app.cache.default_ttl', 3600)
        self.max_size = config.get('app.cache.max_size', 1000)
    
    @property
    def redis(self):
        """获取Redis客户端 - 延迟加载"""
        return redis_manager.get_client()
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            elif not isinstance(value, (str, int, float, bool)):
                value = str(value)
            
            ttl = ttl or self.default_ttl
            return self.redis.setex(key, ttl, value)
        except Exception as e:
            logger.error(f"设置缓存失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存"""
        try:
            value = self.redis.get(key)
            if value is None:
                return default
            
            # 尝试解析JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value.decode('utf-8') if isinstance(value, bytes) else value
        except Exception as e:
            logger.error(f"获取缓存失败: {e}")
            return default
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            return bool(self.redis.delete(key))
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            return bool(self.redis.exists(key))
        except Exception as e:
            logger.error(f"检查缓存失败: {e}")
            return False
    
    def expire(self, key: str, ttl: int) -> bool:
        """设置缓存过期时间"""
        try:
            return bool(self.redis.expire(key, ttl))
        except Exception as e:
            logger.error(f"设置过期时间失败: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """清除匹配模式的缓存"""
        try:
            keys = self.redis.keys(pattern)
            if keys:
                return self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"清除模式缓存失败: {e}")
            return 0
    
    def clear_all(self) -> bool:
        """清除所有缓存"""
        try:
            self.redis.flushdb()
            logger.info("所有缓存已清除")
            return True
        except Exception as e:
            logger.error(f"清除所有缓存失败: {e}")
            return False
    
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        try:
            info = self.redis.info()
            return {
                "total_keys": info.get('db0', {}).get('keys', 0),
                "memory_usage": info.get('used_memory_human', '0B'),
                "connected_clients": info.get('connected_clients', 0),
                "uptime": info.get('uptime_in_seconds', 0)
            }
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {}
    
    def set_hash(self, key: str, field: str, value: Any) -> bool:
        """设置哈希字段"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            return bool(self.redis.hset(key, field, value))
        except Exception as e:
            logger.error(f"设置哈希字段失败: {e}")
            return False
    
    def get_hash(self, key: str, field: str, default: Any = None) -> Any:
        """获取哈希字段"""
        try:
            value = self.redis.hget(key, field)
            if value is None:
                return default
            
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value.decode('utf-8') if isinstance(value, bytes) else value
        except Exception as e:
            logger.error(f"获取哈希字段失败: {e}")
            return default
    
    def get_all_hash(self, key: str) -> dict:
        """获取所有哈希字段"""
        try:
            data = self.redis.hgetall(key)
            result = {}
            for field, value in data.items():
                try:
                    result[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[field] = value.decode('utf-8') if isinstance(value, bytes) else value
            return result
        except Exception as e:
            logger.error(f"获取所有哈希字段失败: {e}")
            return {}

# 全局缓存管理器实例 - 单例
_cache_manager = None

def get_cache_manager() -> CacheManager:
    """获取缓存管理器实例 - 单例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

# 兼容性别名
cache_manager = get_cache_manager()

def cache_result(ttl: Optional[int] = None, key_prefix: str = ""):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # 尝试从缓存获取
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"从缓存获取结果: {cache_key}")
                return cached_result
            
            # 执行函数
            result = await func(*args, **kwargs)
            
            # 缓存结果
            cache_manager.set(cache_key, result, ttl)
            logger.debug(f"结果已缓存: {cache_key}")
            
            return result
        return wrapper
    return decorator

def invalidate_cache(pattern: str):
    """缓存失效装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            # 清除相关缓存
            cache_manager.clear_pattern(pattern)
            logger.debug(f"已清除缓存模式: {pattern}")
            return result
        return wrapper
    return decorator
