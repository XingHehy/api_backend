from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta
from . import models

class UserCRUD:
    """用户CRUD操作"""
    
    @staticmethod
    def create(db: Session, user_data: dict) -> models.User:
        """创建用户"""
        # 检查是否尝试创建管理员账户
        if user_data.get('is_admin', False):
            # 检查是否已存在管理员账户
            existing_admin = db.query(models.User).filter(models.User.is_admin == True).first()
            if existing_admin:
                raise ValueError("管理员账户已存在，不能创建新的管理员账户")
        
        db_user = models.User(**user_data)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    
    @staticmethod
    def create_admin(db: Session, admin_data: dict) -> models.User:
        """创建管理员账户（仅限系统初始化时使用）"""
        # 检查是否已存在管理员账户
        existing_admin = db.query(models.User).filter(models.User.is_admin == True).first()
        if existing_admin:
            raise ValueError("管理员账户已存在，不能创建新的管理员账户")
        
        # 强制设置为管理员
        admin_data['is_admin'] = True
        db_admin = models.User(**admin_data)
        db.add(db_admin)
        db.commit()
        db.refresh(db_admin)
        return db_admin
    
    @staticmethod
    def get_admin(db: Session) -> Optional[models.User]:
        """获取管理员账户"""
        return db.query(models.User).filter(models.User.is_admin == True).first()
    
    @staticmethod
    def is_admin_exists(db: Session) -> bool:
        """检查管理员账户是否存在"""
        return db.query(models.User).filter(models.User.is_admin == True).first() is not None
    
    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[models.User]:
        """根据ID获取用户"""
        return db.query(models.User).filter(models.User.id == user_id).first()
    
    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[models.User]:
        """根据用户名获取用户"""
        return db.query(models.User).filter(models.User.username == username).first()
    
    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[models.User]:
        """根据邮箱获取用户"""
        return db.query(models.User).filter(models.User.email == email).first()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[models.User]:
        """获取所有用户"""
        return db.query(models.User).offset(skip).limit(limit).all()
    
    @staticmethod
    def update(db: Session, user_id: int, user_data: dict) -> Optional[models.User]:
        """更新用户"""
        db_user = db.query(models.User).filter(models.User.id == user_id).first()
        if db_user:
            for key, value in user_data.items():
                if hasattr(db_user, key):
                    setattr(db_user, key, value)
            db.commit()
            db.refresh(db_user)
        return db_user
    
    @staticmethod
    def delete(db: Session, user_id: int) -> bool:
        """删除用户"""
        db_user = db.query(models.User).filter(models.User.id == user_id).first()
        if db_user:
            db.delete(db_user)
            db.commit()
            return True
        return False
    
    @staticmethod
    def change_password(db: Session, user_id: int, new_password_hash: str) -> bool:
        """修改密码"""
        db_user = db.query(models.User).filter(models.User.id == user_id).first()
        if db_user:
            db_user.password = new_password_hash
            db.commit()
            return True
        return False
    
    @staticmethod
    def update_balance(db: Session, user_id: int, new_balance: float) -> Optional[models.User]:
        """更新用户余额"""
        db_user = db.query(models.User).filter(models.User.id == user_id).first()
        if db_user:
            db_user.balance = new_balance
            db.commit()
            db.refresh(db_user)
            return db_user
        return None

