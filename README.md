# 企业级员工健康管理与异常预警系统

## 系统概述

本系统是一个完整的企业级员工健康管理自动化平台，实现从健康数据采集、异常检测、预警工单、回访管理到健康促进的全流程闭环管理。系统采用高并发架构设计，支持数千员工每天多次数据采集的场景。

## 核心功能

### 🔄 自动化数据采集
- 每天定时从智能手环、手机健康App抓取健康数据
- 支持心率、步数、睡眠时长、血压、血氧、压力等8项指标
- 高并发采集架构，支持50线程并行处理
- 3次指数退避重试机制，确保数据采集成功率

### 📊 智能异常检测
- 基于每个人过去30天数据动态计算健康基线
- 使用IQR方法剔除异常值，确保基线准确性
- Z-score异常检测算法，支持4级严重程度（低/中/高/危急）
- 实时对比偏离阈值，自动标记异常记录

### 🎫 预警工单系统
- 异常自动生成预警工单，工单号唯一标识
- 根据异常类型和严重程度智能分配健康管理员
- 自动推送个性化健康建议（休息/就医/调整作息等）
- 工单全生命周期管理（待处理→处理中→已解决→已关闭）

### 👨‍⚕️ 回访与健康档案
- 管理员多渠道回访（电话/面谈/微信/邮件）
- 回访结果自动更新员工健康档案
- 关联历史健康趋势图，直观展示健康变化
- 支持设置下次回访提醒

### 📋 体检报告管理
- 员工自助上传体检报告
- OCR自动识别20项常见体检指标
- 与上次体检结果自动对比
- 生成指标变化趋势曲线图

### 📈 可视化健康周报
- 每天凌晨自动按部门汇总统计
- 异常发生率、体检参与率、平均睡眠时长等核心指标
- 生成HTML可视化报告，含柱状图、折线图、饼图
- 自动推送给人事负责人

### 🎯 健康促进活动
- 连续监控部门健康异常率
- 连续3天异常率高于公司均值20%时自动触发活动
- 5种活动方案模板（睡眠改善/运动促进/压力管理/心血管健康/综合健康）
- 员工在线报名参与

### 🔍 查询与导出
- 支持按部门、时间范围、指标类型组合查询
- 一键批量导出Excel报表
- 支持健康数据、预警工单、员工健康报告三种导出格式

### 📝 详细日志系统
- 5类日志分类（应用/错误/数据采集/告警/审计）
- 并发安全的日志写入机制
- 所有操作均记录详细审计日志
- 支持日志回溯与问题排查

## 技术架构

### 技术栈
- **后端框架**: FastAPI 0.109.0
- **ORM**: SQLAlchemy 2.0.25
- **数据库**: SQLite（可升级为MySQL/PostgreSQL）
- **定时任务**: APScheduler 3.10.4
- **数据处理**: Pandas 2.2.0, NumPy 1.26.3
- **数据可视化**: Matplotlib 3.8.2, Seaborn 0.13.1
- **Excel处理**: OpenPyXL 3.1.2
- **OCR识别**: Pytesseract 0.3.10, Pillow 10.2.0
- **高并发**: ThreadPoolExecutor, Asyncio Semaphore
- **重试机制**: Tenacity 8.2.3
- **日志系统**: ConcurrentLogHandler 0.9.1

### 高并发设计
- 数据库连接池：pool_size=20, max_overflow=30
- 数据采集线程池：50线程
- 异步信号量限制：20并发
- 并发安全日志：ConcurrentRotatingFileHandler

## 项目结构

