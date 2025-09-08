from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, text, cast
from sqlalchemy.types import String
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.auth import get_current_admin_user, get_admin_only, get_admin_module_access
from . import crud, schemas, models
from app.cache import cache_manager
import logging
from app.utils.operation_logger import log_action
from app.utils.webconfig_manager import get_config, ConfigKeys
from app.auth import get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["后台管理"])

# ==================== 用户管理 ====================

@router.post("/users", response_model=schemas.ResponseModel)
async def create_user_admin(
    user_data: schemas.AdminUserCreate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """创建用户（管理员）"""
    try:
        # 校验唯一性
        if crud.UserCRUD.get_by_username(db, user_data.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在"
            )
        if crud.UserCRUD.get_by_email(db, user_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已存在"
            )

        # 使用 WebConfig 默认值
        # 默认余额
        default_balance = get_config(ConfigKeys.SYSTEM_DEFAULT_USER_BALANCE, 0.0, float)
        # 默认激活策略：若开启了注册审批，则默认不激活；否则激活
        registration_approval = get_config(ConfigKeys.SYSTEM_REGISTRATION_APPROVAL, False, bool)

        is_active = user_data.is_active if user_data.is_active is not None else (not registration_approval)
        is_admin = user_data.is_admin if user_data.is_admin is not None else False
        balance = user_data.balance if user_data.balance is not None else default_balance

        # 构造入库数据
        create_dict = {
            "username": user_data.username,
            "email": user_data.email,
            "password": get_password_hash(user_data.password),
            "is_active": is_active,
            "is_admin": is_admin,
            "balance": balance,
        }

        db_user = crud.UserCRUD.create(db, create_dict)

        # 写管理日志
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="create_user",
                resource_type="user",
                resource_id=db_user.id,
                description="管理员创建用户",
                metadata={
                    "username": db_user.username,
                    "email": db_user.email,
                    "is_admin": db_user.is_admin,
                    "is_active": db_user.is_active,
                    "balance": db_user.balance or 0,
                }
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="用户创建成功",
            data={"user_id": db_user.id}
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except ValueError as e:
        # 业务约束（例如禁止重复管理员）
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"创建用户失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建用户失败"
        )

@router.get("/users", response_model=schemas.PaginatedResponse)
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    is_active: Optional[bool] = Query(None, description="是否激活"),
    is_admin: Optional[bool] = Query(None, description="是否管理员"),
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取用户列表（管理员）"""
    try:
        users = crud.UserCRUD.get_all(db, skip, limit)
        
        # 过滤用户
        if keyword:
            users = [u for u in users if keyword.lower() in u.username.lower() or keyword.lower() in u.email.lower()]
        if is_active is not None:
            users = [u for u in users if u.is_active == is_active]
        if is_admin is not None:
            users = [u for u in users if u.is_admin == is_admin]
        
        total = len(users)
        # 批量统计扩展字段（订单数、订阅数、最后登录时间）
        user_ids = [u.id for u in users]
        order_count_map = {}
        subscription_count_map = {}
        last_login_map = {}
        if user_ids:
            # 订单数
            for uid, cnt in db.query(models.Order.user_id, func.count(models.Order.id)).\
                filter(models.Order.user_id.in_(user_ids)).\
                group_by(models.Order.user_id).all():
                order_count_map[uid] = cnt

            # 订阅数
            for uid, cnt in db.query(models.Subscription.user_id, func.count(models.Subscription.id)).\
                filter(models.Subscription.user_id.in_(user_ids)).\
                group_by(models.Subscription.user_id).all():
                subscription_count_map[uid] = cnt

            # 最后登录时间（系统日志中 action='login'）
            for uid, last_time in db.query(models.SystemLog.actor_id, func.max(models.SystemLog.created_at)).\
                filter(models.SystemLog.actor_id.in_(user_ids), models.SystemLog.action == "login").\
                group_by(models.SystemLog.actor_id).all():
                last_login_map[uid] = last_time

        return schemas.PaginatedResponse(
            items=[{
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_admin": user.is_admin,
                "balance": user.balance or 0,
                "order_count": order_count_map.get(user.id, 0),
                "subscription_count": subscription_count_map.get(user.id, 0),
                "last_login": last_login_map.get(user.id),
                "created_at": user.created_at,
                "updated_at": user.updated_at
            } for user in users],
            total=total,
            page=skip // limit + 1,
            size=limit,
            pages=(total + limit - 1) // limit
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"获取用户列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取用户列表失败"
        )

@router.get("/users/{user_id}", response_model=schemas.User)
async def get_user(
    user_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取用户详情（管理员）"""
    try:
        user = crud.UserCRUD.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        return user
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"获取用户详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取用户详情失败"
        )

@router.put("/users/{user_id}", response_model=schemas.ResponseModel)
async def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """更新用户信息（管理员）"""
    try:
        # 过滤掉None值
        update_data = {k: v for k, v in user_update.dict().items() if v is not None}
        
        updated_user = crud.UserCRUD.update(db, user_id, update_data)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"user:*{user_id}*")
        
        # 写管理日志
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="update_user",
                resource_type="user",
                resource_id=user_id,
                description="管理员更新用户信息",
                metadata={k:v for k,v in update_data.items() if k != "password"}
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="用户更新成功",
            data={"user_id": updated_user.id}
        )
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"更新用户失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新用户失败"
        )

