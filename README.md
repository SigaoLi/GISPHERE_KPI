# GISphere 团队绩效管理面板

这是一个基于 Streamlit 构建的团队绩效管理系统，用于可视化展示 GISphere 团队的工作绩效数据。

## 功能特点

- 📊 **关键指标展示**: 入库总数、活跃成员数、平均提前天数、本周新增
- 🏆 **成员贡献排行**: 直观展示每位成员的贡献量
- 📈 **每日工作趋势**: 追踪团队和个人的每日工作情况
- ⏳ **信息时效性分析**: 分析信息发布的提前期
- 🌍 **国家分布**: 展示信息来源的地理分布
- 💼 **职位类型分布**: 统计不同类型的职位信息
- 📋 **数据导出**: 支持将筛选后的数据导出为 CSV 格式

## 文件结构

```
GISphere_Dashboard/
│
├── Dashboard.py            # 主程序（核心代码）
├── requirements.txt        # 依赖库列表
├── credentials.json        # 谷歌 API 密钥（需要准备）
├── token.pickle            # 谷歌 Token（自动生成）
├── sql_credentials.txt     # 数据库账号密码（需要准备）
├── README.md               # 使用说明
└── Coding.ipynb            # 原始数据处理脚本（参考）
```

## 安装步骤

### 1. 环境准备

确保你的系统已安装 Python 3.8 或更高版本。

### 2. 安装依赖

在项目文件夹下运行：

```bash
pip install -r requirements.txt
```

### 3. 配置文件准备

#### credentials.json
从 Google Cloud Console 下载的 API 密钥文件，用于访问 Google Sheets。

#### sql_credentials.txt
数据库连接配置文件，格式如下：

```ini
[MySQL]
host = your_host
port = 3306
user = your_username
password = your_password
database = your_database
```

## 运行方式

在项目文件夹下运行以下命令：

```bash
streamlit run Dashboard.py
```

系统会自动：
1. 启动本地服务器（默认端口 8501）
2. 在默认浏览器中打开可视化面板
3. 显示地址：http://localhost:8501

## 数据处理逻辑

### 数据源

1. **左侧数据（Google Sheet - "Filled" 表）**:
   - Verifier（核验人）
   - Source（信息来源 URL）
   - Deadline（申请截止日期）
   - Direction（研究方向）
   - University_CN（学校中文名）

2. **右侧数据（MySQL - GISource 表）**:
   - Date（入库时间）
   - Description（HTML 格式描述，包含 URL 和 Deadline）
   - University_CN（学校中文名）
   - Country_CN（国家中文名）
   - Job_CN（职位类型中文）

### 匹配逻辑

1. **复合键（Composite Key）**: URL + Deadline
   - 从 MySQL 的 Description 字段中使用正则表达式提取 URL 和 Deadline
   - 从 Google Sheet 中直接读取 Source 和 Deadline
   - 将两者拼接成统一的复合键

2. **数据合并**:
   - 使用复合键进行 INNER JOIN
   - 只有两边都匹配的记录才被认为是"成功入库"
   - 合并后包含：Verifier（人）、Date（入库时间）、Source、Deadline

3. **时效性计算**:
   - Lead Time = Deadline - 入库时间（Date）
   - 提前量越多，信息时效性越好

### 正则表达式

```python
# 提取 URL
url_pattern = r"URL:\s*(https?://[^\s<]+)"

# 提取 Deadline
date_pattern = r"Deadline:\s*(\d{4}-\d{2}-\d{2})"
```

## 使用说明

### 侧边栏功能

- **时间范围选择**: 可选择查看最近 7/14/30/60/90/180 天的数据，或查看全部数据
- **刷新数据**: 点击按钮重新从 Google Sheet 和 MySQL 读取最新数据

### 主面板功能

1. **关键指标区**:
   - 实时显示当前筛选条件下的关键数据

2. **成员贡献排行**:
   - 条形图展示每位成员的入库数量
   - 可展开查看详细数据表

3. **信息时效性分析**:
   - 展示每位成员的平均提前发布天数
   - 颜色越绿表示时效性越好

4. **国家分布**:
   - 饼图展示 Top 10 国家的信息分布

5. **职位类型分布**:
   - 条形图展示不同职位类型的数量分布

6. **每日工作趋势**:
   - 折线图展示每位成员的每日工作量变化

7. **原始数据表**:
   - 展示筛选后的详细数据
   - 支持导出为 CSV 格式

## 数据筛选规则

系统会自动过滤以下数据：
- Verifier 为空的记录
- Verifier 为 "LLM" 的记录
- IS_Deleted = 1 的记录（已删除）

## 技术栈

- **前端框架**: Streamlit
- **数据处理**: Pandas
- **数据可视化**: Plotly
- **数据库**: MySQL
- **API**: Google Sheets API v4

## 常见问题

### Q: 首次运行时提示需要授权怎么办？
A: 首次运行会打开浏览器要求登录 Google 账号并授权访问 Google Sheets。授权后会自动生成 token.pickle 文件。

### Q: 如果 token 过期怎么办？
A: 删除 token.pickle 文件，重新运行程序，系统会自动重新授权。

### Q: 数据不刷新怎么办？
A: 点击侧边栏的"刷新数据"按钮，或重启 Dashboard 程序。

### Q: 如何在后台运行？
A: Windows 可以使用任务计划程序，macOS/Linux 可以使用 nohup 或 screen：
```bash
nohup streamlit run Dashboard.py &
```

### Q: 如何修改端口？
A: 使用 --server.port 参数：
```bash
streamlit run Dashboard.py --server.port 8080
```

## 跨平台兼容性

本系统完全使用 Python 编写，兼容以下平台：
- ✅ Windows 10/11
- ✅ macOS (Intel & Apple Silicon)
- ✅ Linux (Ubuntu, CentOS, etc.)

无需 .bat 或 .sh 脚本，保持纯 Python 环境即可实现跨平台运行。

## 维护与更新

- 定期检查依赖库更新：`pip list --outdated`
- 升级依赖库：`pip install --upgrade -r requirements.txt`
- 备份 credentials.json 和 sql_credentials.txt 文件

## 联系方式

如有问题或建议，请联系 GISphere 团队。

---

**最后更新**: 2025-11-26

