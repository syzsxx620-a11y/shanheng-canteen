from pathlib import Path
import json
import pandas as pd
import streamlit as st
from PIL import Image, UnidentifiedImageError
from canteen.core import FOODS, Portion, analyze
from canteen.detector import YoloDetector
from canteen.storage import Repository

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='膳衡 · 智慧食堂', page_icon='🥗', layout='wide')
st.markdown('''<style>.stApp{background:#f6f8f7}h1,h2,h3{color:#173d35}div[data-testid="stMetric"]{background:white;padding:20px;border-radius:14px;border:1px solid #e0e9e4}.stButton button{border-radius:10px}header{background:transparent!important}</style>''', unsafe_allow_html=True)
repo = Repository(ROOT / 'data' / 'canteen.db')
st.title('🥗 膳衡 · 高校智慧食堂')
st.caption('餐盘浪费监测 / 食物摄入估算 / 工具型营养建议智能体')
with st.sidebar:
    st.header('工作台')
    page = st.radio('导航', ['餐盘分析', '食堂看板', '系统说明'])
    mode = st.selectbox('数据模式', ['演示', '真实记录'])
    st.caption('演示记录与真实记录分开统计。图片仅在本次会话处理，不保存到数据库。')

@st.cache_resource
def detector(path):
    return YoloDetector(path)

if page == '餐盘分析':
    st.subheader('01 / 餐盘识别与人工核验')
    left, right = st.columns([1.1, 1])
    with left:
        upload = st.file_uploader('上传餐后餐盘照片', type=['jpg', 'jpeg', 'png'])
        camera = st.checkbox('使用摄像头拍摄')
        shot = st.camera_input('拍摄餐盘') if camera else None
        source = shot or upload
        weights = st.text_input('本地YOLO权重路径', str(ROOT / 'weights' / 'best.pt'))
        conf = st.slider('检测置信度', .1, .95, .35, .05)
        if source:
            try:
                img = Image.open(source).convert('RGB')
                st.image(img, caption='待分析餐盘', use_container_width=True)
                if st.button('运行YOLO检测', type='primary'):
                    with st.spinner('检测中…'):
                        detections, annotated = detector(weights).detect(img, conf)
                    st.image(annotated, caption='YOLO检测结果', use_container_width=True)
                    st.dataframe(detections, use_container_width=True)
                    st.info('请根据检测类别，在右侧选择食物并填写称重数据。未支持类别需先扩充食物库。')
            except (UnidentifiedImageError, OSError, ValueError, ImportError) as e:
                st.error(str(e))
            except Exception as e:
                st.error(f'模型推理失败：{e}')
        else:
            st.info('上传照片可运行真实检测；没有模型时可直接使用右侧演示数据体验分析。')
    with right:
        st.warning('照片检测只输出类别和位置，不能直接推断克数。请填写称重结果；估算数据需自行核验。')
        canteen = st.selectbox('食堂', ['第一食堂', '第二食堂', '第三食堂'])
        meal = st.selectbox('餐次', ['午餐', '晚餐', '早餐'])
        names = {k: v[0] for k, v in FOODS.items()}
        foods = st.multiselect('食物类别', list(FOODS), default=['rice', 'chicken', 'vegetables'] if mode == '演示' else [], format_func=lambda k: names[k])
        portions = []
        for food in foods:
            a, b = st.columns(2)
            served = a.number_input(f'{names[food]} · 供餐(g)', min_value=0.0, max_value=5000.0, value=150.0 if mode == '演示' else 0.0, step=5.0, key=mode+food+'s')
            waste = b.number_input(f'{names[food]} · 剩余(g)', min_value=0.0, max_value=5000.0, value=30.0 if mode == '演示' else 0.0, step=5.0, key=mode+food+'w')
            portions.append(Portion(food, served, waste))
        if st.button('生成分析并保存', type='primary'):
            try:
                report = analyze(portions)
                repo.save(canteen, meal, mode, report)
                st.session_state['report'] = report
                st.success(f'已保存{mode}记录')
            except ValueError as e:
                st.error(str(e))
    if 'report' in st.session_state:
        r = st.session_state['report']
        st.subheader('02 / 最近一次分析结果')
        cols = st.columns(4)
        for col, label, value in zip(cols, ['剩余重量', '浪费比例', '摄入能量估算', '摄入蛋白质估算'], [f"{r['waste_g']:.0f} g", f"{r['waste_rate']:.1%}", f"{r['nutrients']['kcal']:.0f} kcal", f"{r['nutrients']['protein']:.1f} g"]):
            col.metric(label, value)
        st.subheader('营养建议智能体')
        for advice in r['advice']:
            st.write('• ' + advice)
        st.caption('采用可审计的规则工具智能体，未接入大语言模型。食物成分是示例值，建议仅用于项目演示与一般饮食记录。')
        with st.expander('工具执行记录与完整结果'):
            st.json(r)
        st.download_button('下载本次报告 JSON', json.dumps(r, ensure_ascii=False, indent=2), 'report.json', 'application/json')
elif page == '食堂看板':
    st.subheader('食堂浪费与摄入趋势')
    records = [r for r in repo.records() if r['mode'] == mode]
    if not records:
        st.info(f'暂无{mode}记录，请先完成一次餐盘分析。')
    else:
        df = pd.DataFrame([{k: r[k] for k in ['created', 'canteen', 'meal', 'served_g', 'waste_g', 'waste_rate']} for r in records])
        chosen = st.multiselect('食堂筛选', sorted(df.canteen.unique()), default=sorted(df.canteen.unique()))
        df = df[df.canteen.isin(chosen)].copy()
        if df.empty:
            st.info('当前筛选没有数据。')
        else:
            a, b, c = st.columns(3)
            a.metric('记录餐盘', len(df))
            b.metric('剩余总量', f'{df.waste_g.sum()/1000:.2f} kg')
            c.metric('加权浪费比例', f'{df.waste_g.sum()/df.served_g.sum():.1%}')
            df['日期'] = df.created.str[:10]
            st.bar_chart(df.groupby('日期')[['waste_g']].sum(), color='#26866c')
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button('导出CSV', df.to_csv(index=False).encode('utf-8-sig'), 'canteen-records.csv', 'text/csv')
else:
    st.subheader('系统架构与使用边界')
    st.markdown('''1. **感知层**：Ultralytics YOLO加载本地自训练权重，输出食物类别、位置与置信度。
2. **核验层**：人工确认类别并输入供餐/剩余重量，避免把二维面积当作重量。
3. **智能体层**：按顺序调用质量检查、营养计算、建议生成工具，保留执行记录。
4. **数据层**：SQLite保存匿名记录，演示数据独立筛选，支持CSV与JSON导出。

真实部署需补充本校菜品数据集、经审核的食物成分库及重量标定。通用YOLO权重无法直接识别本系统所有菜品。当前原型适合本机使用；多人部署前需增加登录、权限和备份。''')
    st.dataframe(pd.DataFrame([dict(类别=k, 名称=v[0], 食物组=v[1], 每百克能量=v[2], 蛋白质=v[3], 脂肪=v[4], 碳水=v[5]) for k,v in FOODS.items()]), hide_index=True)
