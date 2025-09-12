from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Float, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class PriceType(str, enum.Enum):
    """价格类型枚举"""
    PER_CALL = "per_call"      # 按次付费
    MONTHLY = "monthly"         # 月付
    QUARTERLY = "quarterly"     # 季付
    YEARLY = "yearly"           # 年付
    LIFETIME = "lifetime"       # 终身付费

class ParameterType(str, enum.Enum):
    """参数类型枚举"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    FILE = "file"

class User(Base):
    """用户模型"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    balance = Column(Float, default=0.0, comment="账户余额")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    orders = relationship("Order", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")
    
    def __init__(self, **kwargs):
        # 移除有问题的管理员账户检查，这个检查应该在业务逻辑层处理
        super().__init__(**kwargs)

class API(Base):
    """API接口模型"""
    __tablename__ = "apis"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 基本信息
    title = Column(String(200), nullable=False, comment="接口标题（中文）")
    alias = Column(String(100), unique=True, index=True, nullable=False, comment="别名（英文标识，唯一）")
    description = Column(Text, comment="简介说明")
    
    # 接口配置
    endpoint = Column(String(500), nullable=False, comment="接口地址")
    method = Column(String(20), nullable=False, comment="请求方式：GET,POST,PUT,DELETE等")
    return_format = Column(String(50), default="JSON", comment="返回格式")
    
    # 请求参数配置
    request_params = Column(Text, comment="请求参数配置（JSON字符串）")
    request_example = Column(Text, comment="请求示例")
    request_headers = Column(Text, comment="请求头配置（JSON字符串）")
    
    # 响应信息
    response_example = Column(Text, comment="返回示例")
    
    # 代码示例
    code_examples = Column(Text, comment="代码示例（JSON字符串）")
    
    # 错误处理
    error_codes = Column(Text, comment="错误代码及说明（JSON字符串）")
    
    # 接口状态
    is_active = Column(Boolean, default=True, comment="是否启用")
    is_public = Column(Boolean, default=True, comment="是否公开")
    is_free = Column(Boolean, default=True, comment="是否免费")
    
    # 统计信息
    call_count = Column(Integer, default=0, comment="调用次数")
    
    # 分类标签
    category_id = Column(Integer, ForeignKey("api_categories.id"), comment="分类ID")
    tags = Column(Text, comment="标签列表（JSON字符串）")
    
    # 价格信息 - 支持多种付费模式
    price_config = Column(Text, comment="价格配置（JSON字符串）")
    price_type = Column(Enum(PriceType), default=PriceType.PER_CALL, comment="价格类型")
    
    # 版本信息
    version = Column(String(20), default="1.0.0", comment="接口版本")
    deprecated = Column(Boolean, default=False, comment="是否已废弃")
    
    # 关联信息
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    category = relationship("APICategory")
    orders = relationship("Order", back_populates="api")
    subscriptions = relationship("Subscription", back_populates="api")

# APIPricing 模型已删除，价格信息现在直接存储在 API 模型中

class Subscription(Base):
    """订阅模型"""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    api_id = Column(Integer, ForeignKey("apis.id"), nullable=False)
    # pricing_id = Column(Integer, ForeignKey("api_pricing.id"), nullable=True)  # api_pricing表已删除
    
    # API访问密钥
    api_key = Column(String(64), unique=True, nullable=False, comment="API访问密钥，用于身份验证和到期判断")
    
    # 订阅信息
    start_date = Column(DateTime(timezone=True), nullable=False, comment="开始日期")
    end_date = Column(DateTime(timezone=True), nullable=False, comment="结束日期")
    status = Column(String(20), default="active", comment="状态：active, expired, cancelled")
    
    # 使用统计
    used_calls = Column(Integer, default=0, comment="已使用调用次数")
    remaining_calls = Column(Integer, comment="剩余调用次数")
    
    # 自动续费
    auto_renew = Column(Boolean, default=False, comment="是否自动续费")
    next_billing_date = Column(DateTime(timezone=True), comment="下次计费日期")
    
    # 创建时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", back_populates="subscriptions")
    api = relationship("API", back_populates="subscriptions")
    # pricing = relationship("APIPricing")  # APIPricing模型已删除

class SystemLog(Base):
    """系统操作日志"""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    # 行为主体
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="操作者用户ID，可为空表示系统")
    actor_type = Column(String(20), default="system", comment="操作者类型：user/admin/system")

    # 行为与资源
    action = Column(String(100), nullable=False, comment="动作，如: login, logout, recharge, consume, create_api, update_user 等")
    resource_type = Column(String(50), nullable=True, comment="资源类型：user/api/order/category/webconfig/system")
    resource_id = Column(Integer, nullable=True, comment="资源ID，可为空")

    # 描述与扩展
    description = Column(Text, comment="描述")
    meta = Column(JSON, comment="额外数据JSON")

    # 客户端信息
    ip = Column(String(50), comment="IP 地址")
    user_agent = Column(String(500), comment="User-Agent")

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    actor = relationship("User")

class Order(Base):
    """订单模型"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    api_id = Column(Integer, ForeignKey("apis.id"))
    # pricing_id = Column(Integer, ForeignKey("api_pricing.id"), nullable=True)  # api_pricing表已删除
    
    # 订单信息
    order_no = Column(String(50), unique=True, index=True, comment="订单号")
    amount = Column(Float, nullable=False, comment="订单金额")
    quantity = Column(Integer, default=1, comment="购买数量")
    status = Column(String(20), default="pending", comment="订单状态")
    
    # 支付信息
    payment_method = Column(String(50), comment="支付方式")
    payment_status = Column(String(20), default="unpaid", comment="支付状态")
    paid_at = Column(DateTime(timezone=True), comment="支付时间")
    
    # 备注信息
    remark = Column(String(200), comment="订单备注")
    
    # 时间信息
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", back_populates="orders")
    api = relationship("API", back_populates="orders")
    # pricing = relationship("APIPricing")  # APIPricing模型已删除


class APICategory(Base):
    """API分类模型"""
    __tablename__ = "api_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="分类名称")
    description = Column(Text, comment="分类描述")
    sort_order = Column(Integer, default=0, comment="排序顺序")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 与API的关系
    apis = relationship("API", back_populates="category")

    

class WebConfig(Base):
    """网站配置模型"""
    __tablename__ = "webconfig"
    
    id = Column(Integer, primary_key=True, index=True)
    k = Column(String(100), unique=True, nullable=False, comment="配置键")
    v = Column(Text, nullable=False, comment="配置值")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), comment="更新时间")
