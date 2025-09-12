from fastapi import APIRouter, Depends, HTTPException, status, Query, Form
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import List, Optional
from app.database import get_db
from app.auth import get_current_user, get_current_user_or_admin, get_password_hash, create_access_token, authenticate_user, get_user_module_access
from app.admin import models as admin_models
from app.admin import crud as admin_crud
from . import schemas
from app.cache import cache_manager
from app.utils.webconfig_manager import get_config, ConfigKeys
from apis.tcaptcha.core import check_tencent_captcha
import logging
from datetime import datetime, timedelta
import uuid
from app.utils.operation_logger import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["前台用户"])
# ==================== 安全 - 修改密码 ====================

@router.post("/change-password", response_model=schemas.ResponseModel)
async def change_password(
    payload: schemas.ChangePassword,
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """修改密码：校验原密码，通过后更新并强制退出当前登录"""
    try:
        # 校验原密码
        if not authenticate_user(db, current_user.username, payload.current_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="原密码不正确"
            )

        # 更新新密码
        hashed = get_password_hash(payload.new_password)
        success = admin_crud.UserCRUD.change_password(db, current_user.id, hashed)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新密码失败"
            )

        # 强制登出：撤销当前用户的token
        from app.auth import revoke_token
        revoke_token(current_user.username)

        # 写日志
        try:
            log_action(db,
                actor_id=current_user.id,
                actor_type="user",
                action="change_password",
                resource_type="user",
                resource_id=current_user.id,
                description="用户修改密码后强制登出"
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="密码修改成功，请重新登录"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"修改密码失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="修改密码失败"
        )


# ==================== 用户认证 ====================

@router.post("/register", response_model=schemas.ResponseModel)
async def register(
    user_data: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    """用户注册"""
    try:
        # 检查用户名是否已存在
        if admin_crud.UserCRUD.get_by_username(db, user_data.username):
            return schemas.ErrorResponseModel(
                message="用户名已存在",
                error_code="USERNAME_EXISTS",
                status_code=400
            )
        
        # 检查邮箱是否已存在
        if admin_crud.UserCRUD.get_by_email(db, user_data.email):
            return schemas.ErrorResponseModel(
                message="邮箱已存在",
                error_code="EMAIL_EXISTS",
                status_code=400
            )
        
        # 若开启验证码，先校验
        auth_captcha = get_config("system.auth_captcha_enabled", "false", str)
        if str(auth_captcha).lower() == 'true':
            # 从 body 中获取
            ticket = getattr(user_data, 'ticket', None) if hasattr(user_data, 'ticket') else None
            randstr = getattr(user_data, 'randstr', None) if hasattr(user_data, 'randstr') else None
            if not ticket or not randstr:
                return schemas.ErrorResponseModel(
                    message="请完成人机校验",
                    error_code="CAPTCHA_REQUIRED",
                    status_code=400
                )
            result = check_tencent_captcha(ticket, randstr)
            if not result.get('success'):
                return schemas.ErrorResponseModel(
                    message="人机校验失败",
                    error_code="CAPTCHA_FAILED",
                    status_code=400
                )

        # 创建用户
        user_dict = user_data.dict()
        user_dict["password"] = get_password_hash(user_data.password)
        user_dict["is_admin"] = False
        user_dict["is_active"] = True
        
        db_user = admin_crud.UserCRUD.create(db, user_dict)
        
        return schemas.ResponseModel(
            success=True,
            message="用户注册成功",
            data={"user_id": db_user.id, "username": db_user.username}
        )
    except Exception as e:
        logger.error(f"用户注册失败: {e}")
        return schemas.ErrorResponseModel(
            message="用户注册失败，请稍后重试",
            error_code="REGISTRATION_ERROR",
            status_code=500
        )

@router.post("/login", response_model=schemas.ResponseModel)
async def login(
    login_data: schemas.Login,
    db: Session = Depends(get_db)
):
    """用户登录"""
    try:
        # 若开启验证码，先校验
        auth_captcha = get_config("system.auth_captcha_enabled", "false", str)
        if str(auth_captcha).lower() == 'true':
            ticket = login_data.ticket
            randstr = login_data.randstr
            if not ticket or not randstr:
                return schemas.ErrorResponseModel(
                    message="请完成人机校验",
                    error_code="CAPTCHA_REQUIRED",
                    status_code=400
                )
            result = check_tencent_captcha(ticket, randstr)
            if not result.get('success'):
                return schemas.ErrorResponseModel(
                    message="人机校验失败",
                    error_code="CAPTCHA_FAILED",
                    status_code=400
                )

        user = authenticate_user(db, login_data.username, login_data.password)
        if not user:
            return schemas.ErrorResponseModel(
                message="用户名或密码错误",
                error_code="INVALID_CREDENTIALS",
                status_code=401
            )
        
        if not user.is_active:
            return schemas.ErrorResponseModel(
                message="账户已被禁用",
                error_code="ACCOUNT_DISABLED",
                status_code=400
            )
        
        # 创建访问令牌
        access_token = create_access_token(data={"sub": user.username})
        
        # 写登录日志
        try:
            log_action(db,
                actor_id=user.id,
                actor_type="user",
                action="login",
                resource_type="user",
                resource_id=user.id,
                description="用户登录"
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="登录成功",
            data={
                "access_token": access_token,
                "token_type": "bearer",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_admin": user.is_admin
                }
            }
        )
    except Exception as e:
        logger.error(f"用户登录失败: {e}")
        return schemas.ResponseModel(
            success=False,
            message="登录失败，请稍后重试",
            data={"error_code": "LOGIN_ERROR", "status_code": 500}
        )

