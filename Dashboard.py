"""
GISource 团队绩效管理面板
Performance Monitoring Dashboard for GISource Team

运行方式: streamlit run Dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import pytz
import pickle
import os
import mysql.connector
import configparser
import warnings
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import re

# 配置
warnings.filterwarnings('ignore')
china_tz = pytz.timezone('Asia/Shanghai')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = '1LcfxcTCuj9ZJXXMxyFQwt-xnbAviNP8j9oDr6OG5-Go'


# ==================== 数据获取函数 ====================

@st.cache_resource
def authorize_credentials():
    """谷歌 API 密钥凭据"""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds


def fetch_google_sheet_data(range_name):
    """从 Google Sheet 获取数据"""
    try:
        creds = authorize_credentials()
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        values = result.get('values', [])
        
        if not values:
            return pd.DataFrame()
        
        headers = values[0]
        data = values[1:]
        
        # 调整列数
        adjusted_data = []
        for row in data:
            adjusted_row = row + [None] * (len(headers) - len(row))
            adjusted_data.append(adjusted_row)
        
        return pd.DataFrame(adjusted_data, columns=headers)
    except Exception as e:
        st.error(f"读取 Google Sheet 出错: {str(e)}")
        return pd.DataFrame()


@st.cache_resource
def connect_to_database():
    """连接到 MySQL 数据库"""
    try:
        config = configparser.ConfigParser()
        config.read('sql_credentials.txt')
        
        mysql_config = {
            'host': config['MySQL']['host'],
            'port': config['MySQL'].getint('port', 3306),
            'user': config['MySQL']['user'],
            'password': config['MySQL']['password'],
            'database': config['MySQL']['database']
        }
        
        conn = mysql.connector.connect(**mysql_config)
        return conn
    except Exception as e:
        st.error(f"数据库连接失败: {str(e)}")
        return None


def fetch_mysql_data():
    """从 MySQL 获取数据"""
    try:
        conn = connect_to_database()
        if not conn:
            return pd.DataFrame()
        
        query = """
        SELECT 
            Event_ID,
            University_CN,
            University_EN,
            Country_CN,
            Job_CN,
            Job_EN,
            Description,
            Title_CN,
            Title_EN,
            Date,
            IS_Public,
            IS_Deleted
        FROM GISource
        WHERE IS_Deleted = 0
        ORDER BY Date DESC
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"读取数据库出错: {str(e)}")
        return pd.DataFrame()


# ==================== 数据处理函数 ====================

def parse_db_description(df):
    """解析 MySQL Description 字段，提取 URL 和 Deadline"""
    if df.empty:
        return df
    
    # 提取 URL
    url_pattern = r"URL:\s*(https?://[^\s<]+)"
    df['Extracted_Source'] = df['Description'].str.extract(url_pattern, flags=re.IGNORECASE)
    
    # 提取 Deadline - 支持日期格式和 "Soon"
    date_pattern = r"Deadline:\s*(\d{4}-\d{2}-\d{2}|Soon)"
    df['Extracted_Deadline'] = df['Description'].str.extract(date_pattern, flags=re.IGNORECASE)
    
    # 创建复合键 (Composite Key) = URL + Deadline
    df['Composite_Key'] = (
        df['Extracted_Source'].fillna('').str.strip() + "_" + 
        df['Extracted_Deadline'].fillna('').str.strip()
    )
    
    return df


def prepare_sheet_data(df):
    """准备 Google Sheet 数据，生成复合键"""
    if df.empty:
        return df
    
    # 处理 Deadline：支持日期格式、Excel序列号和 "Soon"
    def format_deadline(val):
        if pd.isna(val) or val == '':
            return ''
        if str(val).strip().lower() == 'soon':
            return 'Soon'
        
        # 尝试检测 Excel 序列日期（数字格式，通常在 1-100000 范围内）
        try:
            # 先尝试转换为数字
            num_val = float(str(val).strip())
            # 如果是合理的 Excel 日期序列号（1900-01-01 到未来几十年）
            if 1 <= num_val <= 100000:
                # Excel 日期从 1900-01-01 开始计数
                # pandas 的 to_datetime 可以处理 Excel 序列号
                excel_date = pd.Timestamp('1899-12-30') + pd.Timedelta(days=num_val)
                return excel_date.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass
        
        # 尝试标准日期解析
        try:
            return pd.to_datetime(val).strftime('%Y-%m-%d')
        except:
            return ''
    
    df['Deadline_Str'] = df['Deadline'].apply(format_deadline)
    
    # 创建复合键
    df['Composite_Key'] = (
        df['Source'].fillna('').str.strip() + "_" + 
        df['Deadline_Str'].str.strip()
    )
    
    return df