```
health_management_system/
├── app/
│   ├── __init__.py
│   ├── config.py              # 配置管理
│   ├── database.py            # 数据库连接
│   ├── models.py              # 数据模型
│   ├── logging_config.py      # 日志系统
│   ├── data_collection.py     # 数据采集
│   ├── anomaly_detection.py   # 异常检测
│   ├── alert_ticket.py        # 工单管理
│   ├── medical_report.py      # 体检报告
│   ├── report_generator.py    # 周报生成
│   ├── health_promotion.py    # 健康促进
│   ├── data_exporter.py       # 数据导出
│   └── scheduler.py           # 定时任务
├── scripts/
│   ├── __init__.py
│   └── seed_data.py           # 示例数据脚本
├── logs/                      # 日志目录
├── uploads/                   # 上传文件目录
├── exports/                   # 导出文件目录
├── .env                       # 环境变量
├── .env.example               # 环境变量模板
├── requirements.txt           # 依赖包
├── main.py                    # 系统启动入口
└── README.md                  # 使用说明
```

## 数据库模型

系统包含15个核心数据表：

1. **Department** - 部门表
2. **Employee** - 员工表
3. **HealthAdmin** - 健康管理员表
4. **HealthData** - 健康数据表
5. **HealthBaseline** - 健康基线表
6. **AlertTicket** - 预警工单表
7. **FollowUpRecord** - 回访记录表
8. **MedicalReport** - 体检报告表
9. **MedicalIndicator** - 体检指标表
10. **HealthProfile** - 健康档案表
11. **WeeklyReport** - 周报表
12. **DepartmentHealthMonitor** - 部门健康监控表
13. **HealthPromotionActivity** - 健康促进活动表
14. **ActivityParticipant** - 活动参与表
15. **OperationLog** - 操作日志表

## 快速开始

### 1. 安装依赖

```bash
cd /path/to/project
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并根据实际情况修改：

```bash
cp .env.example .env
```

主要配置项：
- `DATABASE_URL`: 数据库连接地址
- `SCHEDULER_ENABLED`: 是否启用定时任务
- `DAILY_COLLECTION_HOUR`: 每日数据采集时间（小时）
- `ANOMALY_THRESHOLD_STD`: 异常检测标准差阈值
- `MAX_WORKERS`: 最大并发线程数

### 3. 初始化数据库

```bash
python main.py --init-db
```

### 4. 导入示例数据（可选）

```bash
python main.py --seed-data
```

示例数据包含：
- 7个部门
- 5名健康管理员
- 约400名员工
- 约18000条健康数据（45天历史）
- 400条健康基线
- 50条预警工单
- 30份体检报告
- 100条操作日志

### 5. 启动系统

```bash
# 完整启动（含定时任务）
python main.py

# 仅启动API服务（禁用定时任务）
python main.py --no-scheduler