@router.post("/logout", response_model=schemas.ResponseModel)
async def logout(
    current_user: schemas.User = Depends(get_user_module_access)
):
    """用户登出"""
    try:
        from ..auth import revoke_token
        # 撤销token
        success = revoke_token(current_user.username)
        if success:
            try:
                # 登出日志
                from app.database import get_db as _getdb
                db = next(_getdb())
                log_action(db,
                    actor_id=current_user.id,
                    actor_type="user",
                    action="logout",
                    resource_type="user",
                    resource_id=current_user.id,
                    description="用户登出"
                )
                db.close()
            except Exception:
                pass
            return schemas.ResponseModel(
                success=True,
                message="登出成功"
            )
        else:
            return schemas.ResponseModel(
                success=False,
                message="登出失败"
            )
    except Exception as e:
        logger.error(f"用户登出失败: {e}")
        return schemas.ResponseModel(
            success=False,
            message="登出失败，请稍后重试"
        )

@router.get("/profile", response_model=schemas.UserProfile)
async def get_profile(
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """获取用户个人资料"""
    try:
        # 获取用户的API订阅数量
        total_apis = db.query(admin_models.Subscription).filter(
            admin_models.Subscription.user_id == current_user.id,
            admin_models.Subscription.status == "active"
        ).count()
        
        # 获取用户的订单数量
        total_orders = db.query(admin_models.Order).filter(
            admin_models.Order.user_id == current_user.id
        ).count()
        
        # 获取用户的订阅数量
        total_subscriptions = db.query(admin_models.Subscription).filter(
            admin_models.Subscription.user_id == current_user.id
        ).count()
        
        profile_data = current_user.__dict__.copy()
        profile_data["total_apis"] = total_apis
        profile_data["total_orders"] = total_orders
        profile_data["total_subscriptions"] = total_subscriptions
        
        return schemas.UserProfile(**profile_data)
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise

    except Exception as e:
        logger.error(f"获取用户资料失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取用户资料失败"
        )

@router.get("/logs", response_model=schemas.PaginatedResponse)
async def get_user_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None, description="动作筛选：login/logout/recharge/consume 等"),
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """获取当前用户相关日志（登录、登出、充值、消费、余额变动等）"""
    try:
        # 关联条件：
        # 1) 用户自己作为操作者（actor_id）
        # 2) 管理员等对该用户进行的操作（resource_type='user' 且 resource_id=当前用户）
        q = db.query(admin_models.SystemLog).filter(
            or_(
                admin_models.SystemLog.actor_id == current_user.id,
                (admin_models.SystemLog.resource_type == "user") & (admin_models.SystemLog.resource_id == current_user.id)
            )
        )

        if action:
            q = q.filter(admin_models.SystemLog.action == action)

        total = q.count()
        logs = q.order_by(admin_models.SystemLog.created_at.desc()).offset(skip).limit(limit).all()

        items = []
        for log in logs:
            items.append({
                "id": log.id,
                "action": log.action,
                "description": log.description,
                "metadata": log.meta,
                "created_at": log.created_at
            })

        return schemas.PaginatedResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit
        )
    except Exception as e:
        logger.error(f"获取用户日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取用户日志失败"
        )

