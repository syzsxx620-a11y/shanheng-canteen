import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from backend.db import Base
from backend.main import app, attempts
from backend import db as database
from backend import worker
from backend.cli import seed, import_legacy
from backend.models import User, Canteen, Device, WasteEvent, Profile, DetectionJob, Dish, MenuEntry, LegacyWeightRecord
from backend.nutrition import energy_summary, allowed, choose_combos
from backend.recommendations import explain_with_llm, today
from backend.vision import union_ratio, grade, TrayGate, crop_roi, Segmenter

@pytest.fixture()
def context(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///'+str(tmp_path/'test.db'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(database,'SessionLocal',sessions)
    monkeypatch.setattr(worker,'SessionLocal',sessions)
    from backend.config import settings
    monkeypatch.setattr(settings(),'data_dir',str(tmp_path))
    monkeypatch.setattr(settings(),'jwt_secret','testing-secret-that-is-more-than-32-characters')
    monkeypatch.setattr(settings(),'yolo_weights','')
    attempts.clear()
    seed()
    with TestClient(app) as client:
        yield client,sessions,tmp_path
    engine.dispose()

def login(client, username='student'):
    response = client.post('/api/v1/auth/login',json={'username':username,'password':'Demo@12345'})
    assert response.status_code == 200,response.text
    return {'Authorization':'Bearer '+response.json()['access_token']}

def test_registration_refresh_and_logout(context):
    client,sessions,_ = context
    r = client.post('/api/v1/auth/register',json={'username':'new_user','password':'Password123','role':'system_admin'})
    assert r.status_code == 201
    assert r.json()['role'] == 'student'
    assert client.post('/api/v1/auth/register',json={'username':'new_user','password':'Password123'}).status_code == 409
    headers = login(client)
    assert client.get('/api/v1/auth/me',headers=headers).status_code == 200
    cookie = client.cookies.get('refresh_token')
    r = client.post('/api/v1/auth/refresh')
    assert r.status_code == 200
    assert cookie != client.cookies.get('refresh_token')
    new_headers={'Authorization':'Bearer '+r.json()['access_token']}
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert client.get('/api/v1/auth/me',headers=new_headers).status_code == 401
    assert client.post('/api/v1/auth/refresh').status_code == 401

def test_permissions_and_canteen_scope(context):
    client,sessions,_ = context
    student = login(client)
    assert client.get('/api/v1/admin/users',headers=student).status_code == 403
    assert client.get('/api/v1/waste-events',headers=student).status_code == 403
    manager = login(client,'manager')
    rows = client.get('/api/v1/waste-events',headers=manager).json()
    with sessions() as db:
        cids = list(db.scalars(select(Canteen.id)))
        user = db.scalar(select(User).where(User.username=='manager'))
        assert all(r['canteen_id']==user.canteen_id for r in rows)
        other = next(c for c in cids if c!=user.canteen_id)
    assert client.post('/api/v1/detection-jobs',headers=manager,data={'canteen_id':other,'mode':'demo'}).status_code == 403
    assert client.get('/api/v1/admin/model-config',headers=manager).status_code == 403

def test_password_and_admin_revocation(context):
    client,sessions,_ = context
    student = login(client)
    assert client.post('/api/v1/auth/password',headers=student,json={'old_password':'wrong','new_password':'NewPassword123'}).status_code == 400
    assert client.post('/api/v1/auth/password',headers=student,json={'old_password':'Demo@12345','new_password':'NewPassword123'}).status_code == 200
    assert client.get('/api/v1/auth/me',headers=student).status_code == 401
    admin = login(client,'admin')
    users=client.get('/api/v1/admin/users',headers=admin).json()
    target=next(u for u in users if u['username']=='student')
    assert client.post(f"/api/v1/admin/users/{target['id']}/reset-password",headers=admin,json={'password':'Demo@12345'}).status_code==200
    student=login(client)
    assert client.put(f"/api/v1/admin/users/{target['id']}",headers=admin,json={'role':'student','active':False}).status_code==200
    assert client.get('/api/v1/auth/me',headers=student).status_code==401
    assert client.post('/api/v1/auth/login',json={'username':'student','password':'Demo@12345'}).status_code==403

def test_profile_and_personal_records_isolated(context):
    client,sessions,_=context
    student=login(client)
    assert client.put('/api/v1/me/profile',headers=student,json={'height_cm':-10}).status_code==422
    profile=client.put('/api/v1/me/profile',headers=student,json={'height_cm':170,'weight_kg':60,'age':20,'sex':'female','allergens':['鸡蛋']}).json()
    assert profile['energy']['bmi']==20.8
    dish=client.get('/api/v1/dishes',headers=student).json()[0]
    r=client.post('/api/v1/me/meal-records',headers=student,json={'date':today(),'meal':'午餐','items':[{'dish_id':dish['id'],'servings':2,'leftover_fraction':.5}]}).json()
    assert r['nutrients']['kcal']==dish['kcal']
    admin=login(client,'admin')
    assert client.get('/api/v1/me/meal-records',headers=admin).json()==[]
    assert client.delete('/api/v1/me/meal-records/'+r['id'],headers=admin).status_code==404
    assert client.post('/api/v1/me/notifications/'+client.get('/api/v1/me/notifications',headers=student).json()[0]['id']+'/read',headers=admin).status_code==404

def test_recommendation_filters_refresh_and_unavailable(context):
    client,sessions,_=context
    headers=login(client)
    client.put('/api/v1/me/profile',headers=headers,json={'allergens':['鸡蛋','大豆'],'budget':12,'dislikes':['杂粮']})
    r=client.post('/api/v1/recommendations',headers=headers,json={'mode':'demo'}).json()
    assert r['combination'] is None # 演示蛋白类均含鸡蛋或大豆，不能绕过过滤。
    client.put('/api/v1/me/profile',headers=headers,json={'budget':20})
    r=client.post('/api/v1/recommendations',headers=headers,json={'mode':'demo'}).json()
    assert r['combination']['price']<=20
    assert len({d['canteen_id'] for d in r['combination']['dishes']})==1
    cached=client.post('/api/v1/recommendations',headers=headers,json={'mode':'demo'}).json()
    assert r['id']==cached['id']
    changed=client.post('/api/v1/recommendations',headers=headers,json={'mode':'demo','refresh':True}).json()
    assert [d['id'] for d in changed['combination']['dishes']] != [d['id'] for d in r['combination']['dishes']]
    with sessions() as db:
        for entry in db.scalars(select(MenuEntry)):
            entry.available=False
        db.commit()
    assert client.post('/api/v1/recommendations',headers=headers,json={'mode':'demo'}).json()['combination'] is None
    assert 'profile' not in r

def test_real_menu_empty_demo_isolation(context):
    client,_,_=context
    student=login(client)
    assert client.get('/api/v1/menus?mode=real',headers=student).json()==[]
    admin=login(client,'admin')
    assert client.get('/api/v1/analytics?mode=real',headers=admin).json()['total']==0
    demo=client.get('/api/v1/analytics?mode=demo',headers=admin).json()
    assert demo['total']==36
    assert client.get('/api/v1/analytics/export?mode=real',headers=admin).content.decode('utf-8-sig').count('\n')==1
    cid=client.get('/api/v1/canteens',headers=admin).json()[0]['id']
    public=client.get('/api/v1/display/'+cid).json()
    assert 'user_id' not in str(public) and 'snapshot' not in str(public)

def test_detection_demo_idempotence_review_and_snapshot(context):
    client,sessions,tmp_path=context
    headers=login(client,'admin')
    cid=client.get('/api/v1/canteens',headers=headers).json()[0]['id']
    r=client.post('/api/v1/detection-jobs',headers=headers,data={'canteen_id':cid,'mode':'demo'})
    assert r.status_code==202,r.text
    id=r.json()['id']
    worker.analyze_job(id)
    worker.analyze_job(id)
    job=client.get('/api/v1/detection-jobs/'+id,headers=headers).json()
    assert job['status']=='done'
    assert 'image_path' not in job
    with sessions() as db:
        event=db.get(WasteEvent,job['result_event_id'])
        assert event.mode=='demo' and event.model_version.startswith('模拟')
        assert Path(event.snapshot).exists()
    eid=job['result_event_id']
    assert client.post('/api/v1/waste-events/'+eid+'/review',headers=headers,json={'area_ratio':.25,'status':'verified','note':'人工复核'}).json()['grade']=='中量'
    assert client.get('/api/v1/waste-events/'+eid+'/snapshot',headers=headers).status_code==200
    with sessions() as db:
        event=db.get(WasteEvent,eid)
        assert len(event.review_history)==1
        event.created_at=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
        db.commit()
    worker.cleanup()
    assert client.get('/api/v1/waste-events/'+eid+'/snapshot',headers=headers).status_code==404

def test_real_detection_without_weights_is_pending(context):
    client,sessions,tmp_path=context
    headers=login(client,'admin')
    cid=client.get('/api/v1/canteens',headers=headers).json()[0]['id']
    image=Image.new('RGB',(100,100),'white');stream=io.BytesIO();image.save(stream,format='PNG')
    content=stream.getvalue()
    invalid=client.post('/api/v1/detection-jobs',headers=headers,data={'canteen_id':cid,'mode':'real','roi':'[0,0,2,1]'},files={'image':('tray.png',content,'image/png')})
    assert invalid.status_code==400
    r=client.post('/api/v1/detection-jobs',headers=headers,data={'canteen_id':cid,'mode':'real','roi':'[0,0,1,1]'},files={'image':('tray.png',content,'image/png')})
    assert r.status_code==202
    worker.analyze_job(r.json()['id'])
    with sessions() as db:
        event=db.get(WasteEvent,'job:'+r.json()['id'])
        assert event.status=='pending' and event.area_ratio is None

def test_device_validation_and_controls(context):
    client,_,_=context
    headers=login(client,'admin');cid=client.get('/api/v1/canteens',headers=headers).json()[0]['id']
    assert client.post('/api/v1/devices',headers=headers,json={'canteen_id':cid,'name':'x','roi':[.5,0,1,1]}).status_code==422
    r=client.post('/api/v1/devices',headers=headers,json={'canteen_id':cid,'name':'摄像头','source_type':'usb','source':'0','roi':[0,0,1,1]})
    assert r.status_code==201
    id=r.json()['id']
    assert client.post('/api/v1/devices/'+id+'/toggle',headers=headers).json()['enabled']
    assert client.put('/api/v1/devices/'+id,headers=headers,json={'canteen_id':cid,'name':'改名','source_type':'demo'}).status_code==409

def test_model_key_never_exposed(context):
    client,sessions,_=context
    headers=login(client,'admin')
    assert client.put('/api/v1/admin/model-config',headers=headers,json={'llm_api_key':'private-test-key','thresholds':[.1,.05,.3]}).status_code==422
    assert client.put('/api/v1/admin/model-config',headers=headers,json={'llm_api_key':'private-test-key'}).status_code==200
    r=client.get('/api/v1/admin/model-config',headers=headers)
    assert r.json()['api_key_configured'] and 'private-test-key' not in r.text
    assert 'private-test-key' not in client.get('/api/v1/admin/audit-logs',headers=headers).text

def test_feedback_ownership_and_response(context):
    client,_,_=context
    student=login(client);cid=client.get('/api/v1/canteens',headers=student).json()[0]['id']
    result=client.post('/api/v1/feedback',headers=student,json={'canteen_id':cid,'rating':4,'content':'希望有小份菜'}).json()
    manager=login(client,'manager')
    assert client.post('/api/v1/feedback/'+result['id']+'/reply',headers=manager,json={'name':'谢谢反馈，已记录'}).status_code==200
    assert any(n['title']=='食堂回复了你的反馈' for n in client.get('/api/v1/me/notifications',headers=student).json())

def test_no_external_call_without_consent(context,monkeypatch):
    client,_,_=context;headers=login(client)
    def fail(*args,**kwargs):
        raise AssertionError('未经同意不应发送外部请求')
    monkeypatch.setattr(httpx,'post',fail)
    result=client.post('/api/v1/assistant',headers=headers,json={'message':'今天怎么吃？'}).json()
    assert result['source']=='规则推荐'

def test_energy_formula_and_special_cases():
    p={'height_cm':180,'weight_kg':75,'age':25,'sex':'male','activity':'sedentary'}
    assert energy_summary(p)['daily_kcal']==2106
    assert energy_summary({**p,'age':17})['daily_kcal'] is None
    assert energy_summary({**p,'special_condition':True})['daily_kcal'] is None
    assert energy_summary({})['daily_kcal'] is None

def test_unknown_allergens_and_budget():
    d={'id':'x','name':'测试','category':'主食','ingredients':['米'],'allergens':None,'price':5,'kcal':100,'protein':2,'fat':1,'carbs':20}
    assert not allowed(d,{'allergens':['花生']})
    assert not allowed({**d,'allergens':['花生']},{'allergens':['花生']})
    assert choose_combos([d],{'budget':1})[0]==[]

@pytest.mark.parametrize('response,source',[
    ({'dish_ids':['a'],'reason_codes':['balanced','budget'],'reminder_code':'small_portion'},'大模型解释'),
    ({'dish_ids':['invented'],'reason_codes':['balanced'],'reminder_code':'small_portion'},'规则推荐'),
    ({'dish_ids':['a'],'reason_codes':['unsafe'],'reminder_code':'small_portion'},'规则推荐'),
    ({'dish_ids':['a'],'reason':'建议吃不存在的菜','reminder':'x'},'规则推荐'),
    ('not json','规则推荐'),
])
def test_llm_validation(monkeypatch,response,source):
    data=json.dumps(response,ensure_ascii=False) if not isinstance(response,str) else response
    monkeypatch.setattr(httpx,'post',lambda *a,**k:Mock(raise_for_status=lambda:None,json=lambda:{'choices':[{'message':{'content':data}}]}))
    default={'dish_ids':['a'],'reason':'规则解释','reminder':'按需取餐'}
    payload={'combination':{'dishes':[{'id':'a','name':'米饭'}]}}
    assert explain_with_llm({'llm_base_url':'https://example.test/v1','llm_model':'test','llm_api_key':'key','llm_timeout':1},payload,default)[1]==source

def test_llm_timeout(monkeypatch):
    def timeout(*a,**kw):raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr(httpx,'post',timeout)
    default={'dish_ids':['a'],'reason':'规则','reminder':'节约'}
    assert explain_with_llm({'llm_base_url':'https://example.test/v1','llm_model':'x','llm_api_key':'k','llm_timeout':1},{},default)[1]=='规则推荐'

def test_union_does_not_double_count_and_grade():
    mask=np.zeros((10,10));mask[:5,:]=1
    assert union_ratio([mask,mask],(10,10))==.5
    assert grade(0)=='无明显剩余' and grade(.01)=='少量' and grade(.1)=='中量' and grade(.3)=='大量'
    assert grade(None)=='待核验'
    with pytest.raises(ValueError):crop_roi(Image.new('RGB',(100,100)),[0,0,2,1])

def test_tray_entry_stability_exit_deduplication():
    gate=TrayGate();empty=np.zeros((100,100,3),dtype=np.uint8);tray=np.full((100,100,3),255,dtype=np.uint8)
    assert not gate.update(empty)
    values=[gate.update(tray) for _ in range(20)]
    assert sum(values)==1
    for _ in range(6):gate.update(empty)
    assert sum(gate.update(tray) for _ in range(20))==1

from pathlib import Path

def test_schema_migration_roundtrip(tmp_path,monkeypatch):
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect
    engine=create_engine('sqlite:///'+str(tmp_path/'migration.db'))
    monkeypatch.setattr(database,'engine',engine)
    config=Config('alembic.ini')
    command.upgrade(config,'head')
    assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())
    command.downgrade(config,'base')
    assert inspect(engine).get_table_names()==['alembic_version']
    engine.dispose()