def merge_data():
    """合并 Google Sheet 和 MySQL 数据"""
    # 获取数据
    with st.spinner('正在从 Google Sheet 读取数据...'):
        filled_data = fetch_google_sheet_data('Filled')
    
    with st.spinner('正在从数据库读取数据...'):
        db_data = fetch_mysql_data()
    
    if filled_data.empty or db_data.empty:
        st.warning("数据为空，无法生成报表")
        return pd.DataFrame()
    
    # 处理数据
    db_data = parse_db_description(db_data)
    filled_data = prepare_sheet_data(filled_data)
    
    # 合并数据
    merged_df = pd.merge(
        db_data,
        filled_data[['Composite_Key', 'Verifier', 'Direction', 'University_CN']],
        on='Composite_Key',
        how='inner',
        suffixes=('_DB', '_Sheet')
    )
    
    # 数据清理
    if not merged_df.empty:
        # 转换日期
        merged_df['Date'] = pd.to_datetime(merged_df['Date'])
        
        # 处理 Deadline：将 "Soon" 按照 30 天计算，支持 Excel 序列号
        def parse_deadline(val, entry_date):
            if pd.isna(val) or val == '':
                return pd.NaT
            if str(val).strip().lower() == 'soon':
                # Soon 按照入库日期 + 30 天计算
                return entry_date + timedelta(days=30)
            
            # 尝试检测 Excel 序列日期
            try:
                num_val = float(str(val).strip())
                if 1 <= num_val <= 100000:
                    # Excel 日期从 1899-12-30 开始计数
                    excel_date = pd.Timestamp('1899-12-30') + pd.Timedelta(days=num_val)
                    return excel_date
            except (ValueError, TypeError):
                pass
            
            # 标准日期解析
            try:
                return pd.to_datetime(val)
            except:
                return pd.NaT
        
        merged_df['Extracted_Deadline_Date'] = merged_df.apply(
            lambda row: parse_deadline(row['Extracted_Deadline'], row['Date']), 
            axis=1
        )
        
        # 过滤掉 Verifier 为空或为 LLM 的数据
        merged_df = merged_df[
            (merged_df['Verifier'].notna()) & 
            (merged_df['Verifier'] != 'LLM') &
            (merged_df['Verifier'] != '')
        ]
    
    return merged_df


# ==================== 可视化组件 ====================

def display_kpi_metrics(filtered_data):
    """显示关键指标"""
    col1, col2, col3, col4 = st.columns(4)
    
    total_entries = len(filtered_data)
    active_members = filtered_data['Verifier'].nunique() if not filtered_data.empty else 0
    
    # 计算平均提前天数（需要先计算 Lead_Time）
    avg_lead_time = 0
    if not filtered_data.empty and 'Extracted_Deadline_Date' in filtered_data.columns:
        # 计算 Lead_Time
        filtered_data_copy = filtered_data.copy()
        filtered_data_copy['Lead_Time'] = (
            filtered_data_copy['Extracted_Deadline_Date'] - filtered_data_copy['Date']
        ).dt.days
        
        # 过滤有效数据
        valid_lead_times = filtered_data_copy[
            (filtered_data_copy['Lead_Time'].notna()) & 
            (filtered_data_copy['Lead_Time'] >= 0)
        ]
        avg_lead_time = valid_lead_times['Lead_Time'].mean() if not valid_lead_times.empty else 0
    
    col1.metric("📊 入库总数", total_entries)
    col2.metric("👥 活跃成员数", active_members)
    col3.metric("⏰ 平均提前天数", f"{avg_lead_time:.1f} 天")
    
    # 最近7天新增
    if not filtered_data.empty:
        today = datetime.now(china_tz).date()
        seven_days_ago = today - timedelta(days=7)
        recent_data = filtered_data[filtered_data['Date'].dt.date >= seven_days_ago]
        col4.metric("📈 最近7天新增", len(recent_data))