@router.put("/profile", response_model=schemas.ResponseModel)
async def update_profile(
    user_update: schemas.UserUpdate,
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """更新用户个人资料"""
    try:
        # 忽略 password 字段（不提示、不更新）
        # 仅更新非空且非密码字段
        update_data = {k: v for k, v in user_update.dict().items() if v is not None and k != "password"}
        
        updated_user = admin_crud.UserCRUD.update(db, current_user.id, update_data)
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"user:*{current_user.id}*")
        
        return schemas.ResponseModel(
            success=True,
            message="个人资料更新成功"
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise

    except Exception as e:
        logger.error(f"更新用户资料失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新用户资料失败"
        )

# ==================== API接口浏览 ====================

@router.get("/apis", response_model=schemas.PaginatedResponse)
async def get_apis(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None, description="分类筛选"),
    is_free: Optional[bool] = Query(None, description="是否免费"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """获取API接口列表（前台用户）"""
    try:
        # 获取所有公开的API接口
        apis = db.query(admin_models.API).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        )
        
        # 应用筛选条件
        if category:
            apis = apis.join(admin_models.APICategory).filter(
                admin_models.APICategory.name == category
            )
        if is_free is not None:
            apis = apis.filter(admin_models.API.is_free == is_free)
        if keyword:
            apis = apis.filter(
                admin_models.API.title.contains(keyword) | 
                admin_models.API.description.contains(keyword) |
                admin_models.API.alias.contains(keyword)
            )
        
        total = apis.count()
        apis = apis.options(joinedload(admin_models.API.category)).offset(skip).limit(limit).all()
        
        # 转换为前台展示格式
        items = []
        for api in apis:
            api_dict = {
                "id": api.id,
                "title": api.title,
                "alias": api.alias,
                "description": api.description,
                "endpoint": api.endpoint,
                "method": api.method,
                "return_format": api.return_format,
                "is_free": api.is_free,
                "price_type": api.price_type,
                "category": api.category.name if api.category else None,
                "tags": api.tags,
                "call_count": api.call_count,
                "success_count": api.success_count,
                "error_count": api.error_count,
                "created_at": api.created_at
            }
            items.append(api_dict)
        
        return schemas.PaginatedResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise

    except Exception as e:
        logger.error(f"获取API接口列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取API接口列表失败"
        )

@router.get("/apis/{api_id}", response_model=schemas.APIDetail)
async def get_api_detail(
    api_id: int,
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """获取API接口详情"""
    try:
        api = db.query(admin_models.API).options(
            joinedload(admin_models.API.category)
        ).filter(
            admin_models.API.id == api_id,
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        ).first()
        
        if not api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API接口不存在"
            )
        
        # 转换为前台展示格式
        api_detail = {
            "id": api.id,
            "title": api.title,
            "alias": api.alias,
            "description": api.description,
            "endpoint": api.endpoint,
            "method": api.method,
            "return_format": api.return_format,
            "is_free": api.is_free,
            "price_type": api.price_type,
            "category": api.category.name if api.category else None,
            "tags": api.tags,
            "call_count": api.call_count,
            "success_count": api.success_count,
            "error_count": api.error_count,
            "created_at": api.created_at,
            "updated_at": api.updated_at
        }
        
        return schemas.APIDetail(**api_detail)
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise

    except Exception as e:
        logger.error(f"获取API接口详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取API接口详情失败"
        )

# ==================== 订阅管理 ====================

@router.post("/subscribe/{api_id}", response_model=schemas.ResponseModel)
async def subscribe_api(
    api_id: int,
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """订阅API接口"""
    try:
        # 检查API是否存在且公开
        api = db.query(admin_models.API).filter(
            admin_models.API.id == api_id,
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        ).first()
        
        if not api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API接口不存在"
            )
        
        # 检查是否已经订阅
        existing_subscription = db.query(admin_models.Subscription).filter(
            admin_models.Subscription.user_id == current_user.id,
            admin_models.Subscription.api_id == api_id,
            admin_models.Subscription.status == "active"
        ).first()
        
        if existing_subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您已经订阅了此API接口"
            )
        
        # 创建订阅
        subscription_data = {
            "user_id": current_user.id,
            "api_id": api_id,
            "status": "active",
            "start_date": datetime.utcnow(),
            "end_date": datetime.utcnow() + timedelta(days=30),  # 默认30天
            "auto_renew": False
        }
        
        db_subscription = admin_crud.SubscriptionCRUD.create(db, subscription_data)
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"user:*{current_user.id}*")
        
        return schemas.ResponseModel(
            success=True,
            message="订阅成功",
            data={"subscription_id": db_subscription.id}
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise

    except Exception as e:
        logger.error(f"订阅API接口失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="订阅API接口失败"
        )

@router.delete("/unsubscribe/{api_id}", response_model=schemas.ResponseModel)
async def unsubscribe_api(
    api_id: int,
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """取消订阅API接口"""
    try:
        # 查找订阅记录
        subscription = db.query(admin_models.Subscription).filter(
            admin_models.Subscription.user_id == current_user.id,
            admin_models.Subscription.api_id == api_id,
            admin_models.Subscription.status == "active"
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到订阅记录"
            )
        
        # 取消订阅
        admin_crud.SubscriptionCRUD.update(db, subscription.id, {"status": "cancelled"})
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"user:*{current_user.id}*")
        
        return schemas.ResponseModel(
            success=True,
            message="取消订阅成功"
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise

    except Exception as e:
        logger.error(f"取消订阅API接口失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="取消订阅API接口失败"
        )

@router.post("/subscriptions/{api_id}/update-key", response_model=schemas.ResponseModel)
async def update_api_key(
    api_id: int,
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """更新API密钥"""
    try:
        # 查找订阅记录
        subscription = db.query(admin_models.Subscription).filter(
            admin_models.Subscription.user_id == current_user.id,
            admin_models.Subscription.api_id == api_id,
            admin_models.Subscription.status == "active"
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到有效的订阅记录"
            )
        
        # 生成新的API密钥
        new_api_key = admin_crud.SubscriptionCRUD.generate_api_key(
            current_user.id, 
            api_id,
            subscription.id
        )
        
        # 确保新密钥唯一性
        while db.query(admin_models.Subscription).filter(
            admin_models.Subscription.api_key == new_api_key,
            admin_models.Subscription.id != subscription.id
        ).first():
            new_api_key = admin_crud.SubscriptionCRUD.generate_api_key(
                current_user.id, 
                api_id,
                subscription.id
            )
        
        # 更新API密钥
        subscription.api_key = new_api_key
        subscription.updated_at = datetime.utcnow()
        db.commit()
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"user:*{current_user.id}*")
        
        return schemas.ResponseModel(
            success=True,
            message="API密钥更新成功",
            data={"new_api_key": new_api_key}
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"更新API密钥失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新API密钥失败"
        )

@router.get("/subscriptions", response_model=schemas.PaginatedResponse)
async def get_subscriptions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    api_id: Optional[int] = Query(None, description="API ID筛选"),
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """获取用户的订阅列表"""
    try:
        subscriptions = db.query(admin_models.Subscription).filter(
            admin_models.Subscription.user_id == current_user.id
        )
        
        # 如果指定了api_id，则只查询该API的订阅
        if api_id is not None:
            subscriptions = subscriptions.filter(
                admin_models.Subscription.api_id == api_id
            )
        
        total = subscriptions.count()
        subscriptions = subscriptions.offset(skip).limit(limit).all()
        
        # 转换为前台展示格式
        items = []
        for subscription in subscriptions:
            api = subscription.api
            subscription_dict = {
                "id": subscription.id,
                "api_id": subscription.api_id,
                "api_key": subscription.api_key,
                "api_title": api.title if api else "未知API",
                "api_alias": api.alias if api else "",
                "start_date": subscription.start_date,
                "status": subscription.status,
                "end_date": subscription.end_date,
                "used_calls": subscription.used_calls,
                "remaining_calls": subscription.remaining_calls
            }
            items.append(subscription_dict)
        
        return schemas.PaginatedResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise

    except Exception as e:
        logger.error(f"获取订阅列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取订阅列表失败"
        )

# ==================== 订单管理 ====================

@router.post("/orders", response_model=schemas.ResponseModel)
async def create_order(
    order_data: schemas.OrderCreate,
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """创建订单"""
    try:
        # 检查API是否存在
        api = db.query(admin_models.API).filter(
            admin_models.API.id == order_data.api_id,
            admin_models.API.is_active == True
        ).first()
        
        if not api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API接口不存在"
            )
        
        # 创建订单
        order_dict = order_data.dict()
        order_dict["user_id"] = current_user.id
        order_dict["order_no"] = f"ORD{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8]}"
        order_dict["status"] = "pending"
        order_dict["created_at"] = datetime.utcnow()
        
        db_order = admin_crud.OrderCRUD.create(db, order_dict)
        
        return schemas.ResponseModel(
            success=True,
            message="订单创建成功",
            data={"order_id": db_order.id, "order_no": db_order.order_no}
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise

    except Exception as e:
        logger.error(f"创建订单失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建订单失败"
        )

@router.get("/orders", response_model=schemas.PaginatedResponse)
async def get_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """获取用户的订单列表"""
    try:
        orders = db.query(admin_models.Order).options(
            joinedload(admin_models.Order.api)
        ).filter(
            admin_models.Order.user_id == current_user.id
        )
        
        total = orders.count()
        orders = orders.offset(skip).limit(limit).all()
        
        # 转换为前台展示格式
        items = []
        for order in orders:
            api = order.api
            order_dict = {
                "id": order.id,
                "order_no": order.order_no,
                "api_id": order.api_id,
                "api_title": api.title if api else "未知API",
                "api_alias": api.alias if api else "",
                "amount": order.amount,
                "status": order.status,
                "payment_method": order.payment_method or "未知",
                "payment_status": order.payment_status or "未知",
                "remark": order.remark or "",
                "created_at": order.created_at,
                "updated_at": order.updated_at,
                "paid_at": order.paid_at
            }
            items.append(order_dict)
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"user:*{current_user.id}*")
        
        return schemas.PaginatedResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"获取订单列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取订单列表失败"
        )

@router.get("/orders/{order_id}", response_model=schemas.Order)
async def get_order_detail(
    order_id: int,
    current_user: schemas.User = Depends(get_user_module_access),
    db: Session = Depends(get_db)
):
    """获取订单详情"""
    try:
        order = db.query(admin_models.Order).filter(
            admin_models.Order.id == order_id,
            admin_models.Order.user_id == current_user.id
        ).first()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="订单不存在"
            )
        
        # 转换为前台展示格式
        api = order.api
        order_detail = {
            "id": order.id,
            "order_no": order.order_no,
            "api_id": order.api_id,
            "api_title": api.title if api else "未知API",
            "api_alias": api.alias if api else "",
            "amount": order.amount,
            "status": order.status,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "remark": order.remark,
            "paid_at": order.paid_at,
            "created_at": order.created_at,
            "updated_at": order.updated_at
        }
        
        return schemas.Order(**order_detail)
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"获取订单详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取订单详情失败"
        )
