"""
简化的API调用记录工具类
只记录核心统计信息：API调用次数和用户使用次数
"""
import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Request
from app.database import get_db
from app.admin import models as admin_models
from app.admin import crud

logger = logging.getLogger(__name__)

def verify_and_record_api_call(
    api_id: int,
    request: Request = None,
    api_key: str = None
) -> admin_models.Subscription:
    """
    验证API密钥并记录API调用统计
    
    Args:
        api_key: API密钥
        api_id: API ID
        
    Returns:
        Subscription: 验证成功的订阅信息
        
    Raises:
        HTTPException: 验证失败时抛出异常
    """
    db = next(get_db())
    
    try:
        # 提取/验证API密钥
        if api_key is None and request is not None:
            api_key = extract_api_key_from_request(request)
        # 验证API密钥和API状态
        subscription = verify_api_key(api_key, api_id, db)
        
        # 记录API调用统计
        record_api_call(api_key, api_id, db)
        
        return subscription
    finally:
        db.close()


def extract_api_key_from_request(request: Request) -> str:
    """从请求中提取 API Key，支持多种传递方式。
    优先级：query(apiKey|api_key) > headers(X-API-KEY) > Authorization: ApiKey <key>
    """
    # 1) Query 参数
    key = request.query_params.get("apiKey") or request.query_params.get("api_key")
    if key and key.strip():
        return key.strip()
    # 2) 自定义请求头
    for header_name in ["x-api-key", "X-API-KEY", "X-Api-Key"]:
        key = request.headers.get(header_name)
        if key and key.strip():
            return key.strip()
    # 3) Authorization 头（格式：ApiKey <key>）
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.strip():
        parts = auth.strip().split()
        if len(parts) == 2 and parts[0].lower() == "apikey":
            return parts[1]
    # 未提供
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API密钥缺失，请在 query(apiKey) 或 Header(X-API-KEY或Authorization) 中提供",
        headers={"WWW-Authenticate": "ApiKey"}
    )

def record_api_call(
    api_key: str,
    api_id: int,
    db: Session
) -> bool:
    """
    记录API调用统计 - 只更新核心计数
    
    Args:
        api_key: API密钥
        api_id: API ID
        db: 数据库会话
        
    Returns:
        bool: 记录是否成功
    """
    try:
        # 根据api_id查找API信息
        api = db.query(admin_models.API).filter(
            admin_models.API.id == api_id
        ).first()
        
        if not api:
            logger.warning(f"未找到API ID对应的接口: {api_id}")
            return False
        
        # 根据api_key查找订阅信息
        subscription = db.query(admin_models.Subscription).filter(
            admin_models.Subscription.api_key == api_key
        ).first()
        
        if not subscription:
            logger.warning(f"未找到API密钥对应的订阅: {api_key}")
            return False
        
        # 更新API调用统计
        api.call_count += 1
        
        # 更新订阅使用统计
        subscription.used_calls += 1
        if subscription.remaining_calls is not None and subscription.remaining_calls > 0:
            subscription.remaining_calls -= 1
        
        db.commit()
        
        logger.info(f"API调用已记录: user_id={subscription.user_id}, api_id={api.id}")
        return True
        
    except Exception as e:
        logger.error(f"记录API统计失败: {e}")
        db.rollback()
        return False

def verify_api_key(api_key: str, api_id: int, db: Session) -> admin_models.Subscription:
    """
    验证API密钥和API状态并返回订阅信息
    
    Args:
        api_key: API密钥
        api_id: API ID
        db: 数据库会话
        
    Returns:
        Subscription: 验证成功的订阅信息
        
    Raises:
        HTTPException: 验证失败时抛出异常
    """
    from datetime import datetime, timezone
    
    # 1. 检查API密钥格式
    if not api_key or len(api_key.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="API密钥不能为空", 
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # 2. 查找订阅记录
    subscription = crud.SubscriptionCRUD.get_by_api_key(db, api_key)
    # print("subscription",subscription.api_id)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="API密钥不存在", 
            headers={"WWW-Authenticate": "ApiKey"}
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
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # 4. 检查订阅是否到期
    current_time = datetime.now(timezone.utc)
    
    # 确保end_date有时区信息
    end_date = subscription.end_date
    # print(end_date)
    if end_date.tzinfo is None:
        # 如果end_date没有时区信息，假设它是UTC时间
        end_date = end_date.replace(tzinfo=timezone.utc)
    
    if end_date <= current_time:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail=f"订阅已于 {end_date.strftime('%Y-%m-%d %H:%M:%S')} 到期", 
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # 5. 检查用户状态
    if not subscription.user or not subscription.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="用户账户已被禁用", 
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # 6. 检查订阅是否匹配指定的API
    if subscription.api_id != api_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="API密钥不匹配此接口", 
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # 7. 查找并检查API状态
    api = db.query(admin_models.API).filter(admin_models.API.id == api_id).first()
    if not api:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="API接口不存在"
        )

    # 8. 检查API是否可用
    if not api.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="API接口不可用", 
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # 9. 检查API是否已废弃
    if hasattr(api, 'deprecated') and api.deprecated:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, 
            detail="API接口已废弃，请使用新版本", 
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # 10. 检查调用次数限制（如果有）
    if subscription.remaining_calls is not None and subscription.remaining_calls <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, 
            detail="API调用次数已用完", 
            headers={"WWW-Authenticate": "ApiKey"}
        )

    return subscription