def display_member_leaderboard(filtered_data):
    """成员贡献排行榜"""
    st.subheader("🏆 成员贡献排行")
    
    if filtered_data.empty:
        st.info("暂无数据")
        return
    
    # 统计每个人的贡献
    leaderboard = filtered_data['Verifier'].value_counts().reset_index()
    leaderboard.columns = ['成员', '入库数量']
    
    # 绘制条形图
    fig = px.bar(
        leaderboard,
        x='成员',
        y='入库数量',
        text='入库数量',
        color='入库数量',
        color_continuous_scale='Blues',
        title='成员入库数量排行'
    )
    fig.update_traces(textposition='outside')
    fig.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig, width='stretch')
    
    # 显示详细表格
    with st.expander("查看详细数据"):
        st.dataframe(leaderboard, width='stretch')


def display_daily_trend(filtered_data):
    """每日工作趋势"""
    st.subheader("📈 每日工作趋势")
    
    if filtered_data.empty:
        st.info("暂无数据")
        return
    
    # 按日期和成员分组统计
    trend = filtered_data.groupby([filtered_data['Date'].dt.date, 'Verifier']).size().reset_index(name='Count')
    trend.columns = ['Date', 'Verifier', 'Count']
    
    # 绘制折线图
    fig = px.line(
        trend,
        x='Date',
        y='Count',
        color='Verifier',
        markers=True,
        title='成员每日贡献趋势'
    )
    fig.update_layout(
        xaxis_title='日期',
        yaxis_title='入库数量',
        height=400,
        hovermode='x unified'
    )
    st.plotly_chart(fig, width='stretch')


def display_lead_time_analysis(filtered_data):
    """信息时效性分析"""
    st.subheader("⏳ 信息时效性分析")
    
    if filtered_data.empty:
        st.info("暂无数据")
        return
    
    # 计算提前期：Deadline - 入库时间（Soon 按 30 天计算）
    if 'Extracted_Deadline_Date' in filtered_data.columns:
        filtered_data['Lead_Time'] = (
            filtered_data['Extracted_Deadline_Date'] - filtered_data['Date']
        ).dt.days
        
        # 过滤有效数据（提前期 >= 0）
        valid_data = filtered_data[
            (filtered_data['Lead_Time'].notna()) & 
            (filtered_data['Lead_Time'] >= 0)
        ]
        
        if valid_data.empty:
            st.info("暂无有效时效性数据")
            return
        
        # 按成员统计平均提前期
        avg_lead = valid_data.groupby('Verifier')['Lead_Time'].mean().reset_index()
        avg_lead = avg_lead.sort_values('Lead_Time', ascending=False)
        
        # 绘制条形图
        fig = px.bar(
            avg_lead,
            x='Verifier',
            y='Lead_Time',
            text='Lead_Time',
            color='Lead_Time',
            color_continuous_scale='RdYlGn',
            title='成员平均提前发布天数'
        )
        fig.update_traces(texttemplate='%{text:.1f}', textposition='outside')
        fig.update_layout(
            xaxis_title='成员',
            yaxis_title='平均提前天数',
            showlegend=False,
            height=400
        )
        st.plotly_chart(fig, width='stretch')
        
        # 显示统计信息
        col1, col2 = st.columns(2)
        with col1:
            st.metric("平均提前天数", f"{valid_data['Lead_Time'].mean():.1f} 天")
        with col2:
            st.metric("最大提前天数", f"{valid_data['Lead_Time'].max():.0f} 天")


def display_country_distribution(filtered_data):
    """国家分布分析"""
    st.subheader("🌍 国家分布")
    
    if filtered_data.empty:
        st.info("暂无数据")
        return
    
    # 统计国家分布
    country_dist = filtered_data['Country_CN'].value_counts().reset_index()
    country_dist.columns = ['国家', '数量']
    country_dist = country_dist.head(10)  # 只显示前10
    
    # 绘制饼图
    fig = px.pie(
        country_dist,
        values='数量',
        names='国家',
        title='Top 10 国家分布'
    )
    fig.update_traces(textposition='inside', textinfo='percent+label')
    st.plotly_chart(fig, width='stretch')


