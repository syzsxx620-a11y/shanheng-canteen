from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator, field_validator

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r'^[a-zA-Z0-9_\-]+$')
    password: str = Field(min_length=8, max_length=128)

class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)

class ProfileInput(BaseModel):
    height_cm: float | None = Field(default=None, ge=100, le=230)
    weight_kg: float | None = Field(default=None, ge=25, le=300)
    age: int | None = Field(default=None, ge=10, le=100)
    sex: Literal['male', 'female'] | None = None
    activity: Literal['sedentary', 'light', 'moderate', 'active'] = 'light'
    goal: Literal['balanced', 'maintain', 'fitness'] = 'balanced'
    allergens: list[str] = Field(default_factory=list, max_length=20)
    dislikes: list[str] = Field(default_factory=list, max_length=30)
    preferences: list[str] = Field(default_factory=list, max_length=20)
    budget: float = Field(default=20, ge=1, le=200)
    special_condition: bool = False
    llm_consent: bool = False

    @field_validator('allergens','dislikes','preferences')
    @classmethod
    def clean_preferences(cls,value):
        if any(len(s)>50 for s in value):
            raise ValueError('单项食材或偏好不能超过50字')
        return list(dict.fromkeys(s.strip() for s in value if s.strip()))

class DishInput(BaseModel):
    window_id: str
    name: str = Field(min_length=1, max_length=80)
    category: Literal['主食', '蛋白类', '蔬菜', '水果']
    price: float = Field(ge=0, le=500)
    portion_g: float = Field(gt=0, le=5000)
    kcal: float = Field(ge=0, le=10000)
    protein: float = Field(ge=0, le=1000)
    fat: float = Field(ge=0, le=1000)
    carbs: float = Field(ge=0, le=1000)
    ingredients: list[str] = Field(default_factory=list)
    allergens: list[str] | None = None
    nutrition_source: str = Field(min_length=1, max_length=200)
    image_url: str = Field(default='', max_length=300, pattern=r'^(|/assets/[a-zA-Z0-9_\-]+\.svg)$')
    active: bool = True
    is_demo: bool = False

class MenuInput(BaseModel):
    date: date
    meal: Literal['早餐', '午餐', '晚餐'] = '午餐'
    dish_id: str
    available: bool = True

class MealItem(BaseModel):
    dish_id: str
    servings: float = Field(gt=0, le=10)
    leftover_fraction: float = Field(default=0, ge=0, le=1)

class MealInput(BaseModel):
    date: date
    meal: Literal['早餐', '午餐', '晚餐']
    items: list[MealItem] = Field(min_length=1, max_length=20)

class RecommendInput(BaseModel):
    meal: Literal['早餐', '午餐', '晚餐'] = '午餐'
    canteen_id: str | None = None
    refresh: bool = False
    mode: Literal['demo', 'real'] = 'demo'

class AssistantInput(RecommendInput):
    message: str = Field(min_length=1, max_length=1000)

class FeedbackInput(BaseModel):
    canteen_id: str
    recommendation_id: str | None = None
    rating: int = Field(ge=1, le=5)
    content: str = Field(min_length=1, max_length=1000)

class DeviceInput(BaseModel):
    canteen_id: str
    name: str = Field(min_length=1, max_length=80)
    source_type: Literal['demo', 'usb', 'rtsp', 'video'] = 'demo'
    source: str = Field(default='', max_length=1000)
    roi: list[float] = Field(default_factory=lambda: [0, 0, 1, 1], min_length=4, max_length=4)

    @model_validator(mode='after')
    def check_roi(self):
        x, y, w, h = self.roi
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1-x and 0 < h <= 1-y):
            raise ValueError('ROI必须为归一化的[x,y,width,height]且位于图像内')
        if self.source_type == 'rtsp' and not self.source.startswith('rtsp://'):
            raise ValueError('请输入rtsp://地址')
        if self.source_type == 'usb' and not self.source.isdigit():
            raise ValueError('USB摄像头填写数字索引，例如0')
        return self

class ReviewInput(BaseModel):
    area_ratio: float | None = Field(default=None, ge=0, le=1)
    status: Literal['verified', 'rejected']
    note: str = Field(min_length=1, max_length=500)

class UserUpdate(BaseModel):
    role: Literal['student', 'canteen_admin', 'system_admin']
    active: bool
    canteen_id: str | None = None

class ResetPassword(BaseModel):
    password: str = Field(min_length=8, max_length=128)

class NameInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    canteen_id: str | None = None

class ModelConfigInput(BaseModel):
    llm_base_url: str = Field(default='', max_length=500)
    llm_model: str = Field(default='', max_length=100)
    llm_api_key: str | None = Field(default=None, max_length=500)
    llm_timeout: float = Field(default=15, ge=1, le=60)
    yolo_weights: str = Field(default='', max_length=500)
    thresholds: list[float] = Field(default_factory=lambda: [.01, .1, .3], min_length=3, max_length=3)

    @model_validator(mode='after')
    def thresholds_valid(self):
        a, b, c = self.thresholds
        if not 0 < a < b < c < 1:
            raise ValueError('分级阈值必须在0与1之间严格递增')
        if self.llm_base_url and not self.llm_base_url.startswith(('http://', 'https://')):
            raise ValueError('模型地址必须是HTTP(S)地址')
        return self
