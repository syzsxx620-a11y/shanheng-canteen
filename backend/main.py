import csv
import io
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, HTTPException, Response, Request, Cookie, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import *
from .schemas import *
from .security import current_user, manager, system_admin, check_canteen, hasher, verify_password, token_pair, digest, revoke_all, audit
from .recommendations import today, dish_dict, menu_dishes, recommend, public_recommendation, model_config
from .nutrition import energy_summary, NUTRIENTS
from .vision import grade, thresholds, crop_roi

app = FastAPI(title='膳衡 · 智慧食堂 API', version='2.0.0', description='匿名餐盘回收监测与学生主动记录相互独立。')
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins, allow_credentials=True, allow_methods=['GET', 'POST', 'PUT', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])
PREFIX = '/api/v1'
attempts = defaultdict(deque)

def limit_auth(request):
    key = request.client.host if request.client else 'local'
    queue = attempts[key]
    now_ts = time.monotonic()
    while queue and queue[0] < now_ts-60:
        queue.popleft()
    if len(queue) >= 20:
        raise HTTPException(429, '请求过于频繁，请稍后重试')
    queue.append(now_ts)

def obj_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

def user_dict(user):
    return {k: getattr(user, k) for k in ('id', 'username', 'role', 'active', 'canteen_id', 'created_at')}

def must_get(db, model, id):
    item = db.get(model, id)
    if item is None:
        raise HTTPException(404, '记录不存在')
    return item

def scoped(query, model, user):
    if user.role != 'system_admin':
        query = query.where(model.canteen_id == user.canteen_id)
    return query

def set_tokens(response, tokens):
    response.set_cookie('refresh_token', tokens.pop('refresh_token'), httponly=True, samesite='strict', secure=settings().cookie_secure, max_age=7*86400, path=PREFIX+'/auth')
    return tokens

def origin_check(request):
    origin = request.headers.get('origin')
    if origin and origin not in settings().cors_origins:
        raise HTTPException(403, '不允许的请求来源')

@app.get(PREFIX+'/health')
def health():
    return {'status': 'ok', 'version': '2.0.0'}

@app.post(PREFIX+'/auth/register', status_code=201)
def register(data: Credentials, request: Request, db: Session = Depends(get_db)):
    limit_auth(request)
    user = User(username=data.username.lower(), password_hash=hasher.hash(data.password), role='student')
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '账号已存在')
    db.add(Profile(user_id=user.id, data={}))
    db.add(Notification(user_id=user.id, title='欢迎加入膳衡', content='完善饮食偏好后，即可获取当天菜品搭配。身体信息自愿填写。'))
    audit(db, user, 'register', user.id)
    db.commit()
    return user_dict(user)

@app.post(PREFIX+'/auth/login')
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    limit_auth(request)
    user = db.scalar(select(User).where(User.username == data.username.lower()))
    if not user or not verify_password(user.password_hash, data.password):
        raise HTTPException(401, '账号或密码错误')
    if not user.active:
        raise HTTPException(403, '账号已禁用')
    tokens = token_pair(db, user)
    audit(db, user, 'login', user.id)
    db.commit()
    return {**set_tokens(response, tokens), 'user': user_dict(user)}

@app.post(PREFIX+'/auth/refresh')
def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    origin_check(request)
    limit_auth(request)
    session = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == digest(refresh_token or '')))
    if not session or session.revoked or datetime.fromisoformat(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(401, '会话已失效')
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, '账号不可用')
    tokens = token_pair(db, user, session)
    db.commit()
    return {**set_tokens(response, tokens), 'user': user_dict(user)}

@app.post(PREFIX+'/auth/logout')
def logout(request: Request, response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    origin_check(request)
    session = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == digest(refresh_token or '')))
    if session:
        session.revoked = True
        db.commit()
    response.delete_cookie('refresh_token', path=PREFIX+'/auth')
    return {'ok': True}

@app.get(PREFIX+'/auth/me')
def me(user: User = Depends(current_user)):
    return user_dict(user)

