from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
import re
import hashlib
from sqlalchemy.orm import Session
from .database import get_db
from .config import config
from .cache import cache_manager
import logging

logger = logging.getLogger(__name__)

# 密码加密上下文
# 使用sha256_crypt作为主要方案，bcrypt作为备选方案
pwd_context = CryptContext(schemes=["sha256_crypt", "bcrypt"], deprecated="auto")

# OAuth2 密码承载者（与路由前缀一致）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v/user/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """获取密码哈希值"""
    return pwd_context.hash(password)

def authenticate_user(db: Session, username: str, password: str):
    """验证用户，兼容并自动升级旧系统MD5密码。

    - 先使用当前算法校验（sha256_crypt/bcrypt）
    - 若失败且存储格式为 md5$<hex> 或 32位hex，则按MD5校验；成功则升级为新哈希并保存
    """
    from .admin.models import User

    def _is_plain_md5_hex(s: str) -> bool:
        return bool(s) and len(s) == 32 and re.fullmatch(r"[0-9a-fA-F]{32}", s) is not None

    def _md5_hex(plain: str) -> str:
        return hashlib.md5(plain.encode("utf-8")).hexdigest()

    def _legacy_md5_with_salt(plain: str, salt: str) -> str:
        # 等价于 PHP: md5(md5($text) . $salt)
        inner = _md5_hex(plain)
        return hashlib.md5((inner + salt).encode("utf-8")).hexdigest()

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False

    # 1) 现行算法校验（忽略未知哈希错误，继续尝试旧算法）
    try:
        if verify_password(password, user.password):
            return user
    except Exception:
        pass

    # 2) 兼容旧MD5
    stored = user.password or ""
    legacy = None
    if stored.startswith("md5$"):
        legacy = stored.split("$", 1)[1].strip()
    elif _is_plain_md5_hex(stored):
        legacy = stored

    if legacy:
        # 优先按旧系统加盐算法校验
        LEGACY_SALT = "api"
        if _legacy_md5_with_salt(password, LEGACY_SALT).lower() == legacy.lower() or _md5_hex(password).lower() == legacy.lower():
            # 升级为新算法哈希
            try:
                new_hash = get_password_hash(password)
                user.password = new_hash
                db.commit()
            except Exception:
                db.rollback()
            return user

    return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建访问令牌并存储到Redis"""
    jwt_config = config.get_jwt_config()
    secret_key = jwt_config.get('secret_key')
    algorithm = jwt_config.get('algorithm', 'HS256')
    
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=jwt_config.get('access_token_expire_minutes', 30))
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=algorithm)
    
    # 将token存储到Redis中
    username = data.get("sub")
    if username:
        # 计算token过期时间（秒）
        ttl = int((expire - datetime.utcnow()).total_seconds())
        # 存储token到Redis，key格式：token:{username}
        cache_manager.set(f"token:{username}", encoded_jwt, ttl)
        logger.info(f"Token已存储到Redis: {username}")
    
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """获取当前用户（从Redis验证token）"""
    jwt_config = config.get_jwt_config()
    secret_key = jwt_config.get('secret_key')
    algorithm = jwt_config.get('algorithm', 'HS256')
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无法验证凭据",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 从Redis中验证token是否存在
        redis_token = cache_manager.get(f"token:{username}")
        if redis_token != token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token已失效，请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    from .admin.models import User
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def revoke_token(username: str) -> bool:
    """撤销用户token（登出）"""
    try:
        # 从Redis中删除token
        cache_manager.delete(f"token:{username}")
        logger.info(f"Token已从Redis删除: {username}")
        return True
    except Exception as e:
        logger.error(f"删除Token失败: {e}")
        return False

def verify_api_key(api_key: str = Query(..., description="API访问密钥"), db: Session = Depends(get_db)):
    """验证API密钥并返回订阅信息"""
    from .admin import crud
    from datetime import datetime
    
    # 1. 检查API密钥格式
    if not api_key or len(api_key.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API密钥不能为空",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # 2. 查找订阅记录
    subscription = crud.SubscriptionCRUD.get_by_api_key(db, api_key)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API密钥不存在",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # 3. 检查订阅状态
    if subscription.status != "active":
        status_messages = {
            "expired": "订阅已过期",
            "cancelled": "订阅已取消",
            "suspended": "订阅已暂停"
        }
        message = status_messages.get(subscription.status, f"订阅状态异常: {subscription.status}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # 4. 检查订阅是否到期
    current_time = datetime.utcnow()
    if subscription.end_date <= current_time:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"订阅已于 {subscription.end_date.strftime('%Y-%m-%d %H:%M:%S')} 到期",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # 5. 检查用户状态
    if not subscription.user or not subscription.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户账户已被禁用",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # 6. 检查API是否可用
    if not subscription.api or not subscription.api.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API接口不可用",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # 7. 检查调用次数限制（如果有）
    if subscription.remaining_calls is not None and subscription.remaining_calls <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="API调用次数已用完",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return subscription

def get_current_active_user(current_user = Depends(get_current_user)):
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="用户已被禁用"
        )
    return current_user

def get_current_admin_user(current_user = Depends(get_current_user)):
    """获取当前管理员用户"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="权限不足，需要管理员权限"
        )
    return current_user

def get_current_user_or_admin(current_user = Depends(get_current_user)):
    """获取当前用户或管理员用户（管理员可以访问所有模块，普通用户只能访问用户模块）"""
    return current_user

def get_user_module_access(current_user = Depends(get_current_user)):
    """获取用户模块访问权限（管理员和普通用户都可以访问）"""
    return current_user

def get_admin_module_access(current_user = Depends(get_current_user)):
    """获取管理员模块访问权限（仅管理员可以访问）"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="权限不足，需要管理员权限"
        )
    return current_user

def get_admin_only(current_user = Depends(get_current_user)):
    """仅管理员可访问（用于admin模块的严格权限控制）"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="权限不足，需要管理员权限"
        )
    return current_user

def check_api_permission(user_id: int, api_id: int, db: Session):
    """检查用户是否有权限访问API"""
    from .admin.models import Subscription, API
    
    # 检查用户是否有有效的订阅
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.api_id == api_id,
        Subscription.is_active == True,
        Subscription.expires_at > datetime.utcnow()
    ).first()
    
    return bool(subscription)