@router.delete("/users/{user_id}", response_model=schemas.ResponseModel)
async def delete_user(
    user_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """删除用户（管理员）"""
    try:
        # 不能删除自己
        if user_id == current_admin.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能删除自己的账户"
            )
        
        if crud.UserCRUD.delete(db, user_id):
            # 清除相关缓存
            cache_manager.clear_pattern(f"user:*{user_id}*")
            
            # 写管理日志
            try:
                log_action(db,
                    actor_id=current_admin.id,
                    actor_type="admin",
                    action="delete_user",
                    resource_type="user",
                    resource_id=user_id,
                    description="管理员删除用户"
                )
            except Exception:
                pass

            return schemas.ResponseModel(
                success=True,
                message="用户删除成功"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"删除用户失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除用户失败"
        )

@router.post("/users/{user_id}/toggle-status", response_model=schemas.ResponseModel)
async def toggle_user_status(
    user_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """切换用户状态（管理员）"""
    try:
        user = crud.UserCRUD.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 不能禁用自己
        if user_id == current_admin.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能禁用自己的账户"
            )
        
        user_update = schemas.UserUpdate(is_active=not user.is_active)
        updated_user = crud.UserCRUD.update(db, user_id, user_update.dict(exclude_unset=True))
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"user:*{user_id}*")
        
        return schemas.ResponseModel(
            success=True,
            message="用户状态切换成功",
            data={"is_active": updated_user.is_active}
        )
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"切换用户状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="切换用户状态失败"
        )

@router.post("/users/{user_id}/balance", response_model=schemas.ResponseModel)
async def update_user_balance(
    user_id: int,
    balance_data: dict,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """修改用户余额（管理员）"""
    try:
        user = crud.UserCRUD.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        amount = balance_data.get("amount", 0)
        if not isinstance(amount, (int, float)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="金额格式错误"
            )
        
        # 计算新余额
        new_balance = (user.balance or 0) + amount
        if new_balance < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="余额不足，无法完成操作"
            )
        
        # 更新用户余额
        updated_user = crud.UserCRUD.update_balance(db, user_id, new_balance)
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新用户余额失败"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"user:*{user_id}*")
        
        action = "增加" if amount > 0 else "减少"
        # 写管理日志
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="update_user_balance",
                resource_type="user",
                resource_id=user_id,
                description=f"管理员{action}余额",
                metadata={"amount": amount, "new_balance": updated_user.balance}
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message=f"成功{action}用户余额 ¥{abs(amount)}",
            data={"balance": updated_user.balance}
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"修改用户余额失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="修改用户余额失败"
        )

# ==================== API接口管理 ====================

