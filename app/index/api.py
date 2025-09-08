from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.database import get_db
from app.admin import models as admin_models
from app.admin import crud as admin_crud
from app.cache import cache_manager
from app.auth import get_current_user
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["首页"])

# 请求模型
class PurchaseRequest(BaseModel):
    price_type: str = "monthly"

def calculate_api_price(api, price_type=None):
    """计算API价格"""
    try:
        if api.is_free:
            return 0
        
        # 解析价格配置
        if api.price_config:
            if isinstance(api.price_config, str):
                price_config = json.loads(api.price_config)
            else:
                price_config = api.price_config
            
            # 根据价格类型获取价格
            target_price_type = price_type or (api.price_type.value if api.price_type else "monthly")
            
            if target_price_type == "monthly" and "monthly" in price_config:
                return price_config["monthly"]
            elif target_price_type == "quarterly" and "quarterly" in price_config:
                return price_config["quarterly"]
            elif target_price_type == "yearly" and "yearly" in price_config:
                return price_config["yearly"]
        
        return 0
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.error(f"计算API价格失败: {e}")
        return 0

def get_api_pricing_options(api):
    """获取API的所有价格选项"""
    try:
        if api.is_free:
            return []
        
        options = []
        
        # 解析价格配置
        if api.price_config:
            if isinstance(api.price_config, str):
                price_config = json.loads(api.price_config)
            else:
                price_config = api.price_config
            
            
            # 月付
            if "monthly" in price_config and price_config["monthly"] > 0:
                options.append({
                    "type": "monthly",
                    "name": "月付",
                    "price": price_config["monthly"],
                    "unit": "元/月"
                })
            
            # 季付
            if "quarterly" in price_config and price_config["quarterly"] > 0:
                options.append({
                    "type": "quarterly",
                    "name": "季付",
                    "price": price_config["quarterly"],
                    "unit": "元/季"
                })
            
            # 年付
            if "yearly" in price_config and price_config["yearly"] > 0:
                options.append({
                    "type": "yearly",
                    "name": "年付",
                    "price": price_config["yearly"],
                    "unit": "元/年"
                })
        
        return options
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.error(f"获取API价格选项失败: {e}")
        return []

# ==================== 首页统计 ====================

@router.get("/stats")
async def get_home_stats(db: Session = Depends(get_db)):
    """获取首页统计信息"""
    try:
        # 获取基本统计
        total_apis = db.query(admin_models.API).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        ).count()
        
        total_users = db.query(admin_models.User).filter(
            admin_models.User.is_active == True
        ).count()
        
        total_calls = db.query(admin_models.API).with_entities(
            func.sum(admin_models.API.call_count)
        ).scalar() or 0
        
        # 获取热门API接口
        popular_apis = db.query(admin_models.API).options(
            joinedload(admin_models.API.category)
        ).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        ).order_by(admin_models.API.call_count.desc()).limit(10).all()
        
        # 获取最新API接口
        latest_apis = db.query(admin_models.API).options(
            joinedload(admin_models.API.category)
        ).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        ).order_by(admin_models.API.created_at.desc()).limit(5).all()
        
        # 获取分类统计
        categories = db.query(
            admin_models.APICategory.name,
            func.count(admin_models.API.id).label('count')
        ).join(
            admin_models.API, admin_models.APICategory.id == admin_models.API.category_id
        ).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        ).group_by(admin_models.APICategory.name).order_by(
            func.count(admin_models.API.id).desc()
        ).limit(10).all()
        
        return {
            "total_apis": total_apis,
            "total_users": total_users,
            "total_calls": total_calls,
            "popular_apis": [
                {
                    "id": api.id,
                    "title": api.title,
                    "alias": api.alias,
                    "description": api.description,
                    "call_count": api.call_count,
                    "category": api.category.name if api.category else None
                } for api in popular_apis
            ],
            "latest_apis": [
                {
                    "id": api.id,
                    "title": api.title,
                    "alias": api.alias,
                    "description": api.description,
                    "created_at": api.created_at,
                    "category": api.category.name if api.category else None
                } for api in latest_apis
            ],
            "categories": [
                {
                    "name": category.name,
                    "count": category.count
                } for category in categories
            ]
        }
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"获取首页统计信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取首页统计信息失败"
        )

