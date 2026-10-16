"""本校食物实例分割训练入口，标签使用归一化多边形。"""
import argparse
from pathlib import Path

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',default='datasets/canteen.yaml')
    parser.add_argument('--model',default='yolo11n-seg.pt')
    parser.add_argument('--epochs',type=int,default=100)
    parser.add_argument('--device',default='cpu')
    args=parser.parse_args()
    if not Path(args.data).is_file():parser.error('数据集配置不存在')
    from ultralytics import YOLO
    YOLO(args.model).train(data=args.data,epochs=args.epochs,device=args.device,imgsz=640,project='runs',name='canteen-seg')
