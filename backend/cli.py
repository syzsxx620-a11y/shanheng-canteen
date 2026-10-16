import argparse
import json
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

def initialize_env():
    path = Path(__file__).resolve().parents[1]/'.env'
    if not path.exists():
        path.write_text('JWT_SECRET='+secrets.token_urlsafe(48)+'\n',encoding='utf-8')

def seed():
    from .db import SessionLocal
    from .models import User, Canteen, Window, Dish, MenuEntry, Device, Profile, WasteEvent, Notification
    from .security import hasher
    from .recommendations import today
    from .vision import grade
    from sqlalchemy import select
    with SessionLocal() as db:
        canteens = list(db.scalars(select(Canteen)))
        if not canteens:
            canteens = [Canteen(name='清禾食堂'),Canteen(name='知味食堂')]
            db.add_all(canteens)
            db.flush()
        windows = list(db.scalars(select(Window)))
        if not windows:
            for c in canteens:
                db.add(Window(canteen_id=c.id,name='营养自选窗口'))
            db.flush()
            windows = list(db.scalars(select(Window)))
        for name,role,cid in [('student','student',None),('manager','canteen_admin',canteens[0].id),('admin','system_admin',None)]:
            if not db.scalar(select(User).where(User.username == name)):
                u = User(username=name,role=role,canteen_id=cid,password_hash=hasher.hash('Demo@12345'))
                db.add(u)
                db.flush()
                db.add(Profile(user_id=u.id,data={'height_cm':170,'weight_kg':62,'age':21,'sex':'female','activity':'light','budget':20,'allergens':[],'dislikes':[],'preferences':['西兰花'],'llm_consent':False}))
                db.add(Notification(user_id=u.id,title='欢迎来到膳衡',content='这是演示账号，菜品营养与监测数据均为示例。试试查看今日推荐吧。'))
        if not db.scalar(select(Dish.id)):
            examples = [
                ('杂粮米饭','主食',2,180,210,5,1,45,['大米','燕麦'],['谷蛋白'],'rice'),
                ('清蒸米饭','主食',1.5,180,209,4.7,.5,46.6,['大米'],[],'rice'),
                ('香煎鸡胸肉','蛋白类',8,120,220,28,10,4,['鸡肉','大豆油'],['大豆'],'chicken'),
                ('番茄炒蛋','蛋白类',5,160,180,11,12,8,['番茄','鸡蛋'],['鸡蛋'],'egg'),
                ('家常豆腐','蛋白类',4,150,190,13,10,12,['豆腐','青椒'],['大豆'],'tofu'),
                ('清炒西兰花','蔬菜',4,150,90,5,4,9,['西兰花'],[],'vegetables'),
                ('蒜蓉时蔬','蔬菜',3,150,75,3,3,9,['青菜','蒜'],[],'vegetables'),
                ('当季鲜果','水果',3,150,78,.5,.3,20,['苹果'],[],'fruit')]
            for window in windows:
                for name,category,price,portion,kcal,protein,fat,carbs,ingredients,allergens,image in examples:
                    db.add(Dish(window_id=window.id,name=name,category=category,price=price,portion_g=portion,kcal=kcal,protein=protein,fat=fat,carbs=carbs,ingredients=ingredients,allergens=allergens,image_url=f'/assets/{image}.svg',nutrition_source='演示配方估算（非食堂实测）',is_demo=True))
            db.flush()
        # 显式执行seed时，为当天及未来6天发布演示菜单，不修改已有发布状态。
        for offset in range(7):
            day = (datetime.fromisoformat(today())+timedelta(days=offset)).date().isoformat()
            for dish in db.scalars(select(Dish).where(Dish.is_demo.is_(True))):
                for meal in ('早餐','午餐','晚餐'):
                    if not db.scalar(select(MenuEntry.id).where(MenuEntry.date == day,MenuEntry.meal == meal,MenuEntry.dish_id == dish.id)):
                        db.add(MenuEntry(date=day,meal=meal,dish_id=dish.id))
        if not db.scalar(select(Device.id)):
            db.add(Device(canteen_id=canteens[0].id,name='一号回收台 · 模拟设备',source_type='demo'))
        if not db.scalar(select(WasteEvent.id)):
            for i in range(36):
                ratio = [.0,.04,.08,.16,.22,.36][i%6]
                when = datetime.fromisoformat(today())-timedelta(days=i//6)
                db.add(WasteEvent(canteen_id=canteens[i%len(canteens)].id,mode='demo',source='seed',model_version='模拟数据 / 非模型输出',area_ratio=ratio,grade=grade(ratio),confidence=None,status='verified',created_at=when.replace(hour=12,minute=i).astimezone().isoformat()))
        db.commit()
    print('演示账号 student / manager / admin；密码 Demo@12345。请勿用于公网部署。')

def import_legacy(path):
    from .models import LegacyWeightRecord
    from .db import SessionLocal
    with sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro',uri=True) as old, SessionLocal() as db:
        for row in old.execute('SELECT id,created,canteen,meal,mode,report FROM meals'):
            id = 'legacy:'+row[0]
            if not db.get(LegacyWeightRecord,id):
                db.add(LegacyWeightRecord(id=id,data={'created':row[1],'canteen':row[2],'meal':row[3],'mode':row[4],'metric':'weight','report':json.loads(row[5])}))
        db.commit()
    print('旧重量记录导入完成，未转换为面积统计。')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['init','seed','import-legacy'])
    parser.add_argument('--source')
    args = parser.parse_args()
    if args.command == 'init':
        initialize_env()
        from alembic.config import Config
        from alembic import command
        command.upgrade(Config('alembic.ini'),'head')
        print('环境及数据库初始化完成。执行 python -m backend.cli seed 可创建演示数据。')
    elif args.command == 'seed':
        seed()
    elif args.source:
        import_legacy(args.source)
    else:
        parser.error('导入时需要 --source 旧数据库路径')
