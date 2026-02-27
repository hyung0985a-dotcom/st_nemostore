import streamlit as st
import pandas as pd
import json
import re
import os
import sqlite3
import plotly.express as px


# 1. 페이지 초기 설정 및 캐싱
st.set_page_config(page_title="네모 상가 임대 분석 대시보드", layout="wide")

@st.cache_data
def load_and_preprocess_data():
    # 데이터 로드 (JSON 또는 DB 연동)
    md_path = "data/data_json_html.md"
    db_path = "data/nemo_rooms.db"
    
    items = []
    
    # MD 파일 내 JSON 추출
    if os.path.exists(md_path):
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        json_match = re.search(r'(\{[\s\n]*"items":.*?\}[\s\n]*)', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                items = data.get("items", [])
            except: pass
            
    # DB 데이터 결합 (테이블이 존재할 경우)
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            # rooms 테이블이 있는지 확인
            tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
            if "rooms" in tables['name'].values:
                df_db = pd.read_sql("SELECT * FROM rooms", conn)
                db_items = df_db.to_dict('records')
                # ID 기반 중복 제거 (단순화)
                existing_ids = {itm.get('id') for itm in items}
                for itm in db_items:
                    if itm.get('id') not in existing_ids:
                        items.append(itm)
            conn.close()
        except: pass

    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)
    
    # 수치형 변환
    num_cols = ['deposit', 'monthlyRent', 'premium', 'maintenanceFee', 'size']
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    # [데이터 전처리 레이어]
    # 1. 만원 -> 원 단위 변환 (User Formula: deposit * 10000)
    df['deposit_won'] = df['deposit'] * 10000
    df['rent_won'] = df['monthlyRent'] * 10000
    df['premium_won'] = df['premium'] * 10000
    df['maintenance_won'] = df['maintenanceFee'] * 10000
    
    # 2. 추가 파생 컬럼
    df['보증금(억원)'] = df['deposit'] / 10000
    df['월세(만원)'] = df['monthlyRent']
    df['권리금(만원)'] = df['premium']
    df['관리비(만원)'] = df['maintenanceFee']
    
    # 3. 평당월세 (User Formula: monthlyRent / size)
    df['평당월세'] = df.apply(lambda r: r['monthlyRent'] / r['size'] if r['size'] > 0 else 0, axis=1)
    
    return df

# 2. 데이터 로드 및 필터링
df_all = load_and_preprocess_data()

if df_all.empty:
    st.error("데이터를 찾을 수 없습니다. ./data/ 디렉토리 내 파일을 확인해주세요.")
else:
    # 사이드바 필터
    st.sidebar.header("🔍 분석 필터")
    
    # 업종 필터
    categories = ["전체"] + sorted(df_all['businessMiddleCodeName'].unique().tolist())
    sel_cat = st.sidebar.selectbox("업종 선택", categories)
    
    # 층 필터
    floors = ["전체"] + sorted([str(f) for f in df_all['floor'].unique() if f])
    sel_floor = st.sidebar.selectbox("층 선택", floors)
    
    # 면적 슬라이더
    size_range = st.sidebar.slider("면적 범위 (m²)", 
                                   float(df_all['size'].min()), 
                                   float(df_all['size'].max()), 
                                   (float(df_all['size'].min()), float(df_all['size'].max())))
    
    # 월세 슬라이더
    rent_range = st.sidebar.slider("월세 범위 (만원)", 
                                   float(df_all['월세(만원)'].min()), 
                                   float(df_all['월세(만원)'].max()), 
                                   (float(df_all['월세(만원)'].min()), float(df_all['월세(만원)'].max())))
    
    # 데이터 필터링 적용
    df = df_all.copy()
    if sel_cat != "전체":
        df = df[df['businessMiddleCodeName'] == sel_cat]
    if sel_floor != "전체":
        df = df[df['floor'].astype(str) == sel_floor]
    df = df[(df['size'] >= size_range[0]) & (df['size'] <= size_range[1])]
    df = df[(df['월세(만원)'] >= rent_range[0]) & (df['월세(만원)'] <= rent_range[1])]

    # 3. UI 구성
    st.title("🏙️ 네모 상가 임대 분석 대시보드")
    st.markdown("---")
    
    # KPI 카드 (Metric)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("평균 보증금", f"{df['deposit'].mean():,.0f} 만원")
    k2.metric("평균 월세", f"{df['monthlyRent'].mean():,.0f} 만원")
    k3.metric("평균 권리금", f"{df['premium'].mean():,.0f} 만원")
    k4.metric("평균 평당월세", f"{df['평당월세'].mean():,.1f} 만원/m²")
    
    st.markdown("---")
    
    # 4. 시각화 (Plotly Dark Template)
    c1, c2 = st.columns(2)
    
    with c1:
        fig1 = px.histogram(df, x="월세(만원)", nbins=20, title="월세 분포 히스토그램", template="plotly_dark")
        st.plotly_chart(fig1, use_container_width=True)
        
    with c2:
        fig2 = px.scatter(df, x="보증금(억원)", y="월세(만원)", size="size", color="floor", 
                          hover_data=["title"], title="보증금 vs 월세 산점도 (크기:면적, 색상:층)", template="plotly_dark")
        st.plotly_chart(fig2, use_container_width=True)
        
    c3, c4 = st.columns(2)
    
    with c3:
        top10 = df.nlargest(10, '평당월세')
        fig3 = px.bar(top10, x="평당월세", y="title", orientation='h', title="평당월세 TOP10 매물", template="plotly_dark", color="평당월세")
        fig3.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig3, use_container_width=True)
        
    with c4:
        avg_rent = df.groupby('businessMiddleCodeName')['월세(만원)'].mean().reset_index()
        fig4 = px.bar(avg_rent, x="businessMiddleCodeName", y="월세(만원)", title="업종별 평균 월세", template="plotly_dark", color="월세(만원)")
        st.plotly_chart(fig4, use_container_width=True)
        
    st.markdown("---")
    
    # 5. 매물 테이블
    st.subheader("📋 매물 리스트")
    display_cols = ['title', 'nearSubwayStation', 'size', '보증금(억원)', '월세(만원)', '권리금(만원)', '평당월세']
    st.dataframe(df[display_cols].sort_values(by='월세(만원)', ascending=False), 
                 use_container_width=True, 
                 column_config={
                     "보증금(억원)": st.column_config.NumberColumn(format="%.2f 억"),
                     "평당월세": st.column_config.NumberColumn(format="%.2f")
                 })

