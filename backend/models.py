from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def uid():
    return str(uuid4())

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default='student')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    canteen_id: Mapped[str | None] = mapped_column(ForeignKey('canteens.id'), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[str] = mapped_column(String(40))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

class Profile(Base):
    __tablename__ = 'profiles'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

class Canteen(Base):
    __tablename__ = 'canteens'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80), unique=True)

class Window(Base):
    __tablename__ = 'windows'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    canteen_id: Mapped[str] = mapped_column(ForeignKey('canteens.id'))
    name: Mapped[str] = mapped_column(String(80))

class Dish(Base):
    __tablename__ = 'dishes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    window_id: Mapped[str] = mapped_column(ForeignKey('windows.id'))
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(20))
    price: Mapped[float] = mapped_column(Float)
    portion_g: Mapped[float] = mapped_column(Float)
    kcal: Mapped[float] = mapped_column(Float)
    protein: Mapped[float] = mapped_column(Float)
    fat: Mapped[float] = mapped_column(Float)
    carbs: Mapped[float] = mapped_column(Float)
    ingredients: Mapped[list] = mapped_column(JSON, default=list)
    allergens: Mapped[list | None] = mapped_column(JSON, nullable=True)
    nutrition_source: Mapped[str] = mapped_column(String(200), default='示例配方估算')
    image_url: Mapped[str] = mapped_column(String(300), default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

class MenuEntry(Base):
    __tablename__ = 'menu_entries'
    __table_args__ = (UniqueConstraint('date', 'meal', 'dish_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    date: Mapped[str] = mapped_column(String(10))
    meal: Mapped[str] = mapped_column(String(10))
    dish_id: Mapped[str] = mapped_column(ForeignKey('dishes.id'))
    available: Mapped[bool] = mapped_column(Boolean, default=True)

class MealRecord(Base):
    __tablename__ = 'meal_records'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    date: Mapped[str] = mapped_column(String(10))
    meal: Mapped[str] = mapped_column(String(10))
    items: Mapped[list] = mapped_column(JSON)
    nutrients: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Favorite(Base):
    __tablename__ = 'favorites'
    __table_args__ = (UniqueConstraint('user_id', 'dish_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    dish_id: Mapped[str] = mapped_column(ForeignKey('dishes.id'))

class Recommendation(Base):
    __tablename__ = 'recommendations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    date: Mapped[str] = mapped_column(String(10))
    meal: Mapped[str] = mapped_column(String(10))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Feedback(Base):
    __tablename__ = 'feedback'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    recommendation_id: Mapped[str | None] = mapped_column(ForeignKey('recommendations.id'), nullable=True)
    canteen_id: Mapped[str] = mapped_column(ForeignKey('canteens.id'))
    rating: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    reply: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Device(Base):
    __tablename__ = 'devices'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    canteen_id: Mapped[str] = mapped_column(ForeignKey('canteens.id'))
    name: Mapped[str] = mapped_column(String(80))
    source_type: Mapped[str] = mapped_column(String(10), default='demo')
    source: Mapped[str] = mapped_column(Text, default='')
    roi: Mapped[list] = mapped_column(JSON, default=lambda: [0, 0, 1, 1])
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default='stopped')
    heartbeat: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str] = mapped_column(Text, default='')

class DetectionJob(Base):
    __tablename__ = 'detection_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    canteen_id: Mapped[str] = mapped_column(ForeignKey('canteens.id'))
    device_id: Mapped[str | None] = mapped_column(ForeignKey('devices.id'), nullable=True)
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default='queued')
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    roi: Mapped[list | None] = mapped_column(JSON, nullable=True)
    result_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class WasteEvent(Base):
    __tablename__ = 'waste_events'
    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=uid)
    canteen_id: Mapped[str] = mapped_column(ForeignKey('canteens.id'))
    device_id: Mapped[str | None] = mapped_column(ForeignKey('devices.id'), nullable=True)
    mode: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(30))
    model_version: Mapped[str] = mapped_column(String(200))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[str] = mapped_column(String(20), default='待核验')
    status: Mapped[str] = mapped_column(String(20), default='pending')
    detections: Mapped[list] = mapped_column(JSON, default=list)
    reminder: Mapped[str] = mapped_column(Text, default='按需取餐，少量多次。')
    snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class SystemSetting(Base):
    __tablename__ = 'system_settings'
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)

class LegacyWeightRecord(Base):
    __tablename__ = 'legacy_weight_records'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
