from pathlib import Path
from .core import FOODS

class YoloDetector:
    def __init__(self, weights):
        path = Path(weights)
        if not path.is_file() or path.suffix != '.pt':
            raise ValueError('请指定本地已训练的 .pt 权重文件。')
        from ultralytics import YOLO
        self.model = YOLO(str(path))

    def detect(self, image, confidence=.35):
        result = self.model.predict(image, conf=confidence, verbose=False)[0]
        detections = []
        if result.boxes is not None:
            for box in result.boxes:
                name = result.names[int(box.cls.item())]
                detections.append({'class': name, 'confidence': round(float(box.conf.item()), 3),
                                   'supported': name in FOODS,
                                   'bbox': box.xyxy[0].tolist()})
        return detections, result.plot()[:, :, ::-1]
