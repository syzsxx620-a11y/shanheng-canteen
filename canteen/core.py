"""可审计的工具型智能体：质量检查 → 营养计算 → 建议。"""
from dataclasses import dataclass, asdict
import math

# 示例食物成分，每100g；实际部署须使用学校审核过的食谱成分库。
FOODS = {
    'rice': ('米饭', '主食', 116, 2.6, 0.3, 25.9),
    'noodles': ('面条', '主食', 110, 3.5, 0.5, 23.0),
    'chicken': ('鸡肉', '蛋白类', 167, 19.3, 9.4, 0.0),
    'beef': ('牛肉', '蛋白类', 125, 19.9, 4.2, 2.0),
    'egg': ('鸡蛋', '蛋白类', 144, 13.3, 8.8, 2.8),
    'tofu': ('豆腐', '蛋白类', 81, 8.1, 3.7, 4.2),
    'vegetables': ('蔬菜', '蔬菜', 30, 2.0, 0.4, 4.5),
    'potato': ('土豆', '主食', 77, 2.0, 0.2, 17.0),
    'fruit': ('水果', '水果', 52, 0.3, 0.2, 13.5),
}

@dataclass
class Portion:
    food: str
    served_g: float
    leftover_g: float

def analyze(portions):
    if not portions:
        raise ValueError('至少添加一种食物。')
    nutrients = dict(kcal=0.0, protein=0.0, fat=0.0, carbs=0.0)
    groups, served, waste = set(), 0.0, 0.0
    for p in portions:
        if p.food not in FOODS:
            raise ValueError(f'未知食物类别：{p.food}')
        if not all(math.isfinite(v) for v in (p.served_g, p.leftover_g)):
            raise ValueError('重量必须是有限数值。')
        if p.served_g < 0 or not 0 <= p.leftover_g <= p.served_g:
            raise ValueError('剩余重量必须在0与供餐重量之间。')
        food = FOODS[p.food]
        consumed = p.served_g - p.leftover_g
        served += p.served_g
        waste += p.leftover_g
        if consumed > 0:
            groups.add(food[1])
        for key, value in zip(nutrients, food[2:]):
            nutrients[key] += consumed * value / 100
    if served == 0:
        raise ValueError('供餐总重量必须大于0。')
    rate = waste / served
    advice = []
    if rate >= .2:
        advice.append('本餐剩余比例较高，下次可先取小份，不足时再添。')
    else:
        advice.append('继续按需取餐，记录口味与份量反馈。')
    for group, message in [('蔬菜', '本次记录未包含吃下的蔬菜，可考虑搭配一份蔬菜。'), ('蛋白类', '本次记录未包含吃下的蛋白类食物，可考虑鸡蛋、豆腐或肉类。'), ('主食', '本次记录未包含吃下的主食，可按个人需要搭配。')]:
        if group not in groups:
            advice.append(message)
    return {'served_g': served, 'waste_g': waste, 'consumed_g': served-waste,
            'waste_rate': rate, 'nutrients': nutrients, 'advice': advice,
            'portions': [asdict(p) for p in portions],
            'agent_trace': ['质量检查工具：食物类别与重量范围校验通过', '营养计算工具：以供餐量减剩余量计算摄入', '建议工具：依据食物组覆盖及浪费比例生成建议']}
