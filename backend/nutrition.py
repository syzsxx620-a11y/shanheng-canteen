"""确定性计算；Mifflin–St Jeor: 10W+6.25H-5A+s，s男5/女-161。"""
from itertools import product

ACTIVITY = {'sedentary': 1.2, 'light': 1.375, 'moderate': 1.55, 'active': 1.725}
NUTRIENTS = ('kcal', 'protein', 'fat', 'carbs')

def energy_summary(profile):
    h, w, age, sex = (profile.get(k) for k in ('height_cm', 'weight_kg', 'age', 'sex'))
    result = {'bmi': round(w/(h/100)**2, 1) if h and w and age and age >= 18 else None, 'daily_kcal': None,
              'basis': 'Mifflin–St Jeor：10×体重kg + 6.25×身高cm − 5×年龄 + 常数；活动系数修正。仅为成年人维持能量估算。',
              'note': '资料不完整或属于特殊人群时，仅提供一般搭配。'}
    if all((h, w, age, sex)) and age >= 18 and not profile.get('special_condition'):
        bmr = 10*w + 6.25*h - 5*age + (5 if sex == 'male' else -161)
        result.update(daily_kcal=round(bmr*ACTIVITY.get(profile.get('activity'), 1.375)), note='估算值不等同于实际消耗；不根据BMI诊断营养状况。')
    return result

def allowed(dish, profile):
    allergens = {x.strip().casefold() for x in profile.get('allergens', []) if x.strip()}
    if allergens and dish['allergens'] is None:
        return False
    if allergens.intersection(x.strip().casefold() for x in (dish['allergens'] or [])):
        return False
    text = ' '.join([dish['name'], *dish['ingredients']]).casefold()
    # 过敏原也检查食材与菜名，防止维护遗漏。
    if any(x in text for x in allergens):
        return False
    return not any(x.strip().casefold() in text for x in profile.get('dislikes', []) if x.strip())

def choose_combos(dishes, profile, meal='午餐'):
    candidates = [d for d in dishes if allowed(d, profile)]
    buckets = [[d for d in candidates if d['category'] == c] for c in ('主食', '蛋白类', '蔬菜')]
    summary = energy_summary(profile)
    target = (summary['daily_kcal'] or 2000) * (.25 if meal == '早餐' else .375)
    combos = []
    for parts in product(*buckets):
        price = round(sum(d['price'] for d in parts), 2)
        if price > profile.get('budget', 20):
            continue
        totals = {k: round(sum(d[k] for d in parts), 1) for k in NUTRIENTS}
        pref = sum(any(p in d['name'] or p in d['ingredients'] for p in profile.get('preferences', [])) for d in parts)
        protein_preference = min(totals['protein'],40)*.004 if profile.get('goal') == 'fitness' else 0
        score = abs(totals['kcal']-target)/max(target, 1) + price*.002 - pref*.1 - protein_preference
        combos.append({'dishes': list(parts), 'price': price, 'nutrients': totals, '_score': score})
    combos.sort(key=lambda c: (c['_score'], tuple(d['id'] for d in c['dishes'])))
    return combos[:30], summary
