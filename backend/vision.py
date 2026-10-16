from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from .models import SystemSetting

SUPPORTED = {'rice', 'noodles', 'chicken', 'beef', 'egg', 'tofu', 'vegetables', 'potato', 'fruit'}

def thresholds(db):
    row = db.get(SystemSetting, 'models')
    return row.value.get('thresholds', [.01, .1, .3]) if row else [.01, .1, .3]

def grade(ratio, levels=(.01, .1, .3)):
    if ratio is None:
        return '待核验'
    return ['无明显剩余', '少量', '中量', '大量'][sum(ratio >= x for x in levels)]

def crop_roi(image, roi):
    if not roi or len(roi) != 4:
        raise ValueError('未配置有效餐盘区域')
    x, y, w, h = roi
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1-x and 0 < h <= 1-y):
        raise ValueError('餐盘区域超出图像')
    width, height = image.size
    bounds = (int(x*width), int(y*height), int((x+w)*width), int((y+h)*height))
    if bounds[2]-bounds[0] < 16 or bounds[3]-bounds[1] < 16:
        raise ValueError('餐盘有效区域太小')
    return image.crop(bounds)

def union_ratio(masks, size):
    width, height = size
    union = np.zeros((height, width), dtype=bool)
    for mask in masks:
        resized = Image.fromarray((np.asarray(mask) > .5).astype('uint8')*255).resize((width, height), Image.Resampling.NEAREST)
        union |= np.asarray(resized) > 0
    return float(union.mean())

class Segmenter:
    def __init__(self, weights):
        if not weights or not Path(weights).is_file():
            raise ValueError('未配置本地YOLO权重，真实事件待核验')
        from ultralytics import YOLO
        self.model = YOLO(weights)
        self.version = Path(weights).name

    def detect(self, image):
        result = self.model.predict(image, conf=.15, verbose=False)[0]
        boxes = list(result.boxes) if result.boxes is not None else []
        detections = [{'class': result.names[int(b.cls.item())], 'confidence': float(b.conf.item()), 'bbox': b.xyxy[0].tolist()} for b in boxes]
        confidence = min((d['confidence'] for d in detections), default=1.0)
        supported = all(d['class'] in SUPPORTED for d in detections)
        is_seg = self.model.task == 'segment'
        if not is_seg or (boxes and (result.masks is None or not supported or len(result.masks.data) != len(boxes))):
            return detections, None, confidence, 'pending'
        masks = result.masks.data.cpu().numpy() if result.masks is not None else []
        ratio = union_ratio(masks, image.size)
        from PIL import ImageStat
        gray = ImageStat.Stat(image.convert('L'))
        quality_ok = 15 < gray.mean[0] < 245 and gray.stddev[0] >= 5
        # 严重曝光/低对比或区域几乎完全被覆盖时，不自动确认；遮挡仍需人工核验。
        return detections, ratio, confidence, 'verified' if confidence >= .45 and quality_ok and ratio < .85 else 'pending'

def demo_image(ratio):
    img = Image.new('RGB', (640, 420), '#eee9dc')
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((30, 30, 610, 390), radius=30, fill='#cbd5cf', outline='#87998c', width=4)
    draw.rectangle((70, 80, 280, 340), outline='#87998c', width=3)
    draw.rectangle((310, 80, 570, 200), outline='#87998c', width=3)
    draw.rectangle((310, 220, 570, 340), outline='#87998c', width=3)
    draw.ellipse((90, 130, 90+int(ratio*600), 250), fill='#e3ba67')
    draw.ellipse((340, 110, 340+int(ratio*400), 170), fill='#6d9656')
    draw.text((45, 40), 'SIMULATED TRAY / NOT MODEL OUTPUT', fill='#173d35')
    return img

class TrayGate:
    """固定机位背景差分，稳定3帧触发，连续5帧离开后重新武装。"""
    def __init__(self, stable_frames=3, empty_frames=5):
        self.background = None
        self.previous = None
        self.stable = self.empty = 0
        self.armed = True
        self.stable_frames = stable_frames
        self.empty_frames = empty_frames

    def update(self, frame):
        arr = np.asarray(Image.fromarray(frame).convert('L').resize((64, 48)), dtype=float)/255
        if self.background is None:
            self.background = arr
            self.previous = arr
            return False
        occupied = float(np.mean(np.abs(arr-self.background) > .12)) > .08
        stable = float(np.mean(np.abs(arr-self.previous))) < .015
        self.previous = arr
        if not occupied:
            self.empty += 1
            self.stable = 0
            if self.empty >= self.empty_frames:
                self.armed = True
            return False
        self.empty = 0
        self.stable = self.stable+1 if stable else 0
        if self.armed and self.stable >= self.stable_frames:
            self.armed = False
            return True
        return False
