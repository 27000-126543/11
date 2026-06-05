import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import date, timedelta

from app.database import get_db_context
from app.data_collection import DataCollector
from app.anomaly_detection import BaselineCalculator, AnomalyDetector
from app.alert_ticket import AlertTicketManager
from app.models import Employee, HealthData

print("=" * 60)
print("测试核心流程")
print("=" * 60)

print("\n[测试1] 数据采集模块")
collector = DataCollector()
test_date = date.today() - timedelta(days=1)
with get_db_context() as db:
    employee = db.query(Employee).filter(Employee.id == 1).first()
    if employee:
        result = collector.collect_employee_data(employee, test_date)
        status = "成功" if result else "失败"
        print(f"  员工{employee.name}: {status}")

print("\n[测试2] 基线计算模块")
calculator = BaselineCalculator(baseline_days=30)
baselines = calculator.calculate_employee_baselines(employee_id=1, calc_date=date.today())
print(f"  生成 {len(baselines)} 条基线记录")
for b in baselines[:3]:
    print(f"    {b.metric_name}: 基线={b.baseline_value:.2f}, 标准差={b.std_dev:.2f}")

print("\n[测试3] 异常检测模块")
detector = AnomalyDetector()
with get_db_context() as db:
    health_data_list = db.query(HealthData).filter(
        HealthData.employee_id == 1,
        HealthData.data_date == test_date
    ).all()
    all_anomalies = []
    for hd in health_data_list:
        anomalies = detector.detect_employee_anomalies(1, hd, db)
        all_anomalies.extend(anomalies)
    print(f"  检测 {len(health_data_list)} 条数据, 发现 {len(all_anomalies)} 个异常")
    for a in all_anomalies[:3]:
        metric_cn = a.get("metric_name_cn", a["metric_name"])
        dev = a["deviation_percent"]
        sev = a.get("severity", "unknown")
        print(f"    {metric_cn}: 偏离={dev:.1f}%, 严重={sev}")

print("\n[测试4] 工单生成模块")
manager = AlertTicketManager()
tickets_created, anomalies_processed = manager.generate_tickets_from_anomalies(data_date=test_date)
print(f"  处理 {anomalies_processed} 个异常, 生成 {tickets_created} 个工单")

print("\n" + "=" * 60)
print("✓ 所有核心流程测试完成!")
print("=" * 60)
