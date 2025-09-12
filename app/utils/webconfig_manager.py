#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网站配置管理器
提供便捷的配置获取和设置方法
"""

from typing import Any, Optional, Dict
from app.database import get_db
from app.admin.crud import WebConfigCRUD
import logging
import json

logger = logging.getLogger(__name__)

class WebConfigManager:
    """网站配置管理器"""
    
    @staticmethod
    def get(key: str, default: Any = None, convert_type: type = str) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            convert_type: 转换类型 (str, int, float, bool, list, dict)
        
        Returns:
            配置值
        """
        try:
            db = next(get_db())
            value = WebConfigCRUD.get_config(db, key, str(default) if default is not None else None)
            db.close()
            
            if value is None:
                return default
            
            # 类型转换
            if convert_type == str:
                return value
            elif convert_type == int:
                return int(value)
            elif convert_type == float:
                return float(value)
            elif convert_type == bool:
                return value.lower() in ('true', '1', 'yes', 'on')
            elif convert_type == list:
                try:
                    return json.loads(value) if value else []
                except json.JSONDecodeError:
                    return []
            elif convert_type == dict:
                try:
                    return json.loads(value) if value else {}
                except json.JSONDecodeError:
                    return {}
            else:
                return value
                
        except Exception as e:
            logger.error(f"获取配置失败 {key}: {e}")
            return default
    
    @staticmethod
    def set(key: str, value: Any) -> bool:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
        
        Returns:
            是否成功
        """
        try:
            # 将值转换为字符串
            if isinstance(value, (list, dict)):
                str_value = json.dumps(value, ensure_ascii=False)
            else:
                str_value = str(value)
            
            db = next(get_db())
            WebConfigCRUD.set_config(db, key, str_value)
            db.close()
            return True
        except Exception as e:
            logger.error(f"设置配置失败 {key}: {e}")
            return False
    
    @staticmethod
    def get_all() -> Dict[str, str]:
        """获取所有配置"""
        try:
            db = next(get_db())
            configs = WebConfigCRUD.get_all_dict(db)
            db.close()
            return configs
        except Exception as e:
            logger.error(f"获取所有配置失败: {e}")
            return {}
    
    @staticmethod
    def delete(key: str) -> bool:
        """删除配置"""
        try:
            db = next(get_db())
            success = WebConfigCRUD.delete_by_key(db, key)
            db.close()
            return success
        except Exception as e:
            logger.error(f"删除配置失败 {key}: {e}")
            return False
    
    @staticmethod
    def exists(key: str) -> bool:
        """检查配置是否存在"""
        try:
            db = next(get_db())
            config = WebConfigCRUD.get_by_key(db, key)
            db.close()
            return config is not None
        except Exception as e:
            logger.error(f"检查配置存在性失败 {key}: {e}")
            return False

# 便捷的配置获取方法
def get_config(key: str, default: Any = None, convert_type: type = str) -> Any:
    """获取配置值的便捷函数"""
    return WebConfigManager.get(key, default, convert_type)

def set_config(key: str, value: Any) -> bool:
    """设置配置值的便捷函数"""
    return WebConfigManager.set(key, value)

def get_all_configs() -> Dict[str, str]:
    """获取所有配置的便捷函数"""
    return WebConfigManager.get_all()

def delete_config(key: str) -> bool:
    """删除配置的便捷函数"""
    return WebConfigManager.delete(key)

def config_exists(key: str) -> bool:
    """检查配置是否存在的便捷函数"""
    return WebConfigManager.exists(key)

# 预定义的配置键常量
class ConfigKeys:
    """配置键常量"""
    
    # 网站配置
    SITE_TITLE = "site.title"
    SITE_DESCRIPTION = "site.description"
    SITE_KEYWORDS = "site.keywords"
    SITE_AUTHOR = "site.author"
    SITE_COPYRIGHT = "site.copyright"
    SITE_ICP = "site.icp"
    SITE_BEIAN = "site.beian"
    SITE_FOUNDED_DATE = "site.founded_date"
    SITE_LAST_UPDATE = "site.last_update"
    
    # 联系信息
    CONTACT_EMAIL = "contact.email"
    CONTACT_PHONE = "contact.phone"
    CONTACT_ADDRESS = "contact.address"
    CONTACT_QQ = "contact.qq"
    CONTACT_WECHAT = "contact.wechat"
    
    # JWT配置
    JWT_SECRET_KEY = "jwt.secret_key"
    JWT_ALGORITHM = "jwt.algorithm"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES = "jwt.access_token_expire_minutes"
    JWT_REFRESH_TOKEN_EXPIRE_DAYS = "jwt.refresh_token_expire_days"
    
    # 安全配置
    SECURITY_BCRYPT_ROUNDS = "security.bcrypt_rounds"
    SECURITY_RATE_LIMIT_PER_MINUTE = "security.rate_limit_per_minute"
    SECURITY_CORS_ORIGINS = "security.cors_origins"
    
    # 系统配置
    SYSTEM_MAINTENANCE_MODE = "system.maintenance_mode"
    SYSTEM_MAINTENANCE_MESSAGE = "system.maintenance_message"
    SYSTEM_REGISTRATION_ENABLED = "system.registration_enabled"
    SYSTEM_REGISTRATION_APPROVAL = "system.registration_approval"
    SYSTEM_DEFAULT_USER_BALANCE = "system.default_user_balance"
    SYSTEM_MAX_API_CALLS_PER_DAY = "system.max_api_calls_per_day"
    SYSTEM_API_BASE_URL = "system.api_base_url"
    
    # 界面配置
    UI_THEME = "ui.theme"
    UI_LOGO = "ui.logo"
    UI_FAVICON = "ui.favicon"
    UI_FOOTER_TEXT = "ui.footer_text"
    UI_SHOW_STATISTICS = "ui.show_statistics"
    UI_SHOW_ANNOUNCEMENTS = "ui.show_announcements"
    
    # 邮件配置
    EMAIL_SMTP_HOST = "email.smtp_host"
    EMAIL_SMTP_PORT = "email.smtp_port"
    EMAIL_SMTP_USERNAME = "email.smtp_username"
    EMAIL_SMTP_PASSWORD = "email.smtp_password"
    EMAIL_SMTP_USE_TLS = "email.smtp_use_tls"
    EMAIL_FROM_EMAIL = "email.from_email"
    EMAIL_FROM_NAME = "email.from_name"
    
    # 缓存配置
    CACHE_DEFAULT_TTL = "cache.default_ttl"
    CACHE_MAX_SIZE = "cache.max_size"
    
    # 文件上传配置
    UPLOAD_MAX_FILE_SIZE = "upload.max_file_size"
    UPLOAD_ALLOWED_EXTENSIONS = "upload.allowed_extensions"
    UPLOAD_UPLOAD_DIR = "upload.upload_dir"