# ==================== 搜索功能 ====================

@router.get("/search")
async def search_apis(
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类筛选"),
    method: Optional[str] = Query(None, description="请求方式筛选"),
    is_free: Optional[bool] = Query(None, description="是否免费"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(20, ge=1, le=100, description="返回的记录数"),
    db: Session = Depends(get_db)
):
    """搜索API接口"""
    try:
        # 构建查询
        query = db.query(admin_models.API).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        )
        
        # 关键词搜索
        if keyword and keyword.strip():
            keyword = keyword.strip()
            query = query.filter(
                admin_models.API.title.contains(keyword) | 
                admin_models.API.description.contains(keyword) |
                admin_models.API.alias.contains(keyword)
            )
        
        # 分类筛选
        if category:
            query = query.join(admin_models.APICategory).filter(
                admin_models.APICategory.name == category
            )
        
        # 请求方式筛选
        if method:
            query = query.filter(admin_models.API.method == method)
        
        # 是否免费筛选
        if is_free is not None:
            query = query.filter(admin_models.API.is_free == is_free)
        
        # 获取总数
        total = query.count()
        
        # 执行查询（分页）
        apis = query.options(joinedload(admin_models.API.category)).order_by(
            admin_models.API.call_count.desc()
        ).offset(skip).limit(limit).all()
        
        # 转换为响应格式
        results = []
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
                "request_headers": api.request_headers or "",
                "response_example": api.response_example or "",
                "code_examples": api.code_examples or "",
                "error_codes": api.error_codes or "",
                "is_active": api.is_active,
                "is_public": api.is_public,
                "is_free": api.is_free,
                "call_count": api.call_count,
                "category_id": api.category_id,
                "category": api.category.name if api.category else None,
                "tags": api.tags or "[]",
                "price_config": api.price_config or "{}",
                "version": api.version or "1.0.0",
                "deprecated": api.deprecated,
                "created_at": api.created_at,
                "updated_at": api.updated_at
            }
            results.append(api_dict)
        
        return {
            "keyword": keyword,
            "category": category,
            "method": method,
            "is_free": is_free,
            "total": total,
            "skip": skip,
            "limit": limit,
            "page": skip // limit + 1 if limit > 0 else 1,
            "pages": (total + limit - 1) // limit if limit > 0 else 1,
            "results": results
        }
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"搜索API接口失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="搜索API接口失败"
        )

# ==================== 分类浏览 ====================

@router.get("/categories")
async def get_categories(db: Session = Depends(get_db)):
    """获取所有分类"""
    try:
        categories = db.query(
            admin_models.APICategory.name,
            func.count(admin_models.API.id).label('count')
        ).join(
            admin_models.API, admin_models.APICategory.id == admin_models.API.category_id
        ).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        ).group_by(admin_models.APICategory.name).order_by(
            func.count(admin_models.API.id).desc()
        ).all()
        
        return [
            {
                "name": category.name,
                "count": category.count
            } for category in categories
        ]
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"获取分类列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取分类列表失败"
        )