@router.get("/apis", response_model=schemas.PaginatedResponse)
async def get_apis_admin(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类筛选"),
    is_active: Optional[bool] = Query(None, description="是否激活"),
    is_public: Optional[bool] = Query(None, description="是否公开"),
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取API接口列表（管理员）"""
    try:
        # 获取所有API接口（管理员可以看到所有API）
        apis = db.query(models.API)
        
        # 应用筛选条件
        if keyword:
            apis = apis.filter(
                models.API.title.contains(keyword) | 
                models.API.description.contains(keyword) |
                models.API.alias.contains(keyword)
            )
        if category:
            apis = apis.filter(models.API.category_id == category)
        if is_active is not None:
            apis = apis.filter(models.API.is_active == is_active)
        if is_public is not None:
            apis = apis.filter(models.API.is_public == is_public)
        
        total = apis.count()
        apis = apis.options(joinedload(models.API.category)).offset(skip).limit(limit).all()
        
        # 转换为响应格式
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
                "request_params": api.request_params or "[]",
                "request_example": api.request_example or "",
                "request_headers": api.request_headers or "{}",
                "response_example": api.response_example or "",
                "code_examples": api.code_examples or "{}",
                "error_codes": api.error_codes or "{}",
                "is_active": api.is_active,
                "is_public": api.is_public,
                "is_free": api.is_free,
                "call_count": api.call_count,
                "category_id": api.category_id,
                "category": api.category.name if api.category else None,
                "tags": api.tags or "[]",
                "price_config": api.price_config or "{}",
                "price_type": api.price_type.value if api.price_type else "per_call",
                "version": api.version or "1.0.0",
                "deprecated": api.deprecated,
                "created_at": api.created_at,
                "updated_at": api.updated_at
            }
            items.append(api_dict)
        
        return schemas.PaginatedResponse(
            items=items,
            total=total,
            page=skip // limit + 1,
            size=limit,
            pages=(total + limit - 1) // limit
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

@router.post("/apis", response_model=schemas.ResponseModel)
async def create_api_admin(
    api: schemas.APICreate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """创建API接口（管理员）"""
    try:
        # 检查端点是否已存在
        if crud.APICRUD.get_by_endpoint(db, api.endpoint):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API端点已存在"
            )
        
        # 创建API接口
        api_data = api.dict()
        
        # 处理分类字段：统一使用 category_id
        if 'category_id' in api_data and api_data['category_id'] is not None:
            category_id = api_data['category_id']
            # 验证分类ID是否存在
            category = db.query(models.APICategory).filter(
                models.APICategory.id == category_id
            ).first()
            if not category:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"分类ID {category_id} 不存在"
                )
        
        db_api = crud.APICRUD.create(db, api_data)
        
        # 清除相关缓存
        cache_manager.clear_pattern("api:*")
        
        # 日志
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="create_api",
                resource_type="api",
                resource_id=db_api.id,
                description="创建API接口",
                metadata={"title": db_api.title, "alias": db_api.alias}
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="API接口创建成功",
            data={"api_id": db_api.id, "title": db_api.title}
        )
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"API接口创建失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API接口创建失败"
        )

@router.put("/apis/{api_id}", response_model=schemas.ResponseModel)
async def update_api_admin(
    api_id: int,
    api_update: schemas.APIUpdate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """更新API接口（管理员）"""
    try:
        # 获取API接口
        api = crud.APICRUD.get_by_id(db, api_id)
        if not api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API接口不存在"
            )
        
        # 过滤掉None值
        update_data = {k: v for k, v in api_update.dict().items() if v is not None}
        
        # 添加调试日志
        logger.info(f"更新API {api_id}，原始数据: {api_update.dict()}")
        logger.info(f"过滤后的更新数据: {update_data}")
        
        # 处理分类字段：统一使用 category_id
        if 'category_id' in update_data:
            category_id = update_data['category_id']
            logger.info(f"处理分类ID字段: {category_id}")
            if category_id is not None:
                # 验证分类ID是否存在
                category = db.query(models.APICategory).filter(
                    models.APICategory.id == category_id
                ).first()
                if not category:
                    logger.error(f"分类ID {category_id} 不存在")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"分类ID {category_id} 不存在"
                    )
                logger.info(f"分类ID {category_id} 验证通过")
        
        # 更新API接口
        updated_api = crud.APICRUD.update(db, api_id, update_data)
        
        if not updated_api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API接口不存在"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"api:*{api_id}*")
        cache_manager.clear_pattern("api:*")
        
        # 日志
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="update_api",
                resource_type="api",
                resource_id=api_id,
                description="更新API接口",
                metadata=update_data
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="API接口更新成功",
            data={"api_id": updated_api.id}
        )
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"API接口更新失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API接口更新失败"
        )

@router.delete("/apis/{api_id}", response_model=schemas.ResponseModel)
async def delete_api_admin(
    api_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """删除API接口（管理员）"""
    try:
        if crud.APICRUD.delete(db, api_id):
            # 清除相关缓存
            cache_manager.clear_pattern(f"api:*{api_id}*")
            cache_manager.clear_pattern("api:*")
            
            try:
                log_action(db,
                    actor_id=current_admin.id,
                    actor_type="admin",
                    action="delete_api",
                    resource_type="api",
                    resource_id=api_id,
                    description="删除API接口"
                )
            except Exception:
                pass

            return schemas.ResponseModel(
                success=True,
                message="API接口删除成功"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API接口不存在"
            )
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"删除API接口失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除API接口失败"
        )

@router.post("/apis/{api_id}/toggle-status", response_model=schemas.ResponseModel)
async def toggle_api_status_admin(
    api_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """切换API接口状态（管理员）"""
    try:
        updated_api = crud.APICRUD.toggle_status(db, api_id)
        
        if not updated_api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API接口不存在"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern(f"api:*{api_id}*")
        cache_manager.clear_pattern("api:*")
        
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="toggle_api_status",
                resource_type="api",
                resource_id=api_id,
                description="切换API接口状态",
                metadata={"is_active": updated_api.is_active}
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="API接口状态切换成功",
            data={"is_active": updated_api.is_active}
        )
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"API接口状态切换失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API接口状态切换失败"
        )

# ==================== 统计分析 ====================

@router.get("/stats", response_model=schemas.APIStats)
async def get_admin_stats(
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取管理统计信息"""
    try:
        # 获取用户总数
        total_users = db.query(models.User).count()
        
        # 获取API总数
        total_apis = db.query(models.API).count()
        active_apis = db.query(models.API).filter(models.API.is_active == True).count()
        
        # 获取总调用次数
        total_calls = db.query(models.API).with_entities(
            func.sum(models.API.call_count)
        ).scalar() or 0
        
        # 获取订单总数
        total_orders = db.query(models.Order).count()
        
        # 获取总收入
        revenue_stats = crud.OrderCRUD.get_revenue_stats(db)
        total_revenue = revenue_stats["total_revenue"]
        
        # 获取热门分类（按API数量排序）
        popular_categories = db.query(
            models.APICategory.name,
            func.count(models.API.id).label('api_count')
        ).join(models.API, models.APICategory.id == models.API.category_id, isouter=True)\
         .group_by(models.APICategory.id, models.APICategory.name)\
         .order_by(func.count(models.API.id).desc())\
         .limit(5).all()
        
        popular_categories_list = [
            {"name": cat.name, "count": cat.api_count} 
            for cat in popular_categories
        ]
        
        # 获取最近活动（最近注册的用户）
        recent_users = db.query(models.User)\
                        .order_by(models.User.created_at.desc())\
                        .limit(5).all()
        
        recent_activities = [
            {
                "type": "user_register",
                "description": "新用户注册",
                "user": user.username,
                "timestamp": user.created_at.isoformat()
            }
            for user in recent_users
        ]
        
        return schemas.APIStats(
            total_apis=total_apis,
            active_apis=active_apis,
            total_calls=total_calls,
            total_users=total_users,
            total_orders=total_orders,
            total_revenue=total_revenue,
            popular_categories=popular_categories_list,
            recent_activities=recent_activities
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取统计信息失败"
        )

@router.get("/stats/user-growth")
async def get_user_growth_stats(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取用户增长趋势数据"""
    try:
        from datetime import datetime, timedelta
        
        # 计算日期范围
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days-1)
        
        # 获取每日用户注册数量
        daily_users = db.query(
            func.date(models.User.created_at).label('date'),
            func.count(models.User.id).label('count')
        ).filter(
            func.date(models.User.created_at) >= start_date,
            func.date(models.User.created_at) <= end_date
        ).group_by(func.date(models.User.created_at)).all()
        
        # 创建完整的日期列表
        dates = []
        counts = []
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            dates.append(date_str)
            
            # 查找对应日期的用户数量
            count = 0
            for daily_user in daily_users:
                if daily_user.date == current_date:
                    count = daily_user.count
                    break
            
            counts.append(count)
            current_date += timedelta(days=1)
        
        return schemas.ResponseModel(
            success=True,
            message="获取用户增长数据成功",
            data={
                "dates": dates,
                "counts": counts,
                "total_days": days
            }
        )
        
    except Exception as e:
        logger.error(f"获取用户增长数据失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取用户增长数据失败"
        )

@router.get("/stats/api-usage")
async def get_api_usage_stats(
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取API使用情况统计（按API聚合）"""
    try:
        # 按API聚合调用次数，取前10
        api_usage = db.query(
            models.API.title.label('api_title'),
            models.API.call_count.label('total_calls')
        ).order_by(models.API.call_count.desc())\
         .limit(10).all()

        # 转换为图表数据格式
        chart_data = []
        for item in api_usage:
            if (item.total_calls or 0) > 0:
                chart_data.append({
                    "name": item.api_title,
                    "value": int(item.total_calls or 0)
                })
        
        # 如果没有数据，返回默认数据
        if not chart_data:
            chart_data = [
                {"name": "暂无数据", "value": 1}
            ]
        
        return schemas.ResponseModel(
            success=True,
            message="获取API使用统计成功",
            data={
                "chart_data": chart_data,
                "total_items": len(chart_data)
            }
        )
        
    except Exception as e:
        logger.error(f"获取API使用统计失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取API使用统计失败"
        )

@router.get("/stats/api-performance")
async def get_api_performance_stats(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取API调用汇总统计（精简版）

    说明：不再依赖 APILog 明细表统计成功次数、成功率、平均响应时间、今日/本月调用。
    仅返回所有 API 在 apis.call_count 字段上的总和。
    """
    try:
        # 基于 API 表的调用累计计数汇总
        total_calls = db.query(models.API).with_entities(
            func.sum(models.API.call_count)
        ).scalar() or 0

        return schemas.ResponseModel(
            success=True,
            message="获取API调用汇总成功",
            data={
                "total_calls": int(total_calls)
            }
        )

    except Exception as e:
        logger.error(f"获取API调用汇总失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取API调用汇总失败"
        )

@router.get("/system/status")
async def get_system_status(
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取系统状态"""
    try:
        status = {
            "database": "healthy",
            "redis": "healthy", 
            "api": "healthy",
            "overall": "healthy"
        }
        
        # 检查数据库状态（更健壮：优先使用文本查询，失败则退回连接级检测）
        try:
            db.execute(text("SELECT 1"))
            status["database"] = "healthy"
        except Exception as e:
            logger.warning(f"会话级数据库探测失败，尝试连接级探测: {e}")
            try:
                from app.database import engine
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                status["database"] = "healthy"
            except Exception as e2:
                logger.error(f"数据库连接失败: {e2}")
                status["database"] = "unhealthy"
        
        # 检查Redis状态
        try:
            cache_manager.redis.ping()
            status["redis"] = "healthy"
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            status["redis"] = "unhealthy"
        
        # API服务状态（如果能到达这里说明API正常）
        status["api"] = "healthy"
        
        # 计算整体状态
        if status["database"] == "healthy" and status["redis"] == "healthy" and status["api"] == "healthy":
            status["overall"] = "healthy"
        else:
            status["overall"] = "unhealthy"
        
        return schemas.ResponseModel(
            success=True,
            message="系统状态检查完成",
            data=status
        )
        
    except Exception as e:
        logger.error(f"系统状态检查失败: {e}")
        return schemas.ResponseModel(
            success=False,
            message="系统状态检查失败",
            data={
                "database": "unhealthy",
                "redis": "unhealthy",
                "api": "unhealthy", 
                "overall": "unhealthy"
            }
        )

# ==================== 分类管理 ====================

@router.get("/categories")
async def get_categories_admin(
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取所有分类（管理员）"""
    try:
        categories = crud.CategoryCRUD.get_all(db)
        
        # 为每个分类添加API数量
        categories_with_count = []
        for category in categories:
            api_count = crud.CategoryCRUD.get_api_count(db, category.id)
            category_dict = {
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "sort_order": category.sort_order,
                "is_active": category.is_active,
                "created_at": category.created_at,
                "api_count": api_count
            }
            categories_with_count.append(category_dict)
        
        return categories_with_count
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取分类列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取分类列表失败"
        )



@router.get("/categories/{category_id}", response_model=schemas.Category)
async def get_category_admin(
    category_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取分类详情（管理员）"""
    try:
        category = crud.CategoryCRUD.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="分类不存在"
            )
        return category
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取分类详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取分类详情失败"
        )

@router.post("/categories", response_model=schemas.ResponseModel)
async def create_category_admin(
    category: schemas.CategoryCreate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """创建分类（管理员）"""
    try:
        # 检查分类名称是否已存在
        if crud.CategoryCRUD.get_by_name(db, category.name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="分类名称已存在"
            )
        
        # 创建分类
        db_category = crud.CategoryCRUD.create(db, category.dict())
        
        return schemas.ResponseModel(
            success=True,
            message="分类创建成功",
            data={"category_id": db_category.id, "name": db_category.name}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建分类失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建分类失败"
        )

@router.put("/categories/{category_id}", response_model=schemas.ResponseModel)
async def update_category_admin(
    category_id: int,
    category_update: schemas.CategoryUpdate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """更新分类（管理员）"""
    try:
        # 检查分类是否存在
        existing_category = crud.CategoryCRUD.get_by_id(db, category_id)
        if not existing_category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="分类不存在"
            )
        
        # 如果更新名称，检查是否与其他分类重复
        if category_update.name and category_update.name != existing_category.name:
            if crud.CategoryCRUD.get_by_name(db, category_update.name):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="分类名称已存在"
                )
        
        # 更新分类
        updated_category = crud.CategoryCRUD.update(db, category_id, category_update.dict(exclude_unset=True))
        
        if not updated_category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="分类不存在"
            )
        
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="update_category",
                resource_type="category",
                resource_id=category_id,
                description="更新分类",
                metadata=category_update.dict(exclude_unset=True)
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="分类更新成功",
            data={"category_id": updated_category.id}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新分类失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新分类失败"
        )