def display_job_type_distribution(filtered_data):
    """职位类型分析"""
    st.subheader("💼 职位类型分布")
    
    if filtered_data.empty:
        st.info("暂无数据")
        return
    
    # 统计职位类型
    job_dist = filtered_data['Job_CN'].value_counts().reset_index()
    job_dist.columns = ['职位类型', '数量']
    
    # 绘制条形图
    fig = px.bar(
        job_dist,
        x='职位类型',
        y='数量',
        text='数量',
        color='数量',
        color_continuous_scale='Viridis'
    )
    fig.update_traces(textposition='outside')
    fig.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig, width='stretch')


def display_data_table(filtered_data):
    """显示原始数据表"""
    st.subheader("📋 原始数据")
    
    if filtered_data.empty:
        st.info("暂无数据")
        return
    
    # 选择要显示的列
    display_columns = [
        'Date', 'Verifier', 'University_CN', 'Country_CN', 
        'Job_CN', 'Direction', 'Extracted_Deadline'
    ]
    
    available_columns = [col for col in display_columns if col in filtered_data.columns]
    
    if available_columns:
        display_df = filtered_data[available_columns].copy()
        display_df['Date'] = display_df['Date'].dt.strftime('%Y-%m-%d')
        if 'Extracted_Deadline' in display_df.columns:
            display_df['Extracted_Deadline'] = pd.to_datetime(
                display_df['Extracted_Deadline'], errors='coerce'
            ).dt.strftime('%Y-%m-%d')
        
        st.dataframe(display_df, width='stretch', height=400)
        
        # 下载按钮
        csv = display_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 下载数据 (CSV)",
            data=csv,
            file_name=f"gisphere_performance_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )


# ==================== 主程序 ====================

def main():
    st.set_page_config(
        page_title="GISource 绩效面板",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 标题
    st.title("📊 GISource 团队绩效管理面板")
    st.markdown("---")
    
    # 侧边栏：控制面板
    with st.sidebar:
        st.header("⚙️ 筛选条件")
        
        # 时间范围选择
        days_options = {
            "最近 7 天": 7,
            "最近 14 天": 14,
            "最近 30 天": 30,
            "最近 60 天": 60,
            "最近 90 天": 90,
            "最近 180 天": 180,
            "最近 365 天": 365,
            "全部数据": 36500
        }
        
        selected_range = st.selectbox(
            "时间范围",
            options=list(days_options.keys()),
            index=2
        )
        days = days_options[selected_range]
        
        st.markdown("---")
        
        # 刷新按钮
        if st.button("🔄 刷新数据", width='stretch'):
            st.cache_resource.clear()
            st.rerun()
        
        st.markdown("---")
        st.info("💡 **提示**: 数据每次刷新时会从 Google Sheet 和 MySQL 数据库重新读取")
    
    # 加载和合并数据
    with st.spinner('正在加载数据...'):
        data = merge_data()
    
    if data.empty:
        st.error("❌ 无法加载数据，请检查 Google Sheet 和数据库连接")
        return
    
    # 根据时间范围筛选数据
    today = datetime.now(china_tz).date()
    start_date = today - timedelta(days=days)
    filtered_data = data[data['Date'].dt.date >= start_date]
    
    st.success(f"✅ 成功加载 {len(data)} 条数据，当前显示 {len(filtered_data)} 条数据")
    
    # 显示关键指标
    display_kpi_metrics(filtered_data)
    
    st.markdown("---")
    
    # 布局：两列
    col1, col2 = st.columns(2)
    
    with col1:
        display_member_leaderboard(filtered_data)
        st.markdown("---")
        display_country_distribution(filtered_data)
    
    with col2:
        display_lead_time_analysis(filtered_data)
        st.markdown("---")
        display_job_type_distribution(filtered_data)
    
    st.markdown("---")
    
    # 每日趋势（全宽）
    display_daily_trend(filtered_data)
    
    # 页脚
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: gray;'>"
        "GISource 团队绩效管理系统 | "
        f"最后更新: {datetime.now(china_tz).strftime('%Y-%m-%d %H:%M:%S')}"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()

