import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import date, timedelta

from app.database import get_db_context
from app.data_collection import DataCollector
from app.anomaly_detection import BaselineCalculator, AnomalyDetector
from app.alert_ticket import AlertTicketManager
from app.models import Employee
from app.logging_config import get_logger

logger = get_logger("test_core_flow")

def test_data_collection():
    logger.info("=" * 60)
    logger.info("测试1: 数据采集模块")
    logger.info("=" * 60)
    
    collector = DataCollector()
    test_date = date.today() - timedelta(days=1)
    
    with get_db_context() as db:
        employee = db.query(Employee).filter(Employee.id == 1).first()
        if employee:
            result = collector.collect_employee_data(employee, test_date)
            logger.info(f"采集员工{employee.id}({employee.name})数据: {'成功' if result else '失败'}")
            logger.info(f"采集日期: {test_date}")
        else:
            logger.error("找不到员工1")
    
    logger.info("")

def test_baseline_calculation():
    logger.info("=" * 60)
    logger.info("测试2: 基线计算模块")
    logger.info("=" * 60)
    
    calculator = BaselineCalculator(baseline_days=30)
    calc_date = date.today()
    
    baselines = calculator.calculate_employee_baselines(employee_id=1, calc_date=calc_date)
    logger.info(f"计算员工1基线 (基于过去30天): 生成 {len(baselines)} 条基线记录")
    for b in baselines[:5]:
        logger.info(f"  {b.metric_name}: 基线值={b.baseline_value:.2f}, 标准差={b.std_dev:.2f}, "
                   f"第25百分位={b.percentile_25:.2f}, 第75百分位={b.percentile_75:.2f}, "
                   f"数据量={b.data_count}")
    
    logger.info("")

def test_anomaly_detection():
    logger.info("=" * 60)
    logger.info("测试3: 异常检测模块")
    logger.info("=" * 60)
    
    detector = AnomalyDetector()
    detect_date = date.today() - timedelta(days=1)
    
    with get_db_context() as db:
        from app.models import HealthData
        health_data_list = db.query(HealthData)\
            .filter(HealthData.employee_id == 1)\
            .filter(HealthData.data_date == detect_date)\
            .all()
        
        all_anomalies = []
        for hd in health_data_list:
            anomalies = detector.detect_employee_anomalies(1, hd, db)
            all_anomalies.extend(anomalies)
        
        logger.info(f"检测员工1异常 (日期: {detect_date}): 检测 {len(health_data_list)} 条数据, 发现 {len(all_anomalies)} 个异常")
        for a in all_anomalies[:5]:
            logger.info(f"  {a.get('metric_name_cn', a['metric_name'])}: "
                       f"当前值={a['current_value']:.2f}, "
                       f"基线={a['baseline_value']:.2f}, "
                       f"偏离={a['deviation_percent']:.1f}%, "
                       f"严重程度={a.get('severity', 'unknown')}")
    
    logger.info("")

def test_ticket_generation():
    logger.info("=" * 60)
    logger.info("测试4: 工单生成模块")
    logger.info("=" * 60)
    
    manager = AlertTicketManager()
    test_date = date.today() - timedelta(days=1)
    
    tickets_created, anomalies_processed = manager.generate_tickets_from_anomalies(
        data_date=test_date
    )
    logger.info(f"生成工单 (日期: {test_date}): 处理 {anomalies_processed} 个异常, 生成 {tickets_created} 个工单")
    
    with get_db_context() as db:
        from app.models import AlertTicket
        recent_tickets = db.query(AlertTicket)\
            .filter(AlertTicket.created_at >= test_date)\
            .order_by(AlertTicket.created_at.desc())\
            .limit(3)\
            .all()
        
        for t in recent_tickets:
            admin_name = t.assigned_admin.name if t.assigned_admin else "未分配"
            logger.info(f"  工单编号: {t.ticket_no}")
            logger.info(f"    员工: {t.employee.name}, 类型: {t.alert_type}")
            logger.info(f"    严重程度: {t.severity}, 状态: {t.status}")
            logger.info(f"    分配管理员: {admin_name}")
            logger.info(f"    个性化建议: {t.personal_advice[:60]}...")
    
    logger.info("")

def run_all_tests():
    logger.info("")
    logger.info("╔" + "═" * 58 + "╗")
    logger.info("║" + " " * 15 + "企业级员工健康管理系统核心流程测试" + " " * 15 + "║")
    logger.info("╚" + "═" * 58 + "╝")
    logger.info("")
    
    try:
        test_data_collection()
        test_baseline_calculation()
        test_anomaly_detection()
        test_ticket_generation()
        
        logger.info("=" * 60)
        logger.info("✓ 所有测试完成！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    run_all_tests()