@app.post(PREFIX+'/auth/password')
def password_change(data: PasswordChange, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(user.password_hash, data.old_password):
        raise HTTPException(400, '原密码错误')
    user.password_hash = hasher.hash(data.new_password)
    revoke_all(db, user.id)
    audit(db, user, 'change_password', user.id)
    db.commit()
    return {'ok': True, 'message': '密码已修改，请重新登录'}

@app.get(PREFIX+'/me/profile')
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(Profile, user.id)
    data = ProfileInput(**(row.data if row else {})).model_dump()
    return {'profile': data, 'energy': energy_summary(data)}

@app.put(PREFIX+'/me/profile')
def put_profile(data: ProfileInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(Profile, user.id)
    if not row:
        row = Profile(user_id=user.id)
        db.add(row)
    row.data = data.model_dump()
    db.commit()
    return {'profile': row.data, 'energy': energy_summary(row.data)}

@app.get(PREFIX+'/canteens')
def canteens(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{'id': c.id, 'name': c.name, 'windows': [obj_dict(w) for w in db.scalars(select(Window).where(Window.canteen_id == c.id))]} for c in db.scalars(select(Canteen))]

@app.get(PREFIX+'/dishes')
def dishes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Dish, Window, Canteen).join(Window, Dish.window_id == Window.id).join(Canteen, Window.canteen_id == Canteen.id)
    if user.role == 'canteen_admin':
        query = query.where(Canteen.id == user.canteen_id)
    if user.role == 'student':
        query = query.where(Dish.active.is_(True))
    return [dish_dict(d, w, c) for d,w,c in db.execute(query)]

@app.post(PREFIX+'/dishes', status_code=201)
def create_dish(data: DishInput, user: User = Depends(manager), db: Session = Depends(get_db)):
    window = must_get(db, Window, data.window_id)
    check_canteen(user, window.canteen_id)
    dish = Dish(**data.model_dump())
    db.add(dish)
    db.flush()
    audit(db, user, 'create_dish', dish.id)
    db.commit()
    return obj_dict(dish)

@app.put(PREFIX+'/dishes/{id}')
def update_dish(id: str, data: DishInput, user: User = Depends(manager), db: Session = Depends(get_db)):
    dish = must_get(db, Dish, id)
    check_canteen(user, must_get(db, Window, dish.window_id).canteen_id)
    check_canteen(user, must_get(db, Window, data.window_id).canteen_id)
    for k,v in data.model_dump().items():
        setattr(dish,k,v)
    audit(db, user, 'update_dish', id)
    db.commit()
    return obj_dict(dish)

@app.get(PREFIX+'/menus')
def menus(date: date | None = None, meal: Literal['早餐','午餐','晚餐'] = '午餐', mode: Literal['demo','real'] = 'demo', canteen_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return menu_dishes(db, str(date) if date else today(), meal, mode, canteen_id)

@app.get(PREFIX+'/menus/entries')
def menu_entries(date: date | None = None, user: User = Depends(manager), db: Session = Depends(get_db)):
    query = select(MenuEntry, Dish, Window).join(Dish, MenuEntry.dish_id == Dish.id).join(Window, Dish.window_id == Window.id).where(MenuEntry.date == (str(date) if date else today()))
    if user.role != 'system_admin':
        query = query.where(Window.canteen_id == user.canteen_id)
    return [{**obj_dict(m), 'dish_name': d.name} for m,d,w in db.execute(query)]

@app.post(PREFIX+'/menus')
def upsert_menu(data: MenuInput, user: User = Depends(manager), db: Session = Depends(get_db)):
    dish = must_get(db, Dish, data.dish_id)
    check_canteen(user, must_get(db, Window, dish.window_id).canteen_id)
    row = db.scalar(select(MenuEntry).where(MenuEntry.date == str(data.date), MenuEntry.meal == data.meal, MenuEntry.dish_id == data.dish_id))
    if not row:
        row = MenuEntry(date=str(data.date), meal=data.meal, dish_id=data.dish_id)
        db.add(row)
    row.available = data.available
    audit(db, user, 'publish_menu', data.dish_id, {'date': str(data.date), 'available': data.available})
    db.commit()
    return obj_dict(row)

@app.get(PREFIX+'/me/meal-records')
def meals(mode: Literal['demo','real'] = 'demo', user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .recommendations import meal_mode
    return [{**obj_dict(r),'mode':meal_mode(r)} for r in db.scalars(select(MealRecord).where(MealRecord.user_id == user.id).order_by(MealRecord.created_at.desc())) if meal_mode(r)==mode]

@app.post(PREFIX+'/me/meal-records', status_code=201)
def add_meal(data: MealInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    items, totals = [], {k: 0.0 for k in NUTRIENTS}
    modes = set()
    for item in data.items:
        dish = must_get(db, Dish, item.dish_id)
        if not dish.active:
            raise HTTPException(400, '菜品已下架')
        modes.add(dish.is_demo)
        if len(modes)>1:
            raise HTTPException(400,'一餐不能混合演示与真实菜品')
        amount = item.servings*(1-item.leftover_fraction)
        for k in totals:
            totals[k] += getattr(dish,k)*amount
        items.append({**item.model_dump(), 'dish_name': dish.name, 'source': dish.nutrition_source, 'is_demo':dish.is_demo})
    row = MealRecord(user_id=user.id, date=str(data.date), meal=data.meal, items=items, nutrients={k:round(v,1) for k,v in totals.items()})
    db.add(row)
    db.commit()
    return obj_dict(row)

@app.delete(PREFIX+'/me/meal-records/{id}')
def delete_meal(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = must_get(db, MealRecord, id)
    if row.user_id != user.id:
        raise HTTPException(404, '记录不存在')
    db.delete(row)
    db.commit()
    return {'ok': True}

@app.get(PREFIX+'/me/favorites')
def favorites(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [r.dish_id for r in db.scalars(select(Favorite).where(Favorite.user_id == user.id))]

@app.post(PREFIX+'/me/favorites/{dish_id}')
def favorite(dish_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    must_get(db, Dish, dish_id)
    row = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.dish_id == dish_id))
    if row:
        db.delete(row)
        active = False
    else:
        db.add(Favorite(user_id=user.id, dish_id=dish_id))
        active = True
    db.commit()
    return {'favorite': active}

@app.get(PREFIX+'/me/notifications')
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [obj_dict(r) for r in db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()))]

@app.post(PREFIX+'/me/notifications/{id}/read')
def notification_read(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = must_get(db, Notification, id)
    if row.user_id != user.id:
        raise HTTPException(404, '消息不存在')
    row.read = True
    db.commit()
    return {'ok': True}

@app.post(PREFIX+'/recommendations')
def recommendations(data: RecommendInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return public_recommendation(recommend(db, user, data))

@app.post(PREFIX+'/assistant')
def assistant(data: AssistantInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return public_recommendation(recommend(db, user, data, data.message))

@app.post(PREFIX+'/feedback')
def create_feedback(data: FeedbackInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    must_get(db, Canteen, data.canteen_id)
    if data.recommendation_id:
        rec = must_get(db, Recommendation, data.recommendation_id)
        if rec.user_id != user.id:
            raise HTTPException(404, '推荐不存在')
    row = Feedback(user_id=user.id, **data.model_dump())
    db.add(row)
    db.commit()
    return obj_dict(row)

@app.get(PREFIX+'/feedback')
def feedback(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Feedback).order_by(Feedback.created_at.desc())
    if user.role == 'student':
        query = query.where(Feedback.user_id == user.id)
    elif user.role != 'system_admin':
        query = query.where(Feedback.canteen_id == user.canteen_id)
    return [obj_dict(r) for r in db.scalars(query)]

@app.post(PREFIX+'/feedback/{id}/reply')
def reply_feedback(id: str, data: NameInput, user: User = Depends(manager), db: Session = Depends(get_db)):
    row = must_get(db, Feedback, id)
    check_canteen(user, row.canteen_id)
    row.reply = data.name
    db.add(Notification(user_id=row.user_id, title='食堂回复了你的反馈', content=data.name))
    audit(db, user, 'reply_feedback', id)
    db.commit()
    return {'ok': True}

def device_dict(device, user):
    result = obj_dict(device)
    if user.role != 'system_admin':
        result['source'] = '已配置（仅系统管理员可见）'
    return result

@app.get(PREFIX+'/devices')
def devices(user: User = Depends(manager), db: Session = Depends(get_db)):
    return [device_dict(r, user) for r in db.scalars(scoped(select(Device), Device, user))]

@app.post(PREFIX+'/devices', status_code=201)
def add_device(data: DeviceInput, user: User = Depends(system_admin), db: Session = Depends(get_db)):
    must_get(db, Canteen, data.canteen_id)
    row = Device(**data.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, 'add_device', row.id)
    db.commit()
    return device_dict(row, user)

@app.put(PREFIX+'/devices/{id}')
def edit_device(id: str, data: DeviceInput, user: User = Depends(system_admin), db: Session = Depends(get_db)):
    row = must_get(db, Device, id)
    if row.enabled:
        raise HTTPException(409, '请先停止设备再修改配置')
    must_get(db, Canteen, data.canteen_id)
    for k,v in data.model_dump().items():
        setattr(row,k,v)
    audit(db, user, 'edit_device', id)
    db.commit()
    return device_dict(row, user)

@app.post(PREFIX+'/devices/{id}/toggle')
def toggle_device(id: str, user: User = Depends(manager), db: Session = Depends(get_db)):
    row = must_get(db, Device, id)
    check_canteen(user, row.canteen_id)
    row.enabled = not row.enabled
    row.status = 'starting' if row.enabled else 'stopped'
    row.error = ''
    audit(db, user, 'toggle_device', id, {'enabled': row.enabled})
    db.commit()
    return device_dict(row,user)

@app.post(PREFIX+'/detection-jobs', status_code=202)
async def add_job(canteen_id: str = Form(...), mode: Literal['demo','real'] = Form('demo'), roi: str = Form(''), image: UploadFile | None = File(default=None), user: User = Depends(manager), db: Session = Depends(get_db)):
    check_canteen(user, canteen_id)
    must_get(db, Canteen, canteen_id)
    job = DetectionJob(canteen_id=canteen_id, mode=mode)
    db.add(job)
    db.flush()
    if mode == 'real':
        if not image:
            raise HTTPException(400, '真实检测需要上传图片并选择餐盘区域')
        content = await image.read(10*1024*1024+1)
        if len(content) > 10*1024*1024:
            raise HTTPException(413, '图片不能超过10MB')
        try:
            bounds = json.loads(roi)
            with Image.open(io.BytesIO(content)) as im:
                if im.width*im.height > 20_000_000:
                    raise ValueError('图片像素过大')
                cropped = crop_roi(im.convert('RGB'), bounds)
            dest = Path(settings().data_dir)/'snapshots'/f'{job.id}.jpg'
            dest.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(dest, quality=85)
            job.image_path = str(dest)
            job.roi = [0,0,1,1]
        except (ValueError, TypeError, UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(400, '图片或餐盘区域无效，请重新选择')
    audit(db, user, 'enqueue_detection', job.id, {'mode': mode})
    db.commit()
    return obj_dict(job)

@app.get(PREFIX+'/detection-jobs/{id}')
def get_job(id: str, user: User = Depends(manager), db: Session = Depends(get_db)):
    job = must_get(db, DetectionJob, id)
    check_canteen(user, job.canteen_id)
    return {k:v for k,v in obj_dict(job).items() if k != 'image_path'}

def event_list(db, user, mode, canteen_id=None):
    query = scoped(select(WasteEvent).where(WasteEvent.mode == mode), WasteEvent, user).order_by(WasteEvent.created_at.desc())
    if canteen_id:
        query = query.where(WasteEvent.canteen_id == canteen_id)
    return list(db.scalars(query))

def event_dict(row):
    data = obj_dict(row)
    data['snapshot'] = PREFIX+f'/waste-events/{row.id}/snapshot' if row.snapshot else None
    return data

@app.get(PREFIX+'/waste-events')
def waste_events(mode: Literal['demo','real'] = 'demo', canteen_id: str | None = None, user: User = Depends(manager), db: Session = Depends(get_db)):
    return [event_dict(r) for r in event_list(db,user,mode,canteen_id)[:500]]

@app.get(PREFIX+'/waste-events/{id}/snapshot')
def snapshot(id: str, user: User = Depends(manager), db: Session = Depends(get_db)):
    row = must_get(db, WasteEvent, id)
    check_canteen(user, row.canteen_id)
    if not row.snapshot or not Path(row.snapshot).is_file():
        raise HTTPException(404, '截图已过期或不存在')
    return FileResponse(row.snapshot, media_type='image/jpeg', headers={'Cache-Control':'no-store'})

@app.post(PREFIX+'/waste-events/{id}/review')
def review(id: str, data: ReviewInput, user: User = Depends(manager), db: Session = Depends(get_db)):
    row = must_get(db, WasteEvent, id)
    check_canteen(user, row.canteen_id)
    if data.status == 'verified' and data.area_ratio is None:
        raise HTTPException(400, '确认记录时必须填写人工估计面积占比')
    history = [*row.review_history, {'at': now(), 'reviewer': user.id, 'before': {'area_ratio':row.area_ratio,'status':row.status}, **data.model_dump()}]
    row.review_history = history
    row.area_ratio = data.area_ratio
    row.status = data.status
    row.grade = grade(data.area_ratio, thresholds(db))
    audit(db,user,'review_event',id,data.model_dump())
    db.commit()
    return event_dict(row)

@app.get(PREFIX+'/analytics')
def analytics(mode: Literal['demo','real'] = 'demo', canteen_id: str | None = None, start: date | None = None, end: date | None = None, user: User = Depends(manager), db: Session = Depends(get_db)):
    if start and end and start > end:
        raise HTTPException(400,'开始日期不能晚于结束日期')
    local_day = lambda r: datetime.fromisoformat(r.created_at).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    rows = [r for r in event_list(db,user,mode,canteen_id) if (not start or local_day(r) >= str(start)) and (not end or local_day(r) <= str(end))]
    valid = [r for r in rows if r.status == 'verified' and r.area_ratio is not None]
    days, grades = {}, defaultdict(int)
    for r in valid:
        day = local_day(r)
        days.setdefault(day, []).append(r.area_ratio)
        grades[r.grade] += 1
    return {'mode':mode,'total':len(rows),'verified':len(valid),'pending':sum(r.status == 'pending' for r in rows), 'average_area_ratio':sum(r.area_ratio for r in valid)/len(valid) if valid else None,
            'grades': dict(grades), 'trend': [{'date':d,'count':len(v),'average_area_ratio':sum(v)/len(v)} for d,v in sorted(days.items())]}

@app.get(PREFIX+'/analytics/export')
def analytics_export(mode: Literal['demo','real'] = 'demo', canteen_id: str | None = None, start: date | None = None, end: date | None = None, user: User = Depends(manager), db: Session = Depends(get_db)):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['事件ID','时间UTC','模式','来源','面积占比','等级','核验状态'])
    for r in event_list(db,user,mode,canteen_id):
        day = datetime.fromisoformat(r.created_at).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
        if (not start or day >= str(start)) and (not end or day <= str(end)):
            writer.writerow([r.id,r.created_at,r.mode,r.source,r.area_ratio,r.grade,r.status])
    return Response(content=output.getvalue().encode('utf-8-sig'), media_type='text/csv', headers={'Content-Disposition':'attachment; filename="waste-events.csv"'})

@app.get(PREFIX+'/display/{canteen_id}')
def display(canteen_id: str, mode: Literal['demo','real'] = 'demo', db: Session = Depends(get_db)):
    must_get(db,Canteen,canteen_id)
    # 公共大屏只提供今天的聚合与匿名摘要，不返回图片、设备地址、用户或核验人员。
    rows = list(db.scalars(select(WasteEvent).where(WasteEvent.canteen_id == canteen_id,WasteEvent.mode == mode).order_by(WasteEvent.created_at.desc()).limit(1000)))
    local_today = [r for r in rows if datetime.fromisoformat(r.created_at).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() == today()]
    latest = rows[0] if rows else None
    return {'mode':mode,'today_count':len(local_today),'latest': {k:getattr(latest,k) for k in ('grade','reminder','created_at','area_ratio','status')} if latest else None}

@app.get(PREFIX+'/admin/users')
def users(user: User = Depends(system_admin), db: Session = Depends(get_db)):
    return [user_dict(r) for r in db.scalars(select(User))]

@app.put(PREFIX+'/admin/users/{id}')
def user_update(id: str, data: UserUpdate, user: User = Depends(system_admin), db: Session = Depends(get_db)):
    row = must_get(db,User,id)
    if row.id == user.id and (not data.active or data.role != 'system_admin'):
        raise HTTPException(400,'不能禁用或降级当前管理员')
    if data.role == 'canteen_admin':
        if not data.canteen_id:
            raise HTTPException(400,'食堂管理员必须分配食堂')
        must_get(db,Canteen,data.canteen_id)
    row.role,row.active,row.canteen_id = data.role,data.active,data.canteen_id if data.role == 'canteen_admin' else None
    revoke_all(db,id)
    audit(db,user,'update_user',id,data.model_dump())
    db.commit()
    return user_dict(row)

@app.post(PREFIX+'/admin/users/{id}/reset-password')
def reset_password(id: str, data: ResetPassword, user: User = Depends(system_admin), db: Session = Depends(get_db)):
    row = must_get(db,User,id)
    row.password_hash = hasher.hash(data.password)
    revoke_all(db,id)
    audit(db,user,'reset_password',id)
    db.commit()
    return {'ok':True}

@app.post(PREFIX+'/admin/canteens')
def add_canteen(data: NameInput, user: User = Depends(system_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Canteen).where(Canteen.name == data.name)):
        raise HTTPException(409,'食堂名称已存在')
    row = Canteen(name=data.name)
    db.add(row)
    db.flush()
    audit(db,user,'add_canteen',row.id)
    db.commit()
    return obj_dict(row)

@app.post(PREFIX+'/admin/windows')
def add_window(data: NameInput, user: User = Depends(system_admin), db: Session = Depends(get_db)):
    must_get(db,Canteen,data.canteen_id)
    row = Window(name=data.name,canteen_id=data.canteen_id)
    db.add(row)
    db.flush()
    audit(db,user,'add_window',row.id)
    db.commit()
    return obj_dict(row)

@app.get(PREFIX+'/admin/model-config')
def get_model_config(user: User = Depends(system_admin), db: Session = Depends(get_db)):
    config = model_config(db)
    config['api_key_configured'] = bool(config.pop('llm_api_key',''))
    config['thresholds'] = thresholds(db)
    return config

@app.put(PREFIX+'/admin/model-config')
def put_model_config(data: ModelConfigInput, user: User = Depends(system_admin), db: Session = Depends(get_db)):
    value = data.model_dump()
    if value['llm_api_key'] is None:
        value['llm_api_key'] = model_config(db)['llm_api_key']
    row = db.get(SystemSetting,'models')
    if not row:
        row = SystemSetting(key='models',value=value)
        db.add(row)
    else:
        row.value = value
    audit(db,user,'update_model_config','models',{'model':data.llm_model,'key_changed':data.llm_api_key is not None})
    db.commit()
    return {'ok':True}

@app.get(PREFIX+'/admin/audit-logs')
def audit_logs(user: User = Depends(system_admin), db: Session = Depends(get_db)):
    return [obj_dict(r) for r in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(300))]

@app.get(PREFIX+'/admin/legacy-records')
def legacy_records(user: User = Depends(system_admin), db: Session = Depends(get_db)):
    return [obj_dict(r) for r in db.scalars(select(LegacyWeightRecord))]