class APICRUD:
    """API接口CRUD操作"""
    
    @staticmethod
    def create(db: Session, api_data: dict) -> models.API:
        """创建API接口"""
        # 不对这些字段做JSON校验，直接按字符串保存
        text_fields = [
            'request_params', 'request_headers', 'code_examples', 'error_codes',
            'tags', 'price_config', 'response_example', 'request_example'
        ]
        processed_data = api_data.copy()
        for field in text_fields:
            if field in processed_data:
                value = processed_data[field]
                processed_data[field] = '' if value is None else str(value)
        
        db_api = models.API(**processed_data)
        db.add(db_api)
        db.commit()
        db.refresh(db_api)
        return db_api
    
    @staticmethod
    def get_by_id(db: Session, api_id: int) -> Optional[models.API]:
        """根据ID获取API接口"""
        return db.query(models.API).filter(models.API.id == api_id).first()
    
    @staticmethod
    def get_by_endpoint(db: Session, endpoint: str) -> Optional[models.API]:
        """根据端点获取API接口"""
        return db.query(models.API).filter(models.API.endpoint == endpoint).first()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[models.API]:
        """获取所有API接口"""
        return db.query(models.API).offset(skip).limit(limit).all()
    
    
    @staticmethod
    def update(db: Session, api_id: int, api_data: dict) -> Optional[models.API]:
        """更新API接口"""
        import logging
        logger = logging.getLogger(__name__)
        
        db_api = db.query(models.API).filter(models.API.id == api_id).first()
        if db_api:
            logger.info(f"更新API {api_id}，更新数据: {api_data}")
            
            # 不做JSON校验，直接按字符串保存
            text_fields = [
                'request_params', 'request_headers', 'code_examples', 'error_codes',
                'tags', 'price_config', 'response_example', 'request_example'
            ]
            processed_data = api_data.copy()
            for field in text_fields:
                if field in processed_data:
                    value = processed_data[field]
                    processed_data[field] = '' if value is None else str(value)
            
            for key, value in processed_data.items():
                if hasattr(db_api, key):
                    old_value = getattr(db_api, key)
                    setattr(db_api, key, value)
                    logger.info(f"更新字段 {key}: {old_value} -> {value}")
                else:
                    logger.warning(f"API模型没有字段: {key}")
            db.commit()
            db.refresh(db_api)
            logger.info(f"API {api_id} 更新完成")
        else:
            logger.error(f"API {api_id} 不存在")
        return db_api
    
    @staticmethod
    def delete(db: Session, api_id: int) -> bool:
        """删除API接口"""
        db_api = db.query(models.API).filter(models.API.id == api_id).first()
        if db_api:
            db.delete(db_api)
            db.commit()
            return True
        return False
    
    @staticmethod
    def toggle_status(db: Session, api_id: int) -> Optional[models.API]:
        """切换API接口状态"""
        db_api = db.query(models.API).filter(models.API.id == api_id).first()
        if db_api:
            db_api.is_active = not db_api.is_active
            db.commit()
            db.refresh(db_api)
        return db_api
    
    @staticmethod
    def search(db: Session, keyword: str, skip: int = 0, limit: int = 100) -> List[models.API]:
        """搜索API接口"""
        return db.query(models.API).filter(
            models.API.title.contains(keyword) | 
            models.API.description.contains(keyword) |
            models.API.alias.contains(keyword)
        ).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_stats(db: Session) -> dict:
        """获取API统计信息"""
        total_apis = db.query(models.API).count()
        active_apis = db.query(models.API).filter(models.API.is_active == True).count()
        total_calls = db.query(func.sum(models.API.call_count)).scalar() or 0
        
        return {
            "total_apis": total_apis,
            "active_apis": active_apis,
            "total_calls": total_calls
        }