@router.delete("/categories/{category_id}", response_model=schemas.ResponseModel)
async def delete_category_admin(
    category_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """删除分类（管理员）"""
    try:
        if crud.CategoryCRUD.delete(db, category_id):
            try:
                log_action(db,
                    actor_id=current_admin.id,
                    actor_type="admin",
                    action="delete_category",
                    resource_type="category",
                    resource_id=category_id,
                    description="删除分类"
                )
            except Exception:
                pass

            return schemas.ResponseModel(
                success=True,
                message="分类删除成功"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="分类不存在"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除分类失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除分类失败"
        )

@router.get("/categories/{category_id}/apis", response_model=schemas.PaginatedResponse)
async def get_category_apis_admin(
    category_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取分类下的API接口（管理员）"""
    try:
        # 检查分类是否存在
        category = crud.CategoryCRUD.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="分类不存在"
            )
        
        # 获取分类下的API接口
        apis = db.query(models.API).filter(
            models.API.category_id == category_id,
            models.API.is_active == True
        )
        
        total = apis.count()
        apis = apis.offset(skip).limit(limit).all()
        
        # 转换为响应格式
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
                "request_params": api.request_params or "[]",
                "request_example": api.request_example or "",
                "request_headers": api.request_headers or "{}",
                "response_example": api.response_example or "",
                "code_examples": api.code_examples or "{}",
                "error_codes": api.error_codes or "{}",
                "is_active": api.is_active,
                "is_public": api.is_public,
                "is_free": api.is_free,
                "call_count": api.call_count,
                "category_id": api.category_id,
                "category": api.category.name if api.category else None,
                "tags": api.tags or "[]",
                "price_config": api.price_config or "{}",
                "price_type": api.price_type.value if api.price_type else "per_call",
                "version": api.version or "1.0.0",
                "deprecated": api.deprecated,
                "created_at": api.created_at,
                "updated_at": api.updated_at
            }
            items.append(api_dict)
        
        return schemas.PaginatedResponse(
            items=items,
            total=total,
            page=skip // limit + 1,
            size=limit,
            pages=(total + limit - 1) // limit
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取分类API接口失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取分类API接口失败"
        )

# ==================== 订单管理 ====================

@router.get("/orders", response_model=schemas.PaginatedResponse)
async def get_orders_admin(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="订单状态筛选"),
    user_id: Optional[int] = Query(None, description="用户ID筛选"),
    api_id: Optional[int] = Query(None, description="API ID筛选"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取订单列表（管理员）"""
    try:
        # 获取所有订单
        orders = db.query(models.Order)
        
        # 应用筛选条件
        if status:
            orders = orders.filter(models.Order.status == status)
        if user_id:
            orders = orders.filter(models.Order.user_id == user_id)
        if api_id:
            orders = orders.filter(models.Order.api_id == api_id)
        if start_date:
            orders = orders.filter(models.Order.created_at >= start_date)
        if end_date:
            orders = orders.filter(models.Order.created_at <= end_date)
        
        total = orders.count()
        orders = orders.order_by(models.Order.created_at.desc()).offset(skip).limit(limit).all()
        
        # 转换为响应格式
        items = []
        for order in orders:
            order_dict = {
                "id": order.id,
                "order_no": order.order_no,
                "user_id": order.user_id,
                "user_username": order.user.username if order.user else "未知用户",
                "user_email": order.user.email if order.user else "",
                "api_id": order.api_id,
                "api_title": order.api.title if order.api else "未知API",
                "api_alias": order.api.alias if order.api else "",
                "amount": order.amount,
                "quantity": order.quantity,
                "status": order.status,
                "payment_method": order.payment_method,
                "payment_status": order.payment_status,
                "paid_at": order.paid_at,
                "remark": order.remark,
                "created_at": order.created_at,
                "updated_at": order.updated_at
            }
            items.append(order_dict)
        
        return schemas.PaginatedResponse(
            items=items,
            total=total,
            page=skip // limit + 1,
            size=limit,
            pages=(total + limit - 1) // limit
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"获取订单列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取订单列表失败"
        )

@router.get("/orders/{order_id}", response_model=schemas.OrderDetail)
async def get_order_detail_admin(
    order_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取订单详情（管理员）"""
    try:
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="订单不存在"
            )
        
        # 转换为响应格式
        order_detail = {
            "id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "user_username": order.user.username if order.user else "未知用户",
            "user_email": order.user.email if order.user else "",
            "api_id": order.api_id,
            "api_title": order.api.title if order.api else "未知API",
            "api_alias": order.api.alias if order.api else "",
            "amount": order.amount,
            "quantity": order.quantity,
            "status": order.status,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "paid_at": order.paid_at,
            "remark": order.remark,
            "created_at": order.created_at,
            "updated_at": order.updated_at
        }
        
        return schemas.OrderDetail(**order_detail)
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"获取订单详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取订单详情失败"
        )

@router.put("/orders/{order_id}/status", response_model=schemas.ResponseModel)
async def update_order_status_admin(
    order_id: int,
    status_update: schemas.OrderStatusUpdate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """更新订单状态（管理员）"""
    try:
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="订单不存在"
            )
        
        # 更新订单状态
        order.status = status_update.status
        
        # 根据状态更新相关字段
        if status_update.status == "paid" and not order.paid_at:
            order.paid_at = datetime.utcnow()
            order.payment_status = "paid"
        elif status_update.status == "refunded":
            order.payment_status = "refunded"
        elif status_update.status == "cancelled":
            order.payment_status = "unpaid"
        
        db.commit()
        
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="update_order_status",
                resource_type="order",
                resource_id=order.id,
                description="更新订单状态",
                metadata={"status": order.status}
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="订单状态更新成功",
            data={"order_id": order.id, "status": order.status}
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"更新订单状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新订单状态失败"
        )

@router.post("/orders/export")
async def export_orders_admin(
    export_params: schemas.OrderExportParams,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """导出订单数据（管理员）"""
    try:
        # 获取订单数据
        orders = db.query(models.Order)
        
        # 应用筛选条件
        if export_params.status:
            orders = orders.filter(models.Order.status == export_params.status)
        if export_params.start_date:
            orders = orders.filter(models.Order.created_at >= export_params.start_date)
        if export_params.end_date:
            orders = orders.filter(models.Order.created_at <= export_params.end_date)
        
        orders = orders.order_by(models.Order.created_at.desc()).all()
        
        # 这里应该实现实际的导出逻辑（CSV、Excel等）
        # 目前返回订单数据
        export_data = []
        for order in orders:
            export_data.append({
                "订单号": order.order_no,
                "用户": order.user.username if order.user else "未知用户",
                "API": order.api.title if order.api else "未知API",
                "金额": order.amount,
                "状态": order.status,
                "创建时间": order.created_at.strftime("%Y-%m-%d %H:%M:%S") if order.created_at else ""
            })
        
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="export_orders",
                resource_type="order",
                description="导出订单数据",
                metadata={"count": len(export_data)}
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="订单导出成功",
            data={"orders": export_data, "total": len(export_data)}
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"导出订单失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="导出订单失败"
        )

# ==================== 系统维护 ====================

@router.post("/maintenance/clear-cache")
async def clear_all_cache(
    current_admin: models.User = Depends(get_admin_module_access)
):
    """清除系统缓存（保留用户登录状态）"""
    try:
        # 明确指定要清除的缓存类型，避免使用通配符*
        cache_patterns = [
            "api:*",           # API相关缓存
            "category:*",      # 分类缓存
            "order:*",         # 订单缓存
            "webconfig*",      # 网站配置缓存
            "stats:*",         # 统计缓存
        ]
        
        total_cleared = 0
        for pattern in cache_patterns:
            cleared = cache_manager.clear_pattern(pattern)
            total_cleared += cleared
            logger.info(f"清除缓存模式 {pattern}: {cleared} 个键")
        
        # 清除用户信息缓存，但保留token缓存
        user_cache_keys = cache_manager.redis.keys("user:*")
        for key in user_cache_keys:
            if not key.decode('utf-8').startswith("token:"):
                cache_manager.redis.delete(key)
                total_cleared += 1
        
        try:
            log_action(db=None,
                actor_id=current_admin.id,
                actor_type="admin",
                action="clear_cache",
                resource_type="system",
                description="清除系统缓存",
                metadata={"cleared": total_cleared}
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message=f"缓存清除成功，共清除 {total_cleared} 个缓存项",
            data={"cleared_count": total_cleared}
        )
    except HTTPException:
        # 重新抛出HTTP异常，保持原始状态码
        raise
    except Exception as e:
        logger.error(f"清除缓存失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="清除缓存失败"
        )


# ==================== 网站配置管理 ====================

@router.get("/webconfig", response_model=schemas.PaginatedResponse)
async def get_webconfigs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取网站配置列表（管理员）"""
    try:
        configs = crud.WebConfigCRUD.get_all(db, skip, limit)
        
        # 过滤配置
        if keyword:
            configs = [c for c in configs if keyword.lower() in c.k.lower() or keyword.lower() in c.v.lower()]
        
        total = len(configs)
        
        return schemas.PaginatedResponse(
            items=[{
                "id": config.id,
                "k": config.k,
                "v": config.v,
                "created_at": config.created_at,
                "updated_at": config.updated_at
            } for config in configs],
            total=total,
            page=skip // limit + 1,
            size=limit,
            pages=(total + limit - 1) // limit
        )
    except Exception as e:
        logger.error(f"获取网站配置列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取网站配置列表失败"
        )

@router.get("/webconfig/{config_id}", response_model=schemas.WebConfig)
async def get_webconfig(
    config_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取单个网站配置（管理员）"""
    try:
        config = crud.WebConfigCRUD.get_by_id(db, config_id)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="配置项不存在"
            )
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取网站配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取网站配置失败"
        )

@router.get("/webconfig/key/{key}", response_model=schemas.WebConfig)
async def get_webconfig_by_key(
    key: str,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """根据键获取网站配置（管理员）"""
    try:
        config = crud.WebConfigCRUD.get_by_key(db, key)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="配置项不存在"
            )
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"根据键获取网站配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="根据键获取网站配置失败"
        )

@router.post("/webconfig", response_model=schemas.WebConfig)
async def create_webconfig(
    config_data: schemas.WebConfigCreate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """创建网站配置（管理员）"""
    try:
        # 检查键是否已存在
        existing_config = crud.WebConfigCRUD.get_by_key(db, config_data.k)
        if existing_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="配置键已存在"
            )
        
        config = crud.WebConfigCRUD.create(db, config_data.dict())
        
        # 清除相关缓存
        cache_manager.clear_pattern("webconfig*")
        
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建网站配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建网站配置失败"
        )

@router.put("/webconfig/{config_id}", response_model=schemas.WebConfig)
async def update_webconfig(
    config_id: int,
    config_data: schemas.WebConfigUpdate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """更新网站配置（管理员）"""
    try:
        config = crud.WebConfigCRUD.update(db, config_id, config_data.dict(exclude_unset=True))
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="配置项不存在"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern("webconfig*")
        
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="update_webconfig",
                resource_type="webconfig",
                resource_id=config_id,
                description="更新网站配置",
                metadata=config_data.dict(exclude_unset=True)
            )
        except Exception:
            pass

        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新网站配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新网站配置失败"
        )

@router.put("/webconfig/key/{key}", response_model=schemas.WebConfig)
async def update_webconfig_by_key(
    key: str,
    config_data: schemas.WebConfigUpdate,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """根据键更新网站配置（管理员）"""
    try:
        if config_data.v is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="配置值不能为空"
            )
        
        config = crud.WebConfigCRUD.update_by_key(db, key, config_data.v)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="配置项不存在"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern("webconfig*")
        
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="update_webconfig_by_key",
                resource_type="webconfig",
                description=f"根据键更新网站配置: {key}"
            )
        except Exception:
            pass

        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"根据键更新网站配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="根据键更新网站配置失败"
        )

@router.delete("/webconfig/{config_id}")
async def delete_webconfig(
    config_id: int,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """删除网站配置（管理员）"""
    try:
        success = crud.WebConfigCRUD.delete(db, config_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="配置项不存在"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern("webconfig*")
        
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="delete_webconfig",
                resource_type="webconfig",
                resource_id=config_id,
                description="删除网站配置"
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="配置项删除成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除网站配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除网站配置失败"
        )

@router.delete("/webconfig/key/{key}")
async def delete_webconfig_by_key(
    key: str,
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """根据键删除网站配置（管理员）"""
    try:
        success = crud.WebConfigCRUD.delete_by_key(db, key)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="配置项不存在"
            )
        
        # 清除相关缓存
        cache_manager.clear_pattern("webconfig*")
        
        try:
            log_action(db,
                actor_id=current_admin.id,
                actor_type="admin",
                action="delete_webconfig_by_key",
                resource_type="webconfig",
                description=f"根据键删除网站配置: {key}"
            )
        except Exception:
            pass

        return schemas.ResponseModel(
            success=True,
            message="配置项删除成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"根据键删除网站配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="根据键删除网站配置失败"
        )

@router.get("/webconfig/all/dict")
async def get_all_webconfigs_dict(
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取所有网站配置的字典格式（管理员）"""
    try:
        configs_dict = crud.WebConfigCRUD.get_all_dict(db)
        return schemas.ResponseModel(
            success=True,
            message="获取配置成功",
            data=configs_dict
        )
    except Exception as e:
        logger.error(f"获取网站配置字典失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取网站配置字典失败"
        )

@router.get("/logs", response_model=schemas.PaginatedResponse)
async def get_system_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    actor_id: Optional[int] = Query(None),
    actor_type: Optional[str] = Query(None),
    actor_username: Optional[str] = Query(None, description="操作用户用户名(模糊)"),
    target_username: Optional[str] = Query(None, description="被操作用户名(模糊)"),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None, description="开始时间 YYYY-MM-DD 或 ISO8601"),
    end_time: Optional[str] = Query(None, description="结束时间 YYYY-MM-DD 或 ISO8601"),
    metadata_keyword: Optional[str] = Query(None, description="元数据模糊查询"),
    keyword: Optional[str] = Query(None),
    current_admin: models.User = Depends(get_admin_module_access),
    db: Session = Depends(get_db)
):
    """获取系统日志（管理员）"""
    try:
        q = db.query(models.SystemLog)
        if actor_id is not None:
            q = q.filter(models.SystemLog.actor_id == actor_id)
        if actor_type:
            q = q.filter(models.SystemLog.actor_type == actor_type)
        if action:
            q = q.filter(models.SystemLog.action == action)
        if resource_type:
            q = q.filter(models.SystemLog.resource_type == resource_type)
        if resource_id is not None:
            q = q.filter(models.SystemLog.resource_id == resource_id)
        if keyword:
            like = f"%{keyword}%"
            q = q.filter(
                func.coalesce(models.SystemLog.description, "").like(like)
            )

        # 按操作用户名筛选（模糊）
        if actor_username:
            user_ids = db.query(models.User.id).filter(models.User.username.like(f"%{actor_username}%")).all()
            user_ids = [uid for (uid,) in user_ids] if user_ids else [-1]
            q = q.filter(models.SystemLog.actor_id.in_(user_ids))

        # 按被操作用户名筛选（当 resource_type 为 user）
        if target_username:
            target_ids = db.query(models.User.id).filter(models.User.username.like(f"%{target_username}%")).all()
            target_ids = [uid for (uid,) in target_ids] if target_ids else [-1]
            q = q.filter(models.SystemLog.resource_type == "user", models.SystemLog.resource_id.in_(target_ids))

        # 时间范围筛选
        from datetime import datetime, timedelta
        def parse_dt(val: str):
            try:
                return datetime.fromisoformat(val)
            except Exception:
                try:
                    return datetime.strptime(val, "%Y-%m-%d")
                except Exception:
                    return None
        if start_time:
            dt = parse_dt(start_time)
            if dt:
                q = q.filter(models.SystemLog.created_at >= dt)
        if end_time:
            dt = parse_dt(end_time)
            if dt:
                # 包含当日到 23:59:59
                if dt.time().hour == 0 and dt.time().minute == 0 and dt.time().second == 0:
                    dt = dt + timedelta(days=1)
                q = q.filter(models.SystemLog.created_at <= dt)

        # 元数据模糊查询（将 JSON 转为字符串再匹配）
        if metadata_keyword:
            like = f"%{metadata_keyword}%"
            q = q.filter(cast(models.SystemLog.meta, String).like(like))

        total = q.count()
        logs = q.order_by(models.SystemLog.created_at.desc()).offset(skip).limit(limit).all()

        items = []
        for log in logs:
            items.append({
                "id": log.id,
                "actor_id": log.actor_id,
                "actor_type": log.actor_type,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "description": log.description,
                "metadata": log.meta,
                "ip": log.ip,
                "user_agent": log.user_agent,
                "created_at": log.created_at
            })

        return schemas.PaginatedResponse(
            items=items,
            total=total,
            page=skip // limit + 1,
            size=limit,
            pages=(total + limit - 1) // limit
        )
    except Exception as e:
        logger.error(f"获取系统日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取系统日志失败"
        )