@router.get("/categories/{category_name}/apis")
async def get_apis_by_category(
    category_name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取指定分类下的API接口"""
    try:
        apis = db.query(admin_models.API).join(
            admin_models.APICategory, admin_models.APICategory.id == admin_models.API.category_id
        ).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True,
            admin_models.APICategory.name == category_name
        ).options(joinedload(admin_models.API.category)).offset(skip).limit(limit).all()
        
        total = db.query(admin_models.API).join(
            admin_models.APICategory, admin_models.APICategory.id == admin_models.API.category_id
        ).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True,
            admin_models.APICategory.name == category_name
        ).count()
        
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
                "is_free": api.is_free,
                "category": api.category.name if api.category else None,
                "tags": api.tags,
                "call_count": api.call_count,
                "success_count": api.success_count,
                "error_count": api.error_count,
                "created_at": api.created_at
            }
            items.append(api_dict)
        
        return {
            "category": category_name,
            "total": total,
            "page": skip // limit + 1,
            "size": limit,
            "pages": (total + limit - 1) // limit,
            "items": items
        }
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"获取分类API接口失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取分类API接口失败"
        )

# ==================== 标签浏览 ====================

@router.get("/tags")
async def get_tags(db: Session = Depends(get_db)):
    """获取所有标签"""
    try:
        # 从API接口中提取标签
        apis = db.query(admin_models.API.tags).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True,
            admin_models.API.tags.is_not(None)
        ).all()
        
        # 统计标签使用次数
        tag_count = {}
        for api in apis:
            if api.tags:
                for tag in api.tags:
                    tag_count[tag] = tag_count.get(tag, 0) + 1
        
        # 按使用次数排序
        sorted_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)
        
        return [
            {
                "name": tag,
                "count": count
            } for tag, count in sorted_tags
        ]
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"获取标签列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取标签列表失败"
        )

@router.get("/tags/{tag_name}/apis")
async def get_apis_by_tag(
    tag_name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取指定标签下的API接口"""
    try:
        apis = db.query(admin_models.API).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True,
            admin_models.API.tags.contains([tag_name])
        ).offset(skip).limit(limit).all()
        
        total = db.query(admin_models.API).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True,
            admin_models.API.tags.contains([tag_name])
        ).count()
        
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
                "is_free": api.is_free,
                "category": api.category,
                "tags": api.tags,
                "call_count": api.call_count,
                "success_count": api.success_count,
                "error_count": api.error_count,
                "created_at": api.created_at
            }
            items.append(api_dict)
        
        return {
            "tag": tag_name,
            "total": total,
            "page": skip // limit + 1,
            "size": limit,
            "pages": (total + limit - 1) // limit,
            "items": items
        }
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"获取标签API接口失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取标签API接口失败"
        )

# ==================== API详情 ====================

@router.get("/apis/{api_id}")
async def get_api_detail(
    api_id: int,
    db: Session = Depends(get_db)
):
    """获取API详情"""
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
                detail="API不存在"
            )
        
        # 转换为响应格式
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
            "request_headers": api.request_headers or "",
            "response_example": api.response_example or "",
            "code_examples": api.code_examples or "",
            "error_codes": api.error_codes or "",
            "is_active": api.is_active,
            "is_public": api.is_public,
            "is_free": api.is_free,
            "call_count": api.call_count,
            "category_id": api.category_id,
            "category": api.category.name if api.category else None,
            "tags": api.tags or "[]",
            "price_config": api.price_config or "{}",
            "version": api.version or "1.0.0",
            "deprecated": api.deprecated,
            "created_at": api.created_at,
            "updated_at": api.updated_at,
            "status": "online" if api.is_active else "offline"
        }
        
        return api_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取API详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取API详情失败"
        )

# ==================== API购买 ====================

