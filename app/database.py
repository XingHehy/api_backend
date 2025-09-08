from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from redis import Redis
from typing import Generator
import logging
from .config import config
import threading
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量
_engine = None
_session_factory = None
_redis_client = None
_lock = threading.Lock()

# 创建基础模型类
Base = declarative_base()

class DatabaseManager:
    """数据库连接管理器 - 单例模式"""
    
    def __new__(cls):
        if not hasattr(cls, '_instance'):
            with _lock:
                if not hasattr(cls, '_instance'):
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._engine = None
            self._session_factory = None
            self._initialized = True
    
    def get_engine(self):
        """获取数据库引擎 - 单例"""
        global _engine
        if _engine is None:
            with _lock:
                if _engine is None:
                    try:
                        database_url = config.get_database_url()
                        mysql_config = config.get_mysql_config()
                        
                        _engine = create_engine(
                            database_url,
                            pool_size=mysql_config.get('pool_size', 10),
                            max_overflow=mysql_config.get('max_overflow', 20),
                            pool_timeout=mysql_config.get('pool_timeout', 30),
                            pool_recycle=mysql_config.get('pool_recycle', 3600),
                            echo=mysql_config.get('echo', False),
                            pool_pre_ping=True  # 连接前ping测试
                        )
                        logger.info("MySQL数据库引擎创建成功")
                    except Exception as e:
                        logger.error(f"MySQL数据库引擎创建失败: {e}")
                        raise
        return _engine
    
    def get_session_factory(self):
        """获取会话工厂 - 单例"""
        global _session_factory
        if _session_factory is None:
            with _lock:
                if _session_factory is None:
                    engine = self.get_engine()
                    _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                    logger.info("数据库会话工厂创建成功")
        return _session_factory
    
    def create_session(self) -> Session:
        """创建新的数据库会话"""
        factory = self.get_session_factory()
        return factory()
    
    def dispose(self):
        """释放数据库连接"""
        global _engine, _session_factory
        with _lock:
            if _engine:
                _engine.dispose()
                _engine = None
                _session_factory = None
                logger.info("数据库连接已释放")

class RedisManager:
    """Redis连接管理器 - 单例模式"""
    
    def __new__(cls):
        if not hasattr(cls, '_instance'):
            with _lock:
                if not hasattr(cls, '_instance'):
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._redis_client = None
            self._initialized = True
    
    def get_client(self) -> Redis:
        """获取Redis客户端 - 单例"""
        if self._redis_client is None:
            with _lock:
                if self._redis_client is None:
                    try:
                        redis_config = config.get_redis_config()
                        self._redis_client = Redis(
                            host=redis_config.get('host', 'localhost'),
                            port=redis_config.get('port', 6379),
                            db=redis_config.get('db', 0),
                            password=redis_config.get('password'),
                            decode_responses=True,  # 自动解码响应
                            socket_connect_timeout=5,
                            socket_timeout=5
                        )
                        # 测试连接
                        self._redis_client.ping()
                        logger.info("Redis连接成功")
                    except Exception as e:
                        logger.error(f"Redis连接失败: {e}")
                        raise
        return self._redis_client
    
    def close(self):
        """关闭Redis连接"""
        with _lock:
            if self._redis_client:
                self._redis_client.close()
                self._redis_client = None
                logger.info("Redis连接已关闭")

# 全局管理器实例
db_manager = DatabaseManager()
redis_manager = RedisManager()

def get_db() -> Generator[Session, None, None]:
    """获取数据库会话 - 依赖注入"""
    session = db_manager.create_session()
    try:
        yield session
    finally:
        session.close()

def get_redis() -> Redis:
    """获取Redis客户端 - 依赖注入"""
    return redis_manager.get_client()

def init_db():
    """初始化数据库，创建所有表"""
    try:
        # 导入所有模型以确保它们被注册
        from .admin import models as admin_models
        
        # 创建所有表
        engine = db_manager.get_engine()
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表创建成功")
    except Exception as e:
        logger.error(f"数据库表创建失败: {e}")
        raise

def close_db():
    """关闭数据库连接"""
    try:
        db_manager.dispose()
        redis_manager.close()
        logger.info("所有数据库连接已关闭")
    except Exception as e:
        logger.error(f"关闭数据库连接失败: {e}")

def health_check():
    """健康检查"""
    mysql_status = "disconnected"
    redis_status = "disconnected"
    overall_status = "unhealthy"
    errors = []
    
    # 检查MySQL
    try:
        engine = db_manager.get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        mysql_status = "connected"
        logger.info("MySQL连接检查成功")
    except Exception as e:
        error_msg = f"MySQL连接失败: {e}"
        logger.error(error_msg)
        errors.append(error_msg)
    
    # 检查Redis
    try:
        redis_client = redis_manager.get_client()
        redis_client.ping()
        redis_status = "connected"
        logger.info("Redis连接检查成功")
    except Exception as e:
        error_msg = f"Redis连接失败: {e}"
        logger.error(error_msg)
        errors.append(error_msg)
    
    # 确定整体状态
    if mysql_status == "connected" and redis_status == "connected":
        overall_status = "healthy"
    elif mysql_status == "connected" or redis_status == "connected":
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"
    
    result = {
        "status": overall_status,
        "mysql": mysql_status,
        "redis": redis_status,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    if errors:
        result["errors"] = errors
    
    return result