class OrderCRUD:
    """订单CRUD操作"""
    
    @staticmethod
    def create(db: Session, order_data: dict) -> models.Order:
        """创建订单"""
        db_order = models.Order(**order_data)
        db.add(db_order)
        db.commit()
        db.refresh(db_order)
        return db_order
    
    @staticmethod
    def get_by_id(db: Session, order_id: int) -> Optional[models.Order]:
        """根据ID获取订单"""
        return db.query(models.Order).filter(models.Order.id == order_id).first()
    
    @staticmethod
    def get_by_user_id(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[models.Order]:
        """获取用户的订单"""
        return db.query(models.Order).filter(
            models.Order.user_id == user_id
        ).order_by(desc(models.Order.created_at)).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[models.Order]:
        """获取所有订单"""
        return db.query(models.Order).order_by(desc(models.Order.created_at)).offset(skip).limit(limit).all()
    
    @staticmethod
    def update(db: Session, order_id: int, order_data: dict) -> Optional[models.Order]:
        """更新订单"""
        db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if db_order:
            for key, value in order_data.items():
                if hasattr(db_order, key):
                    setattr(db_order, key, value)
            db.commit()
            db.refresh(db_order)
        return db_order
    
    @staticmethod
    def get_revenue_stats(db: Session) -> dict:
        """获取收入统计"""
        total_revenue = db.query(func.sum(models.Order.amount)).filter(
            models.Order.payment_status == "paid"
        ).scalar() or 0.0
        
        # 使用正确的MySQL语法计算30天前的日期
        # 使用Python计算30天前的日期，避免MySQL INTERVAL语法问题
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        monthly_revenue = db.query(func.sum(models.Order.amount)).filter(
            models.Order.payment_status == "paid",
            models.Order.paid_at >= thirty_days_ago
        ).scalar() or 0.0
        
        return {
            "total_revenue": total_revenue,
            "monthly_revenue": monthly_revenue
        }

class CategoryCRUD:
    """分类CRUD操作"""
    
    @staticmethod
    def create(db: Session, category_data: dict) -> models.APICategory:
        """创建分类"""
        db_category = models.APICategory(**category_data)
        db.add(db_category)
        db.commit()
        db.refresh(db_category)
        return db_category
    
    @staticmethod
    def get_by_id(db: Session, category_id: int) -> Optional[models.APICategory]:
        """根据ID获取分类"""
        return db.query(models.APICategory).filter(models.APICategory.id == category_id).first()
    
    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[models.APICategory]:
        """根据名称获取分类"""
        return db.query(models.APICategory).filter(models.APICategory.name == name).first()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[models.APICategory]:
        """获取所有分类"""
        return db.query(models.APICategory).order_by(
            models.APICategory.sort_order,
            models.APICategory.name
        ).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_active(db: Session) -> List[models.APICategory]:
        """获取所有激活的分类"""
        return db.query(models.APICategory).filter(
            models.APICategory.is_active == True
        ).order_by(
            models.APICategory.sort_order,
            models.APICategory.name
        ).all()
    

    
    @staticmethod
    def update(db: Session, category_id: int, category_data: dict) -> Optional[models.APICategory]:
        """更新分类"""
        db_category = db.query(models.APICategory).filter(
            models.APICategory.id == category_id
        ).first()
        if db_category:
            for key, value in category_data.items():
                if hasattr(db_category, key):
                    setattr(db_category, key, value)
            db.commit()
            db.refresh(db_category)
        return db_category
    
    @staticmethod
    def delete(db: Session, category_id: int) -> bool:
        """删除分类"""
        db_category = db.query(models.APICategory).filter(
            models.APICategory.id == category_id
        ).first()
        if db_category:
            # 检查是否有API使用此分类
            api_count = db.query(models.API).filter(
                models.API.category_id == category_id
            ).count()
            if api_count > 0:
                raise ValueError("该分类下有API接口，无法删除")
            
            db.delete(db_category)
            db.commit()
            return True
        return False
    
    @staticmethod
    def get_api_count(db: Session, category_id: int) -> int:
        """获取分类下的API数量"""
        return db.query(models.API).filter(
            models.API.category_id == category_id,
            models.API.is_active == True
        ).count()

class SubscriptionCRUD:
    """订阅CRUD操作"""
    
    @staticmethod
    def generate_api_key(user_id: int, api_id: int, subscription_id: int = None) -> str:
        """生成唯一的API密钥"""
        import hashlib
        import time
        
        # 使用用户ID、API ID、时间戳和随机数生成唯一key
        timestamp = str(int(time.time() * 1000))  # 毫秒时间戳
        random_suffix = str(hash(str(time.time())))[-4:]  # 随机后缀
        
        # 生成基础字符串
        base_string = f"{user_id}_{api_id}_{timestamp}_{random_suffix}"
        if subscription_id:
            base_string = f"{subscription_id}_{base_string}"
        
        # 使用MD5生成32位哈希，然后格式化为UUID样式
        hash_obj = hashlib.md5(base_string.encode())
        hash_hex = hash_obj.hexdigest()
        
        # 格式化为UUID样式：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        api_key = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
        
        return api_key
    
    @staticmethod
    def create(db: Session, subscription_data: dict) -> models.Subscription:
        """创建订阅"""
        # 生成唯一的API密钥
        api_key = SubscriptionCRUD.generate_api_key(
            subscription_data['user_id'], 
            subscription_data['api_id']
        )
        
        # 确保key唯一性
        while db.query(models.Subscription).filter(models.Subscription.api_key == api_key).first():
            api_key = SubscriptionCRUD.generate_api_key(
                subscription_data['user_id'], 
                subscription_data['api_id']
            )
        
        subscription_data['api_key'] = api_key
        
        db_subscription = models.Subscription(**subscription_data)
        db.add(db_subscription)
        db.commit()
        db.refresh(db_subscription)
        return db_subscription
    
    @staticmethod
    def get_by_id(db: Session, subscription_id: int) -> Optional[models.Subscription]:
        """根据ID获取订阅"""
        return db.query(models.Subscription).filter(models.Subscription.id == subscription_id).first()
    
    @staticmethod
    def get_by_api_key(db: Session, api_key: str) -> Optional[models.Subscription]:
        """根据API密钥获取订阅"""
        from sqlalchemy.orm import joinedload
        return db.query(models.Subscription).options(
            joinedload(models.Subscription.user),
            joinedload(models.Subscription.api)
        ).filter(models.Subscription.api_key == api_key).first()
    
    @staticmethod
    def get_by_user_and_api(db: Session, user_id: int, api_id: int) -> Optional[models.Subscription]:
        """根据用户ID和API ID获取订阅"""
        return db.query(models.Subscription).filter(
            models.Subscription.user_id == user_id,
            models.Subscription.api_id == api_id,
            models.Subscription.status == "active"
        ).first()
    
    @staticmethod
    def get_by_user_id(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[models.Subscription]:
        """获取用户的订阅列表"""
        return db.query(models.Subscription).filter(
            models.Subscription.user_id == user_id
        ).order_by(desc(models.Subscription.created_at)).offset(skip).limit(limit).all()
    
    @staticmethod
    def update(db: Session, subscription_id: int, subscription_data: dict) -> Optional[models.Subscription]:
        """更新订阅"""
        db_subscription = db.query(models.Subscription).filter(
            models.Subscription.id == subscription_id
        ).first()
        if db_subscription:
            for key, value in subscription_data.items():
                if hasattr(db_subscription, key):
                    setattr(db_subscription, key, value)
            db.commit()
            db.refresh(db_subscription)
        return db_subscription
    
    @staticmethod
    def delete(db: Session, subscription_id: int) -> bool:
        """删除订阅"""
        db_subscription = db.query(models.Subscription).filter(
            models.Subscription.id == subscription_id
        ).first()
        if db_subscription:
            db.delete(db_subscription)
            db.commit()
            return True
        return False
    
    @staticmethod
    def is_valid_subscription(db: Session, api_key: str) -> bool:
        """验证订阅是否有效（未过期且状态为active）"""
        from datetime import datetime
        
        subscription = db.query(models.Subscription).filter(
            models.Subscription.api_key == api_key,
            models.Subscription.status == "active",
            models.Subscription.end_date > datetime.utcnow()
        ).first()
        
        return subscription is not None

class WebConfigCRUD:
    """网站配置CRUD操作"""
    
    @staticmethod
    def create(db: Session, config_data: dict) -> models.WebConfig:
        """创建配置项"""
        db_config = models.WebConfig(**config_data)
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        return db_config
    
    @staticmethod
    def get_by_id(db: Session, config_id: int) -> Optional[models.WebConfig]:
        """根据ID获取配置项"""
        return db.query(models.WebConfig).filter(models.WebConfig.id == config_id).first()
    
    @staticmethod
    def get_by_key(db: Session, key: str) -> Optional[models.WebConfig]:
        """根据键获取配置项"""
        return db.query(models.WebConfig).filter(models.WebConfig.k == key).first()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[models.WebConfig]:
        """获取所有配置项"""
        return db.query(models.WebConfig).order_by(models.WebConfig.k).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_all_dict(db: Session) -> dict:
        """获取所有配置项并返回字典格式"""
        configs = db.query(models.WebConfig).all()
        return {config.k: config.v for config in configs}
    
    @staticmethod
    def update(db: Session, config_id: int, config_data: dict) -> Optional[models.WebConfig]:
        """更新配置项"""
        db_config = db.query(models.WebConfig).filter(models.WebConfig.id == config_id).first()
        if db_config:
            for key, value in config_data.items():
                if hasattr(db_config, key):
                    setattr(db_config, key, value)
            db.commit()
            db.refresh(db_config)
        return db_config
    
    @staticmethod
    def update_by_key(db: Session, key: str, value: str) -> Optional[models.WebConfig]:
        """根据键更新配置项"""
        db_config = db.query(models.WebConfig).filter(models.WebConfig.k == key).first()
        if db_config:
            db_config.v = value
            db.commit()
            db.refresh(db_config)
        return db_config
    
    @staticmethod
    def delete(db: Session, config_id: int) -> bool:
        """删除配置项"""
        db_config = db.query(models.WebConfig).filter(models.WebConfig.id == config_id).first()
        if db_config:
            db.delete(db_config)
            db.commit()
            return True
        return False
    
    @staticmethod
    def delete_by_key(db: Session, key: str) -> bool:
        """根据键删除配置项"""
        db_config = db.query(models.WebConfig).filter(models.WebConfig.k == key).first()
        if db_config:
            db.delete(db_config)
            db.commit()
            return True
        return False
    
    @staticmethod
    def set_config(db: Session, key: str, value: str) -> models.WebConfig:
        """设置配置项（如果不存在则创建，存在则更新）"""
        db_config = db.query(models.WebConfig).filter(models.WebConfig.k == key).first()
        if db_config:
            db_config.v = value
            db.commit()
            db.refresh(db_config)
        else:
            db_config = models.WebConfig(k=key, v=value)
            db.add(db_config)
            db.commit()
            db.refresh(db_config)
        return db_config
    
    @staticmethod
    def get_config(db: Session, key: str, default: str = None) -> str:
        """获取配置值"""
        db_config = db.query(models.WebConfig).filter(models.WebConfig.k == key).first()
        return db_config.v if db_config else default