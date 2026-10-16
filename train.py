"""python train.py --data datasets/canteen.yaml --model yolo11n.pt"""
import argparse
from pathlib import Path

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--model', default='yolo11n.pt')
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    if not Path(args.data).is_file():
        parser.error('数据集配置不存在')
    from ultralytics import YOLO
    YOLO(args.model).train(data=args.data, epochs=args.epochs, imgsz=640, device=args.device, project='runs', name='canteen')
