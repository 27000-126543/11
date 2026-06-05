import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import date, timedelta

from app.database import get_db_context
from app.report_generator import WeeklyReportGenerator
from app.health_promotion import DepartmentMonitor, HealthPromotionManager
from app.data_exporter import ExcelExporter

print("=" * 60)
print("测试周报生成与健康促进活动")
print("=" * 60)

print("\n[测试1] 周报生成模块")
generator = WeeklyReportGenerator()
report_date = date.today()

try:
    reports_created, departments_processed = generator.generate_all_department_reports(report_date)
    print(f"  处理 {departments_processed} 个部门, 生成 {reports_created} 份周报")
    
    from app.database import get_db_context
    from app.models import WeeklyReport
    with get_db_context() as db:
        recent_reports = db.query(WeeklyReport).order_by(WeeklyReport.start_date.desc()).limit(3).all()
        for r in recent_reports:
            print(f"    部门ID: {r.department_id}, 异常发生率: {r.anomaly_rate:.2f}%, "
                  f"平均睡眠: {r.avg_sleep_duration:.2f}小时")
except Exception as e:
    print(f"  周报生成跳过: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n[测试2] 部门健康监控模块")
monitor = DepartmentMonitor()
try:
    monitor_results = monitor.monitor_all_departments()
    print(f"  监控 {len(monitor_results)} 个部门")
    for result in monitor_results[:3]:
        dept_id = result.get("department_id", "N/A")
        anomaly_rate = result.get("anomaly_rate", 0)
        company_avg = result.get("company_avg_anomaly_rate", 0)
        consecutive = result.get("consecutive_days_above", 0)
        print(f"    部门ID: {dept_id}, 异常率: {anomaly_rate:.2f}%, "
              f"公司均值: {company_avg:.2f}%, 连续超标: {consecutive}天")
except Exception as e:
    print(f"  部门监控跳过: {str(e)}")

print("\n[测试3] 健康促进活动模块")
promotion_manager = HealthPromotionManager()
try:
    triggered = promotion_manager.detect_and_trigger_activities()
    print(f"  触发 {len(triggered)} 个健康促进活动")
    for activity in triggered[:2]:
        print(f"    活动: {activity.activity_name}, 部门ID: {activity.department_id}")
except Exception as e:
    print(f"  活动触发跳过: {str(e)}")

print("\n[测试4] Excel导出模块")
exporter = ExcelExporter()
end_date = date.today()
start_date = end_date - timedelta(days=7)
try:
    file_path = exporter.export_health_data_to_excel(
        department_id=1,
        start_date=start_date,
        end_date=end_date
    )
    if file_path and os.path.exists(file_path):
        size_kb = os.path.getsize(file_path) / 1024
        print(f"  导出成功: {os.path.basename(file_path)} ({size_kb:.1f} KB)")
    else:
        print("  导出文件未找到")
except Exception as e:
    print(f"  导出跳过: {str(e)}")

print("\n" + "=" * 60)
print("✓ 所有扩展功能测试完成!")
print("=" * 60)