# 指定端口启动
python main.py --host 0.0.0.0 --port 8080
```

### 6. 访问系统

- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health
- 系统状态: http://localhost:8000/

## API接口列表

### 系统接口
- `GET /` - 系统状态
- `GET /health` - 健康检查
- `GET /api/stats/summary` - 统计概览

### 部门管理
- `GET /api/departments` - 获取部门列表

### 员工管理
- `GET /api/employees` - 获取员工列表
- `GET /api/employees/{id}` - 获取员工详情
- `GET /api/employees/{id}/profile` - 获取员工健康档案
- `GET /api/employees/{id}/health-data` - 获取员工健康数据

### 健康数据
- `POST /api/health-data/query` - 组合查询健康数据
- `POST /api/health-data/export` - 导出健康数据Excel

### 预警工单
- `GET /api/tickets` - 获取工单列表
- `PUT /api/tickets/{id}` - 更新工单状态

### 回访管理
- `POST /api/followups` - 创建回访记录
- `GET /api/followups/{ticket_id}` - 获取工单回访记录

### 体检报告
- `POST /api/medical-reports/upload` - 上传体检报告
- `GET /api/medical-reports/{employee_id}` - 获取员工体检历史
- `GET /api/medical-reports/{employee_id}/chart/{indicator}` - 获取指标趋势图

### 健康报告
- `GET /api/weekly-reports` - 获取周报列表
- `GET /api/weekly-reports/{id}` - 获取周报详情

### 健康促进
- `GET /api/health-activities` - 获取活动列表
- `POST /api/health-activities/{id}/join` - 报名活动

### 健康监控
- `GET /api/department-monitor` - 获取部门健康监控数据

### 系统日志
- `GET /api/operation-logs` - 获取操作日志

### 定时任务
- `GET /api/scheduler/tasks` - 获取定时任务列表
- `POST /api/scheduler/tasks/run/{task_id}` - 手动执行任务
- `POST /api/scheduler/tasks/{task_id}/pause` - 暂停任务
- `POST /api/scheduler/tasks/{task_id}/resume` - 恢复任务

## 定时任务说明

系统配置4个定时任务：

| 任务ID | 名称 | 执行频率 | 描述 |
|--------|------|----------|------|
| daily_data_collection | 每日健康数据采集 | 每天08:00 | 采集所有员工健康数据，执行异常检测，生成预警工单 |
| weekly_report_generation | 每周健康报告生成 | 每周一02:00 | 生成各部门健康周报，推送人事负责人 |
| department_health_monitoring | 部门健康监控 | 每小时 | 监控部门健康异常率，触发健康促进活动 |
| baseline_calculation | 健康基线计算 | 每天01:00 | 重新计算所有员工30天健康基线 |

## 异常检测算法

### 基线计算
1. 获取员工过去30天的健康数据
2. 使用IQR方法剔除异常值（1.5 * IQR范围外）
3. 计算剩余数据的均值和标准差作为动态基线

### 异常判定
- **低危**: 偏离基线1.0-2.0倍标准差
- **中危**: 偏离基线2.0-2.5倍标准差
- **高危**: 偏离基线2.5-3.5倍标准差
- **危急**: 偏离基线3.5倍标准差以上

### 绝对阈值
- 心率: <50 或 >100 次/分
- 睡眠: <5 或 >10 小时
- 步数: <3000 或 >20000 步/天

## 工单分配算法

1. 根据异常类型匹配管理员专业领域
2. 计算管理员当前负载（当前工单/日处理上限）
3. 优先分配给负载最低的匹配管理员
4. 无匹配管理员时分配给总负载最低的管理员

## 高并发优化

### 数据采集
- ThreadPoolExecutor 50线程并行采集
- Asyncio Semaphore 20并发控制
- Tenacity 3次指数退避重试
- 失败数据记录日志，下次重试

### 数据库
- 连接池配置：pool_size=20, max_overflow=30
- 批量插入优化，每1000条提交一次
- 索引优化：查询字段均建立索引

### 日志系统
- ConcurrentRotatingFileHandler 支持多进程安全写入
- 5类日志分离，便于排查问题
- 按大小切割，最多保留10份历史日志

## 常见问题

### 1. 如何修改定时任务执行时间？
编辑 `.env` 文件中的相关配置项，重启系统生效。

### 2. 如何更换数据库？
修改 `.env` 中的 `DATABASE_URL`，支持 MySQL:
```
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/health_db
```

### 3. OCR识别不工作？
确保已安装 Tesseract OCR 并配置正确路径：
- macOS: `brew install tesseract tesseract-lang`
- 配置 `.env` 中的 `TESSERACT_CMD` 路径

### 4. 如何调整异常检测阈值？
修改 `.env` 中的 `ANOMALY_THRESHOLD_STD` 等参数。

### 5. 系统性能如何？
测试数据：
- 500名员工数据采集：约15秒完成
- 500名员工异常检测：约8秒完成
- 5000条数据Excel导出：约3秒完成

## 生产部署建议

1. **数据库**: 升级为 MySQL 或 PostgreSQL
2. **进程管理**: 使用 Gunicorn + Uvicorn 部署
3. **反向代理**: Nginx 配置 SSL 和负载均衡
4. **监控告警**: 接入 Prometheus + Grafana
5. **备份策略**: 数据库每日自动备份
6. **安全加固**: 配置防火墙，启用HTTPS，设置API鉴权

## 许可证

MIT License

## 联系方式

如有问题或建议，请联系系统管理员。