@router.post("/apis/{api_id}/purchase")
async def purchase_api(
    api_id: int,
    purchase_data: PurchaseRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """购买API（余额支付）"""
    try:
        # 获取API信息
        api = db.query(admin_models.API).filter(
            admin_models.API.id == api_id,
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        ).first()
        
        if not api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API不存在"
            )
        
        # 免费接口也需要购买，只是价格可能为0
        
        # 从请求数据中获取价格类型
        price_type = purchase_data.price_type
        
        # 计算价格
        price = calculate_api_price(api, price_type)
        
        # 价格小于0属于配置错误，等于0视为免费但需要订阅
        if price < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API价格配置错误"
            )
        
        # 使用传入的当前用户
        current_user_id = current_user.id
        
        # 获取用户信息
        user = db.query(admin_models.User).filter(
            admin_models.User.id == current_user_id,
            admin_models.User.is_active == True
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 检查余额
        if price > 0 and user.balance < price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"余额不足，当前余额：¥{user.balance}，需要：¥{price}"
            )
        
        # 扣费
        if price > 0:
            user.balance -= price
        
        # 生成订单号（使用专业的订单号生成器）
        import time
        import random
        import threading
        
        class OrderNumberGenerator:
            """订单号生成器，使用时间戳和用户ID的实现"""
            
            def __init__(self):
                """初始化订单号生成器"""
                self.lock = threading.Lock()
                self.last_timestamp = 0
                self.sequence = 0
                self.max_sequence = 99  # 序列号最大值，2位数字
            
            def generate(self, user_id: str, prefix: str = "") -> str:
                """
                生成唯一订单号，包含时间戳和用户ID信息
                
                订单号格式: [前缀][时间戳][用户ID(截取)][序列号][随机数]
                例如: 881693807822123456789
                
                :param user_id: 用户ID，用于关联订单和用户
                :param prefix: 订单号前缀，可选
                :return: 生成的唯一订单号
                """
                if not user_id:
                    raise ValueError("用户ID不能为空")
                    
                with self.lock:  # 确保线程安全
                    # 获取当前时间戳（精确到秒）
                    current_timestamp = int(time.time())
                    
                    # 处理同一秒内的多次请求
                    if current_timestamp == self.last_timestamp:
                        self.sequence += 1
                        # 如果序列号超过最大值，等待到下一秒
                        if self.sequence > self.max_sequence:
                            time.sleep(1)
                            current_timestamp = int(time.time())
                            self.sequence = 0
                    else:
                        self.sequence = 0
                    
                    self.last_timestamp = current_timestamp
                    
                    # 生成2位随机数，增加唯一性
                    random_num = random.randint(10, 99)
                    
                    # 处理用户ID，取后4位（确保长度一致）
                    # 如果用户ID不足4位，前面补0
                    user_id_suffix = str(user_id)[-4:].zfill(4)
                    
                    # 组合订单号各部分
                    order_parts = []
                    if prefix:
                        order_parts.append(prefix)
                    
                    order_parts.extend([
                        f"{current_timestamp}",  # 时间戳部分 (10位)
                        user_id_suffix,          # 用户ID后4位 (4位)
                        f"{self.sequence:02d}",  # 序列号 (2位，补零)
                        f"{random_num}"          # 随机数 (2位)
                    ])
                    
                    return "".join(order_parts)
        
        # 创建生成器实例并生成订单号
        generator = OrderNumberGenerator()
        order_no = generator.generate(user_id=str(current_user_id), prefix="88")
        
        # 生成备注信息
        price_type_text = {
            "monthly": "月",
            "quarterly": "季", 
            "yearly": "年"
        }.get(price_type, "月")
        
        # 检查是否已有该API的订阅
        existing_subscription = db.query(admin_models.Subscription).filter(
            admin_models.Subscription.user_id == current_user_id,
            admin_models.Subscription.api_id == api_id,
            admin_models.Subscription.status == "active"
        ).first()
        
        if existing_subscription:
            # 续费
            remark = f"续费[{api_id}]{api.title} 1 {price_type_text}"
        else:
            # 新购
            remark = f"新购[{api_id}]{api.title} 1 {price_type_text}"
        
        # 创建订单记录
        from datetime import datetime, timedelta
        order = admin_models.Order(
            user_id=current_user_id,
            api_id=api_id,
            order_no=order_no,  # 订单号
            amount=price,
            status="completed",  # 订单完成
            payment_method="balance",
            payment_status="paid",  # 支付完成
            paid_at=datetime.now(),
            remark=remark  # 订单备注
        )
        db.add(order)
        db.flush()  # 获取订单ID
        
        # 计算订阅时间
        start_date = datetime.now()
        if price_type == "monthly":
            end_date = start_date + timedelta(days=30)
        elif price_type == "quarterly":
            end_date = start_date + timedelta(days=90)
        elif price_type == "yearly":
            end_date = start_date + timedelta(days=365)
        else:
            end_date = start_date + timedelta(days=30)  # 默认月付
        
        if existing_subscription:
            # 续费：延长结束时间（从当前结束时间开始延长）
            current_end_date = existing_subscription.end_date
            if current_end_date > datetime.now():
                # 如果订阅还未过期，从当前结束时间延长
                if price_type == "monthly":
                    existing_subscription.end_date = current_end_date + timedelta(days=30)
                elif price_type == "quarterly":
                    existing_subscription.end_date = current_end_date + timedelta(days=90)
                elif price_type == "yearly":
                    existing_subscription.end_date = current_end_date + timedelta(days=365)
                else:
                    existing_subscription.end_date = current_end_date + timedelta(days=30)
            else:
                # 如果订阅已过期，从当前时间开始计算
                existing_subscription.start_date = datetime.now()
                existing_subscription.end_date = end_date
            existing_subscription.updated_at = datetime.now()
        else:
            # 新购：创建新订阅
            subscription_data = {
                "user_id": current_user_id,
                "api_id": api_id,
                "start_date": start_date,
                "end_date": end_date,
                "status": "active",
                "used_calls": 0,
                "remaining_calls": None,  # 无限制调用
                "auto_renew": False
            }
            subscription = admin_crud.SubscriptionCRUD.create(db, subscription_data)
        
        db.commit()
        
        return {
            "success": True,
            "message": "购买成功",
            "order_id": order.id,
            "remaining_balance": user.balance
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"购买API失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="购买失败"
        )

