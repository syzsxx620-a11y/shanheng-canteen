"""独立单实例采集服务：任务队列、设备采集、截图过期清理。"""
import argparse
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select, update
from PIL import Image
from .db import SessionLocal
from .models import DetectionJob, WasteEvent, Device, now, uid
from .recommendations import model_config
from .vision import Segmenter, TrayGate, crop_roi, grade, thresholds, demo_image
from .config import settings

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
models = {}
model_lock = threading.Lock()

def analyze_job(job_id):
    with SessionLocal() as db:
        job = db.get(DetectionJob,job_id)
        if not job or job.status != 'queued':
            return
        # 原子领取：同一任务最多由一个执行者处理。
        claimed = db.execute(update(DetectionJob).where(DetectionJob.id == job_id,DetectionJob.status == 'queued').values(status='processing')).rowcount
        db.commit()
        if not claimed:
            return
        db.refresh(job)
        event_id = 'job:'+job.id
        if db.get(WasteEvent,event_id):
            job.status = 'done'
            job.result_event_id = event_id
            db.commit()
            return
        snapshot, ratio, conf, detections, status, model, error = job.image_path,None,None,[],'pending','unconfigured',''
        if job.mode == 'demo':
            ratio = [.0,.04,.16,.36][int(job.id.replace('-','')[:4],16)%4]
            image = demo_image(ratio)
            path = Path(settings().data_dir)/'snapshots'/f'{job.id}.jpg'
            path.parent.mkdir(parents=True,exist_ok=True)
            image.save(path)
            snapshot,status,model = str(path),'verified','模拟数据 / 非模型输出'
        else:
            try:
                weights = model_config(db)['yolo_weights']
                with model_lock:
                    if weights not in models:
                        models[weights] = Segmenter(weights)
                    detector = models[weights]
                    with Image.open(snapshot) as image:
                        detections,ratio,conf,status = detector.detect(image.convert('RGB'))
                    model = detector.version
            except Exception as exc:
                logger.warning('job %s inference failed: %s',job.id,type(exc).__name__)
                error = '模型未就绪或推理失败，已保留截图供人工核验。'
        reminder = '本次剩余较多，下次可先选小份，按需添加。' if ratio is not None and ratio >= .3 else '按需取餐，少量多次，让每一餐都刚刚好。'
        event = WasteEvent(id=event_id,canteen_id=job.canteen_id,device_id=job.device_id,mode=job.mode,source='device' if job.device_id else 'upload',model_version=model,confidence=conf,area_ratio=ratio,grade=grade(ratio,thresholds(db)),status=status,detections=detections,reminder=reminder,snapshot=snapshot)
        db.add(event)
        job.status,job.result_event_id,job.error = 'done',event_id,error
        db.commit()

def heartbeat(id,status,error=''):
    with SessionLocal() as db:
        device = db.get(Device,id)
        if device:
            device.status,device.heartbeat,device.error = status,now(),error
            db.commit()

def enqueue_frame(device,image):
    with SessionLocal() as db:
        row = DetectionJob(canteen_id=device.canteen_id,device_id=device.id,mode='demo' if device.source_type == 'demo' else 'real',roi=[0,0,1,1])
        db.add(row)
        db.flush()
        if image is not None:
            path = Path(settings().data_dir)/'snapshots'/f'{row.id}.jpg'
            path.parent.mkdir(parents=True,exist_ok=True)
            crop_roi(image,device.roi).save(path,quality=85)
            row.image_path = str(path)
        db.commit()

def device_loop(id):
    cap = None
    gate = TrayGate()
    try:
        while True:
            with SessionLocal() as db:
                device = db.get(Device,id)
                if not device or not device.enabled:
                    break
            if device.source_type == 'demo':
                heartbeat(id,'online')
                enqueue_frame(device,None)
                for _ in range(10):
                    time.sleep(.5)
                    with SessionLocal() as db:
                        if not db.get(Device,id).enabled:
                            return
                continue
            try:
                import cv2
                if cap is None:
                    source = int(device.source) if device.source_type == 'usb' else device.source
                    if device.source_type == 'video' and not Path(device.source).is_file():
                        raise ValueError('视频文件不存在')
                    cap = cv2.VideoCapture(source,cv2.CAP_FFMPEG,[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,5000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,3000]) if device.source_type == 'rtsp' else cv2.VideoCapture(source)
                    if not cap.isOpened():
                        raise ValueError('无法打开视频源')
                    gate = TrayGate()
                ok,frame = cap.read()
                if not ok:
                    if device.source_type == 'video':
                        with SessionLocal() as db:
                            d = db.get(Device,id)
                            d.enabled = False
                            db.commit()
                        break
                    raise ValueError('视频源读取失败')
                heartbeat(id,'online')
                rgb = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                image = Image.fromarray(rgb)
                region = crop_roi(image,device.roi)
                import numpy as np
                if gate.update(np.asarray(region)):
                    enqueue_frame(device,image)
                time.sleep(.2)
            except Exception as exc:
                heartbeat(id,'error',f'{type(exc).__name__}：检查视频源、视觉依赖和ROI配置；5秒后重试。')
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(5)
    finally:
        if cap is not None:
            cap.release()
        heartbeat(id,'stopped')

def cleanup():
    cutoff = datetime.now(timezone.utc)-timedelta(days=settings().image_retention_days)
    with SessionLocal() as db:
        for event in db.scalars(select(WasteEvent).where(WasteEvent.snapshot.is_not(None))):
            if datetime.fromisoformat(event.created_at) < cutoff:
                path = Path(event.snapshot)
                # 只删除服务自己的截图目录下的单个文件。
                if path.resolve().parent == (Path(settings().data_dir)/'snapshots').resolve():
                    path.unlink(missing_ok=True)
                event.snapshot = None
        for job in db.scalars(select(DetectionJob).where(DetectionJob.image_path.is_not(None))):
            if datetime.fromisoformat(job.created_at) < cutoff:
                path = Path(job.image_path)
                if path.resolve().parent == (Path(settings().data_dir)/'snapshots').resolve():
                    path.unlink(missing_ok=True)
                job.image_path = None
        db.commit()

def run(once=False):
    threads = {}
    cleanup_at = 0
    # 单实例运行：重启恢复未完成领取；事件ID保证重复恢复不重复计数。
    with SessionLocal() as db:
        db.execute(update(DetectionJob).where(DetectionJob.status == 'processing').values(status='queued'))
        db.commit()
    while True:
        with SessionLocal() as db:
            jobs = list(db.scalars(select(DetectionJob.id).where(DetectionJob.status == 'queued').limit(10)))
            devices = list(db.scalars(select(Device).where(Device.enabled.is_(True))))
        for job_id in jobs:
            try:
                analyze_job(job_id)
            except Exception:
                logger.exception('任务异常 %s',job_id)
                with SessionLocal() as db:
                    job = db.get(DetectionJob,job_id)
                    job.status,job.error = 'failed','任务处理异常，请检查服务日志后重新提交'
                    db.commit()
        if once:
            cleanup()
            return
        for device in devices:
            if device.id not in threads or not threads[device.id].is_alive():
                thread = threading.Thread(target=device_loop,args=(device.id,),daemon=True)
                threads[device.id] = thread
                thread.start()
        if time.time() > cleanup_at:
            cleanup()
            cleanup_at = time.time()+3600
        time.sleep(.5)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    run(parser.parse_args().once)