def test_legacy_import_idempotent(context):
    import sqlite3
    client,sessions,tmp_path=context
    path=tmp_path/'old.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE meals (id TEXT, created TEXT, canteen TEXT, meal TEXT, mode TEXT, report TEXT)')
        conn.execute('INSERT INTO meals VALUES (?,?,?,?,?,?)',('old-1',today(),'旧食堂','午餐','演示',json.dumps({'waste_g':20})))
    import_legacy(path);import_legacy(path)
    with sessions() as db:
        rows=list(db.scalars(select(LegacyWeightRecord)))
        assert len(rows)==1 and rows[0].data['metric']=='weight'

def test_real_and_demo_personal_records_do_not_mix(context):
    client,sessions,_=context;headers=login(client)
    dishes=client.get('/api/v1/dishes',headers=headers).json()
    demo=dishes[0]
    with sessions() as db:
        real=Dish(window_id=demo['window_id'],name='真实菜',category='蔬菜',price=3,portion_g=100,kcal=100,protein=2,fat=1,carbs=10,ingredients=[],allergens=[],is_demo=False)
        db.add(real);db.commit();real_id=real.id
    items=[{'dish_id':demo['id'],'servings':1},{'dish_id':real_id,'servings':1}]
    assert client.post('/api/v1/me/meal-records',headers=headers,json={'date':today(),'meal':'午餐','items':items}).status_code==400
    assert client.post('/api/v1/me/meal-records',headers=headers,json={'date':today(),'meal':'午餐','items':items[1:]}).status_code==201
    assert client.get('/api/v1/me/meal-records?mode=demo',headers=headers).json()==[]
    assert len(client.get('/api/v1/me/meal-records?mode=real',headers=headers).json())==1