# ==================== 推荐接口 ====================

@router.get("/recommendations")
async def get_recommendations(
    limit: int = Query(10, ge=1, le=50, description="推荐数量"),
    db: Session = Depends(get_db)
):
    """获取推荐API接口"""
    try:
        # 基于调用次数和成功率推荐
        apis = db.query(admin_models.API).filter(
            admin_models.API.is_active == True,
            admin_models.API.is_public == True
        ).order_by(
            admin_models.API.call_count.desc(),
            admin_models.API.success_count.desc()
        ).limit(limit).all()
        
        # 转换为响应格式
        recommendations = []
        for api in apis:
            # 计算成功率
            success_rate = 0.0
            if api.call_count > 0:
                success_rate = (api.success_count / api.call_count) * 100
            
            api_dict = {
                "id": api.id,
                "title": api.title,
                "alias": api.alias,
                "description": api.description,
                "endpoint": api.endpoint,
                "method": api.method,
                "return_format": api.return_format,
                "is_free": api.is_free,
                "category": api.category,
                "tags": api.tags,
                "call_count": api.call_count,
                "success_count": api.success_count,
                "error_count": api.error_count,
                "success_rate": round(success_rate, 2),
                "created_at": api.created_at
            }
            recommendations.append(api_dict)
        
        return {
            "total": len(recommendations),
            "recommendations": recommendations
        }
    except HTTPException:

        # 重新抛出HTTP异常，保持原始状态码

        raise

    except Exception as e:
        logger.error(f"获取推荐API接口失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取推荐API接口失败"
        )

# ==================== API调用 ====================

