import yaml
import os
from pathlib import Path
from typing import Dict, Any

class Config:
    """配置管理类"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            # 默认查找 config/config.yaml
            config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载YAML配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分隔的键"""
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_database_url(self) -> str:
        """获取数据库连接URL"""
        mysql = self.get('database.mysql')
        return f"mysql+pymysql://{mysql['username']}:{mysql['password']}@{mysql['host']}:{mysql['port']}/{mysql['database']}?charset={mysql['charset']}"
    
    def get_redis_url(self) -> str:
        """获取Redis连接URL"""
        redis = self.get('database.redis')
        if redis['password']:
            return f"redis://:{redis['password']}@{redis['host']}:{redis['port']}/{redis['db']}"
        return f"redis://{redis['host']}:{redis['port']}/{redis['db']}"
    
    def get_mysql_config(self) -> Dict[str, Any]:
        """获取MySQL配置"""
        return self.get('database.mysql', {})
    
    def get_redis_config(self) -> Dict[str, Any]:
        """获取Redis配置"""
        return self.get('database.redis', {})
    
    def get_jwt_config(self) -> Dict[str, Any]:
        """获取JWT配置"""
        return self.get('app.jwt', {})
    
    def get_app_config(self) -> Dict[str, Any]:
        """获取应用配置"""
        return self.get('app', {})

# 全局配置实例
config = Config()
