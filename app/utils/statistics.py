"""
公共统计模块
用于记录和统计API调用信息
"""
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.admin import models as admin_models

logger = logging.getLogger(__name__)

class APIStatistics:
    """API统计类"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def record_api_call(
        self, 
        api_key: str,
        api_alias: str,
        endpoint: str,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_method: str = "GET",
        response_status: int = 200,
        response_time: float = 0.0,
        is_success: bool = True,
        error_message: Optional[str] = None
    ):
        """
        记录API调用统计 - 只有验证成功后才统计
        
        Args:
            api_key: API密钥
            api_alias: API别名
            endpoint: 调用的端点
            client_ip: 客户端IP
            user_agent: 用户代理
            request_method: 请求方法
            response_status: 响应状态码
            response_time: 响应时间（毫秒）
            is_success: 是否成功
            error_message: 错误信息
        """
        try:
            # 根据api_key查找订阅信息
            subscription = self.db.query(admin_models.Subscription).filter(
                admin_models.Subscription.api_key == api_key
            ).first()
            
            if not subscription:
                logger.warning(f"未找到API密钥对应的订阅: {api_key}")
                return False
            
            # 根据api_alias查找API信息
            api = self.db.query(admin_models.API).filter(
                admin_models.API.alias == api_alias
            ).first()
            
            if not api:
                logger.warning(f"未找到API别名对应的接口: {api_alias}")
                return False
            
            # 不再写入APILog，仅更新API累计调用次数
            api.call_count += 1
            
            # 更新订阅使用统计
            subscription.used_calls += 1
            if subscription.remaining_calls is not None and subscription.remaining_calls > 0:
                subscription.remaining_calls -= 1
            
            self.db.commit()
            
            logger.info(f"API调用已记录: user_id={subscription.user_id}, api_id={api.id}, endpoint={endpoint}")
            return True
            
        except Exception as e:
            logger.error(f"记录API统计失败: {e}")
            self.db.rollback()
            return False
    
    def get_api_statistics(self, api_alias: str, days: int = 30) -> dict:
        """
        获取API统计信息
        
        Args:
            api_alias: API别名
            days: 统计天数
            
        Returns:
            统计信息字典
        """
        try:
            from datetime import timedelta
            
            # 查找API
            api = self.db.query(admin_models.API).filter(
                admin_models.API.alias == api_alias
            ).first()
            
            if not api:
                return {"error": f"未找到API: {api_alias}"}
            
            # 计算日期范围
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # 无明细日志时，直接返回API累计次数
            total_calls = api.call_count or 0
            success_calls = 0
            error_calls = 0
            
            return {
                "api_alias": api_alias,
                "api_title": api.title,
                "total_calls": total_calls,
                "success_calls": success_calls,
                "error_calls": error_calls,
                "success_rate": 0,
                "period_days": days,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取API统计失败: {e}")
            return {
                "api_alias": api_alias,
                "error": str(e)
            }
    
    def get_user_api_statistics(self, user_id: int, days: int = 30) -> dict:
        """
        获取用户API调用统计
        
        Args:
            user_id: 用户ID
            days: 统计天数
            
        Returns:
            用户统计信息字典
        """
        try:
            from datetime import timedelta
            
            # 计算日期范围
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # 用户维度统计改为聚合订阅使用计数
            subs = self.db.query(admin_models.Subscription).filter(
                admin_models.Subscription.user_id == user_id
            ).all()
            total_calls = sum((s.used_calls or 0) for s in subs)
            success_calls = 0
            error_calls = 0
            
            # 获取用户订阅的API列表
            subscriptions = self.db.query(admin_models.Subscription).filter(
                admin_models.Subscription.user_id == user_id,
                admin_models.Subscription.status == "active"
            ).all()
            
            subscribed_apis = []
            for sub in subscriptions:
                api = sub.api
                if api:
                    subscribed_apis.append({
                        "api_id": api.id,
                        "api_alias": api.alias,
                        "api_title": api.title,
                        "used_calls": sub.used_calls,
                        "remaining_calls": sub.remaining_calls
                    })
            
            return {
                "user_id": user_id,
                "total_calls": total_calls,
                "success_calls": success_calls,
                "error_calls": error_calls,
                "success_rate": 0,
                "subscribed_apis": subscribed_apis,
                "period_days": days,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取用户API统计失败: {e}")
            return {
                "user_id": user_id,
                "error": str(e)
            }

def get_api_statistics(db: Session) -> APIStatistics:
    """获取API统计实例"""
    return APIStatistics(db)
