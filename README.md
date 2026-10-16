# 膳衡 · 高校智慧食堂平台

基于Python、YOLO与受约束大模型智能体的前后端分离毕设系统。

**Vue 3 + TypeScript + Element Plus + ECharts / FastAPI + SQLAlchemy + Alembic / SQLite或PostgreSQL**

## 快速体验

Windows需要Python 3.11/3.12、Node.js 20.19+与pnpm。在项目根目录：

```powershell
.\setup.ps1
.\start.ps1
```

打开 http://127.0.0.1:5173 。演示账号 `student`、`manager`、`admin`，初始密码均为 `Demo@12345`。演示数据通过初始化命令显式创建。运行 `stop.ps1` 停止本项目服务。

| 入口 | 功能 |
|---|---|
| 学生端 | 注册登录、档案、今日菜单、智能搭配、营养助手、饮食记录、收藏、消息、账号设置 |
| 食堂端 | 概览、模拟/真实检测、人工核验、趋势、菜品、每日菜单、反馈与设备控制 |
| 系统端 | 用户权限、重置密码、食堂窗口、设备配置、模型配置、审计与旧记录查看 |
| 回收大屏 | 匿名结果、节约提醒、当天记录数，从管理端打开 |

## 数据与计算口径

- 回收监测匿名，不关联学生、不识别人脸。视觉指标为**剩余食物掩膜并集 / 餐盘有效区域**，不是重量浪费率。
- 框检测不会当作分割面积。未知、低置信度或模型未就绪结果进入待核验。
- 个人摄入来自学生主动记录的菜品、份数与剩余比例，不从匿名回收照片反推。
- 身体资料自愿填写。成年人维持能量采用Mifflin–St Jeor公式估算；特殊人群仅获得一般搭配，不据BMI诊断营养状况。
- 演示菜单、菜品插画与监测数据明确标记，不代表实测营养或真实模型输出。
- 推荐使用当天可售菜单，过滤过敏原、忌口与预算。未授权外部模型时不发送身体资料。
- 模型选择经过校验的解释/提醒代码，不能改写菜品、价格和营养数值；异常自动降级规则推荐。

## 开发与迁移

frontend为前端；backend为API、数据库、智能体与采集服务；backend/tests为业务与集成测试。

旧app.py、canteen和重量测试保留供参考，新入口为backend.main:app。迁移历史数据：

```powershell
.\.venv\Scripts\python.exe -m backend.cli import-legacy --source data/canteen.db
```

历史称重记录保留独立口径，可在系统端日志页查看，不混入面积看板。

详见 [运行与部署](docs/DEPLOYMENT.md)。API文档 http://127.0.0.1:8000/docs 。真实视觉需额外安装视觉依赖、采集标注数据并训练权重；外部大模型需配置接口。

参考：[YOLO实例分割](https://docs.ultralytics.com/tasks/segment/)、[FastAPI认证](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)、[Mifflin–St Jeor原始研究](https://pubmed.ncbi.nlm.nih.gov/2305711/)、[成人体重规划适用范围](https://www.niddk.nih.gov/health-information/weight-management/body-weight-planner)。