def test_detector_does_not_infer_area_from_boxes():
    result=Mock(boxes=[],masks=None)
    detector=Segmenter.__new__(Segmenter)
    detector.model=Mock(task='detect',predict=lambda *a,**kw:[result])
    assert detector.detect(Image.new('RGB',(100,100)))[1] is None
    assert detector.detect(Image.new('RGB',(100,100)))[3]=='pending'

def test_detector_rejects_unsupported_class_and_low_confidence():
    box=Mock()
    box.cls.item.return_value=0;box.conf.item.return_value=.2
    box.xyxy.__getitem__=Mock(return_value=Mock(tolist=lambda:[0,0,50,50]))
    data=Mock()
    data.__len__=Mock(return_value=1)
    data.cpu.return_value.numpy.return_value=np.ones((1,10,10))*.6
    result=Mock(boxes=[box],masks=Mock(data=data),names={0:'unknown'})
    detector=Segmenter.__new__(Segmenter);detector.model=Mock(task='segment',predict=lambda *a,**kw:[result])
    assert detector.detect(Image.new('RGB',(100,100)))[1] is None
    result.names={0:'rice'}
    output=detector.detect(Image.new('RGB',(100,100),'white'))
    assert output[1]==1 and output[3]=='pending'

def test_worker_device_disconnect_status(context,monkeypatch):
    client,sessions,_=context
    from types import SimpleNamespace
    with sessions() as db:
        device=db.scalar(select(Device));device.enabled=True;device.source_type='usb';device.source='0';db.commit();id=device.id
    class BadCapture:
        def isOpened(self):return False
        def release(self):pass
    monkeypatch.setitem(__import__('sys').modules,'cv2',SimpleNamespace(VideoCapture=lambda *a:BadCapture()))
    errors=[]
    def stop_after_failure(duration):
        with sessions() as db:
            d=db.get(Device,id);errors.append(d.error);d.enabled=False;db.commit()
    monkeypatch.setattr(worker.time,'sleep',stop_after_failure)
    worker.device_loop(id)
    assert any('检查视频源' in e for e in errors)