@router.get("/api/call/{api_alias}")
async def call_api(
    api_alias: str,
    api_key: str = Query(..., description="API访问密钥"),
    db: Session = Depends(get_db)
):
    """调用API接口"""
    from app.auth import verify_api_key
    
    try:
        # 验证API密钥
        subscription = verify_api_key(api_key, db)
        
        # 获取API信息
        api = db.query(admin_models.API).filter(
            admin_models.API.alias == api_alias,
            admin_models.API.is_active == True
        ).first()
        
        if not api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API接口不存在"
            )
        
        # 检查订阅是否匹配该API
        if subscription.api_id != api.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API密钥不匹配此接口"
            )
        
        # 检查调用次数限制（如果有）
        if subscription.remaining_calls is not None and subscription.remaining_calls <= 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="API调用次数已用完"
            )
        
        # 这里应该实际调用API，目前返回模拟数据
        # 实际实现中，这里会：
        # 1. 解析API的endpoint和method
        # 2. 构建请求参数
        # 3. 发送HTTP请求到目标API
        # 4. 记录调用日志
        # 5. 更新调用统计
        
        # 更新调用统计
        subscription.used_calls += 1
        if subscription.remaining_calls is not None:
            subscription.remaining_calls -= 1
        
        api.call_count += 1
        api.success_count += 1
        
        db.commit()
        
        # 更新计数：已由 verify_and_record_api_call 内部完成
        
        return {
            "success": True,
            "message": "API调用成功",
            "data": {
                "api_title": api.title,
                "api_alias": api.alias,
                "used_calls": subscription.used_calls,
                "remaining_calls": subscription.remaining_calls,
                "result": "模拟API返回数据"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API调用失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API调用失败"
        )

# ==================== 网站配置 ====================

@router.get("/webconfig/public")
async def get_public_webconfigs(db: Session = Depends(get_db)):
    """获取公开的网站配置（无需登录）"""
    try:
        # 只返回前端需要的公开配置
        public_configs = [
            "site.title",
            "site.description", 
            "site.keywords",
            "site.author",
            "site.copyright",
            "site.icp",
            "site.beian",
            "site.founded_date",
            "contact.email",
            "contact.phone",
            "contact.address",
            "ui.logo",
            "ui.favicon",
            "ui.footer_text",
            "ui.theme",
            "system.maintenance_mode",
            "system.maintenance_message",
            "system.registration_enabled"
        ]
        
        configs = {}
        for key in public_configs:
            config = admin_crud.WebConfigCRUD.get_by_key(db, key)
            if config:
                configs[key] = config.v
        
        return {
            "success": True,
            "message": "获取网站配置成功",
            "data": configs
        }
    except Exception as e:
        logger.error(f"获取公开网站配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取网站配置失败"
        )

@router.get("/webconfig/site-info")
async def get_site_info(db: Session = Depends(get_db)):
    """获取网站基本信息（用于首页显示）"""
    try:
        # 获取网站基本信息
        site_configs = {
            "title": admin_crud.WebConfigCRUD.get_config(db, "site.title", "API管理系统"),
            "description": admin_crud.WebConfigCRUD.get_config(db, "site.description", "专业的API接口管理平台"),
            "keywords": admin_crud.WebConfigCRUD.get_config(db, "site.keywords", "API,接口管理,接口文档"),
            "author": admin_crud.WebConfigCRUD.get_config(db, "site.author", "API管理系统"),
            "copyright": admin_crud.WebConfigCRUD.get_config(db, "site.copyright", "© 2024 API管理系统"),
            "founded_date": admin_crud.WebConfigCRUD.get_config(db, "site.founded_date", "2024-01-01"),
            "logo": admin_crud.WebConfigCRUD.get_config(db, "ui.logo", ""),
            "favicon": admin_crud.WebConfigCRUD.get_config(db, "ui.favicon", ""),
            "footer_text": admin_crud.WebConfigCRUD.get_config(db, "ui.footer_text", "API管理系统"),
            "maintenance_mode": admin_crud.WebConfigCRUD.get_config(db, "system.maintenance_mode", "false"),
            "maintenance_message": admin_crud.WebConfigCRUD.get_config(db, "system.maintenance_message", "系统维护中"),
            "registration_enabled": admin_crud.WebConfigCRUD.get_config(db, "system.registration_enabled", "true")
        }
        
        return {
            "success": True,
            "message": "获取网站信息成功",
            "data": site_configs
        }
    except Exception as e:
        logger.error(f"获取网站信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取网站信息失败"
        )

@router.get("/webconfig/contact")
async def get_contact_info(db: Session = Depends(get_db)):
    """获取联系信息"""
    try:
        contact_configs = {
            "email": admin_crud.WebConfigCRUD.get_config(db, "contact.email", ""),
            "phone": admin_crud.WebConfigCRUD.get_config(db, "contact.phone", ""),
            "address": admin_crud.WebConfigCRUD.get_config(db, "contact.address", ""),
            "qq": admin_crud.WebConfigCRUD.get_config(db, "contact.qq", ""),
            "wechat": admin_crud.WebConfigCRUD.get_config(db, "contact.wechat", "")
        }
        
        return {
            "success": True,
            "message": "获取联系信息成功",
            "data": contact_configs
        }
    except Exception as e:
        logger.error(f"获取联系信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取联系信息失败"
        )
