# 运行、接入与部署

## Windows 本地演示

需要Python 3.11/3.12、Node.js 20.19+，推荐pnpm。项目根目录执行：

```powershell
.\setup.ps1
.\start.ps1
# 结束演示
.\stop.ps1
```

平台 http://127.0.0.1:5173 ，API文档 http://127.0.0.1:8000/docs 。账号 student / manager / admin，初始密码均为 Demo@12345。

setup显式创建演示账号与未来7天示例菜单，不覆盖已有账号密码和菜单状态。菜单过期后执行 `python -m backend.cli seed` 再次发布7天演示菜单。后台进程隐藏运行，日志在data目录。停止脚本校验PID与启动时间，不终止PID已被其他进程复用的服务。

## 手动启动

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m backend.cli init
.\.venv\Scripts\python.exe -m backend.cli seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 另开终端，项目根目录
.\.venv\Scripts\python.exe -m backend.worker
# 另开终端，前端目录
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

init在不存在.env时生成随机JWT密钥。可参考.env.example增加配置，不能把密钥提交到Git。

## YOLO与设备

安装 `backend/requirements-vision.txt`，在系统管理→模型配置指定本校训练好的分割权重。原 `train.py` 为矩形检测，新分割入口：

```powershell
python train_seg.py --data datasets/canteen.yaml --model yolo11n-seg.pt --epochs 100
```

训练前将datasets/canteen.yaml中的path改为本校数据集的绝对路径。类别同配置；分割标签格式为 `class x1 y1 x2 y2 ...`（多边形顶点归一化）。图像与标签分别存入images/train、images/val和labels/train、labels/val。按采集批次划分，保留独立测试集。

USB填写数字索引，RTSP填写地址，本地视频填写服务器可读的绝对路径。设备启动时ROI内必须为空，用于背景标定；依次放入餐盘、放稳、移走。视频应以空回收台开头。背景差分适合固定机位单餐盘演示；现场光照、遮挡和多人并行场景需重新验证。ROI应框住餐盘内部有效区域，不能包含人脸或别的餐盘。

食物掩膜合并后计算ROI内占比，不重复累计重叠区域。普通矩形检测权重、不支持类别、低置信度与未配置模型的事件进入人工核验。无分割结果不能自动产生面积占比。面积不等于克数，当前没有称重设备接入。

worker单实例运行，处理任务队列、设备重连、心跳与截图清理；`python -m backend.worker --once` 处理最多10个排队任务后退出。截图保留7天，摘要持续保存。未取得训练数据与模型验证结果前，不宣称识别准确率。

## 大模型

Base URL通常以/v1结尾；请求地址为 `<Base URL>/chat/completions`。配置模型、密钥与超时；接口需支持system/user消息及纯JSON响应，不强制厂商专有参数。

学生必须在饮食档案明确同意后，才会发送身体资料、偏好、当前候选菜单与最近7次饮食营养摘要。不发送用户名或账号ID；不同意、未配置、超时、格式错误时使用规则推荐。

为防止虚构菜品，模型仅返回匹配组合的菜品ID、解释维度代码和提醒代码，由服务器可信模板生成中文解释。自由生成的菜品、热量和价格不被采纳。助手聚焦当前菜单搭配，不能替代开放式医学咨询。

## 服务器部署

本版本以完整本地毕设演示为验收目标。真实校园部署还需现场验证、负载与安全验收：

- 前端 `pnpm build`，Nginx托管frontend/dist，同源代理/api到FastAPI，使用HTTPS。
- `COOKIE_SECURE=true`，`CORS_ORIGINS=["https://你的域名"]`，使用强随机JWT_SECRET；更改管理员密码，禁用演示账号。
- PostgreSQL配置：`DATABASE_URL=postgresql+psycopg://user:password@host/database`，执行 `alembic upgrade head`。切换地址不自动搬迁SQLite已有数据。
- 模型密钥不回传前端或写入审计；保护.env、数据库和备份权限，生产建议使用秘密管理服务。
- 登录限速为进程内实现，多实例需网关限速。worker默认单实例，扩容前改为带租约的队列。
- 备份并验证数据库恢复；监测任务失败、设备心跳与模型降级，限制设备源网络访问。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q
cd frontend
pnpm build
```

健康检查GET /api/v1/health。日期筛选、菜单和大屏按Asia/Shanghai，存储时间使用带时区ISO字符串。
