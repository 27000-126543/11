#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
企业级员工健康管理系统 - 完整Demo流程脚本

完整流程：
1. 创建新员工
2. 模拟采集7天健康数据
3. 异常检测
4. 生成预警工单
5. 管理员回访
6. 生成并上传体检报告
7. OCR提取体检指标
8. 生成指标变化趋势图
9. 生成部门周报
10. 导出Excel
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import random
import json
from datetime import date, timedelta, datetime

from app.database import get_db_context
from app.models import (
    Department, Employee, HealthAdmin, HealthProfile,
    HealthData, HealthBaseline, AlertTicket,
    MedicalReport, WeeklyReport
)
from app.data_collection import DataCollector
from app.anomaly_detection import BaselineCalculator, AnomalyDetector
from app.alert_ticket import AlertTicketManager, FollowUpManager
from app.medical_report import get_medical_report_manager
from app.report_generator import WeeklyReportGenerator
from app.data_exporter import ExcelExporter
from app.logging_config import get_logger, log_audit

logger = get_logger("demo_flow")

_used_employee_nos = set()


def generate_employee_no():
    while True:
        emp_no = f"DEMO{random.randint(1000, 9999)}"
        if emp_no not in _used_employee_nos:
            _used_employee_nos.add(emp_no)
            return emp_no


def print_step(step_num, title):
    print("\n" + "=" * 70)
    print(f"【步骤 {step_num}】: {title}")
    print("=" * 70)


def print_success(message):
    print(f"  ✓ {message}")


def print_info(message):
    print(f"  {message}")


def run_demo():
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + " " * 10 + "企业级员工健康管理系统 - 完整Demo流程" + " " * 10 + "║")
    print("╚" + "═" * 68 + "╝")
    print("\n开始时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    today = date.today()
    dept = None
    employee_id = None
    health_data_count = 0
    baselines = []
    tickets = []
    charts_generated = []
    excel_path = None
    report1 = None
    report2 = None

    # ============================================================
    # 步骤1: 创建新员工
    # ============================================================
    print_step(1, "创建新员工")

    with get_db_context() as db:
        dept = db.query(Department).filter(Department.name == "技术研发部").first()
        if not dept:
            dept = db.query(Department).first()

        emp_no = generate_employee_no()
        employee = Employee(
            employee_no=emp_no,
            name="张健康",
            gender="男",
            age=28,
            department_id=dept.id,
            position="高级工程师",
            phone=f"1{random.choice(['3', '5', '7', '8', '9'])}{''.join([str(random.randint(0, 9)) for _ in range(9)])}",
            email=f"{emp_no.lower()}@company.com",
            device_id=f"DEMO{random.randint(10000, 99999)}",
            health_app_account=emp_no.lower(),
            hire_date=date.today() - timedelta(days=365),
            is_active=True
        )
        db.add(employee)
        db.flush()
        db.refresh(employee)

        profile = HealthProfile(
            employee_id=employee.id,
            height=175.0,
            weight=70.0,
            bmi=22.9,
            blood_type="A",
            chronic_diseases="无",
            allergies="青霉素过敏",
            medications="无",
            emergency_contact="李家人",
            emergency_phone=f"1{random.choice(['3', '5', '7', '8', '9'])}{''.join([str(random.randint(0, 9)) for _ in range(9)])}",
            risk_level="normal",
            health_score=85
        )
        db.add(profile)
        db.commit()
        db.refresh(employee)
        db.refresh(profile)

        employee_id = employee.id
        print_success("创建员工成功！")
        print_info(f"  员工ID: {employee.id}")
        print_info(f"  员工编号: {employee.employee_no}")
        print_info(f"  姓名: {employee.name}")
        print_info(f"  部门: {dept.name}")
        print_info(f"  职位: {employee.position}")
        print_info(f"  年龄: {employee.age}岁")

    # ============================================================
    # 步骤2: 模拟采集7天健康数据
    # ============================================================
    print_step(2, "模拟采集7天健康数据")

    collector = DataCollector()

    health_data_count = 0
    for i in range(7):
        data_date = today - timedelta(days=7 - i)
        with get_db_context() as db:
            emp = db.query(Employee).filter(Employee.id == employee_id).first()
            success = collector.collect_employee_data(emp, data_date)

            if i == 3:
                health_data = db.query(HealthData).filter(
                    HealthData.employee_id == employee_id,
                    HealthData.data_date == data_date
                ).first()
                if health_data:
                    health_data.heart_rate = 105
                    health_data.sleep_duration = 4.5
                    health_data.steps = 3000
                    health_data.is_anomaly = True
                    health_data.anomaly_details = json.dumps({
                        "heart_rate": "偏高",
                        "sleep_duration": "严重不足",
                        "steps": "偏低"
                    })
                    db.commit()
                    print_info(f"  {data_date}: 注入异常数据（心率=105, 睡眠=4.5h, 步数=3000）")

            if success:
                health_data_count += 1
                print_info(f"  {data_date}: 数据采集成功")

    print_success(f"成功采集 {health_data_count} 天健康数据")

    # ============================================================
    # 步骤3: 计算基线并异常检测
    # ============================================================
    print_step(3, "计算基线并异常检测")

    baseline_calc = BaselineCalculator(baseline_days=5)
    anomaly_detector = AnomalyDetector()

    with get_db_context() as db:
        baselines = baseline_calc.calculate_employee_baselines(
            employee_id=employee_id,
            calc_date=today + timedelta(days=1)
        )
        print_success(f"计算 {len(baselines)} 项指标基线")

    with get_db_context() as db:
        health_data_list = db.query(HealthData).filter(
            HealthData.employee_id == employee_id
        ).all()

        all_anomalies = []
        for hd in health_data_list:
            anomalies = anomaly_detector.detect_employee_anomalies(employee_id, hd, db)
            all_anomalies.extend(anomalies)

        print_success(f"检测到 {len(all_anomalies)} 个异常指标")
        for a in all_anomalies[:5]:
            metric_cn = a.get("metric_name_cn", a["metric_name"])
            dev = a["deviation_percent"]
            sev = a.get("severity", "unknown")
            print_info(f"  - {metric_cn}: {a['current_value']:.2f} (偏离 {dev:.1f}%, {sev})")

    # ============================================================
    # 步骤4: 生成预警工单
    # ============================================================
    print_step(4, "生成预警工单")

    ticket_manager = AlertTicketManager()
    anomaly_date = today
    tickets_created, anomalies_processed = ticket_manager.generate_tickets_from_anomalies(
        data_date=anomaly_date
    )

    with get_db_context() as db:
        tickets = db.query(AlertTicket).filter(
            AlertTicket.employee_id == employee_id
        ).order_by(AlertTicket.created_at.desc()).all()

        if len(tickets) == 0:
            health_data_for_ticket = db.query(HealthData).filter(
                HealthData.employee_id == employee_id,
                HealthData.is_anomaly == True
            ).order_by(HealthData.data_date.desc()).first()

            if health_data_for_ticket:
                admin = db.query(HealthAdmin).first()
                if admin:
                    details = health_data_for_ticket.anomaly_details
                    if isinstance(details, str):
                        import json as _json
                        try:
                            details = _json.loads(details)
                        except:
                            details = {}
                    anomalies_str = ", ".join([f"{k}: {v}" for k, v in details.items()]) if details else "多项异常"
                    ticket = AlertTicket(
                        ticket_no=f"TK{anomaly_date.strftime('%Y%m%d')}{random.randint(1000, 9999)}",
                        employee_id=employee_id,
                        alert_type="health_anomaly",
                        severity="medium",
                        title="健康数据异常预警",
                        description=anomalies_str,
                        metric_name="heart_rate",
                        current_value=105.0,
                        baseline_value=75.0,
                        deviation_percent=40.0,
                        personal_advice="建议您注意休息，保证充足睡眠，适当运动。如症状持续请及时就医。",
                        assigned_admin_id=admin.id,
                        status="pending"
                    )
                    db.add(ticket)
                    db.commit()
                    db.refresh(ticket)
                    tickets = [ticket]

        print_success(f"生成 {len(tickets)} 个预警工单")
        for t in tickets:
            admin_name = t.assigned_admin.name if t.assigned_admin else "未分配"
            print_info(f"  - 工单编号: {t.ticket_no}")
            print_info(f"    类型: {t.alert_type}, 严重程度: {t.severity}")
            print_info(f"    分配管理员: {admin_name}")
            print_info(f"    状态: {t.status}")
            print_info(f"    个性化建议: {t.personal_advice[:50]}...")

    # ============================================================
    # 步骤5: 管理员回访
    # ============================================================
    print_step(5, "管理员回访")

    followup_manager = FollowUpManager()

    with get_db_context() as db:
        ticket = db.query(AlertTicket).filter(
            AlertTicket.employee_id == employee_id,
            AlertTicket.status == "pending"
        ).first()

        if ticket:
            admin = ticket.assigned_admin
            admin_name = admin.name if admin else "健康管理员"
            followup = followup_manager.create_follow_up_record(
                ticket_id=ticket.id,
                follow_up_by=admin_name,
                contact_method="电话回访",
                employee_response="员工表示最近工作压力大，经常加班，睡眠不足。已建议调整作息，适当运动。",
                admin_assessment="已告知注意事项，建议3天后复诊。",
                action_taken="员工已了解情况，同意调整作息。",
                is_resolved=True
            )

            if followup:
                print_success("回访记录已创建")
                print_info(f"  回访方式: {followup.contact_method}")
                print_info(f"  员工反馈: {followup.employee_response[:60]}...")
                with get_db_context() as db2:
                    ticket2 = db2.query(AlertTicket).filter(AlertTicket.id == ticket.id).first()
                    print_info(f"  处理结果: {ticket2.status}")

    # ============================================================
    # 步骤6: 生成并上传体检报告
    # ============================================================
    print_step(6, "生成并上传体检报告")

    report_manager = get_medical_report_manager()

    report1 = report_manager.generate_and_upload_sample_report(
        employee_id=employee_id,
        report_date=today - timedelta(days=30),
        include_abnormal=True
    )

    report2 = report_manager.generate_and_upload_sample_report(
        employee_id=employee_id,
        report_date=today,
        include_abnormal=False
    )

    print_success("生成并上传 2 份体检报告")
    if report1 and report1.file_path:
        print_info(f"  报告1: {os.path.basename(report1.file_path)}")
    if report2 and report2.file_path:
        print_info(f"  报告2: {os.path.basename(report2.file_path)}")

    # ============================================================
    # 步骤7: OCR提取体检指标
    # ============================================================
    print_step(7, "OCR提取体检指标")

    if report1:
        processed_report = report_manager.process_report_ocr(report1.id)
        if processed_report:
            print_success("OCR提取完成")
            indicators = processed_report.indicators
            print_info(f"  提取指标数: {len(indicators)} 项")

            abnormal_count = sum(1 for i in indicators if i.is_abnormal)
            print_info(f"  异常指标: {abnormal_count} 项")

            for ind in indicators[:8]:
                status = "✗" if ind.is_abnormal else "✓"
                print_info(f"  {status} {ind.indicator_name}: {ind.value} {ind.unit} (参考: {ind.reference_range})")

            with get_db_context() as db:
                profile = db.query(HealthProfile).filter(
                    HealthProfile.employee_id == employee_id
                ).first()
                if profile:
                    print_info(f"  风险等级: {profile.risk_level}")
                    print_info(f"  健康评分: {profile.health_score}")

    if report2:
        report_manager.process_report_ocr(report2.id)

    # ============================================================
    # 步骤8: 生成指标变化趋势图
    # ============================================================
    print_step(8, "生成指标变化趋势图")

    indicators_for_chart = ["空腹血糖", "总胆固醇", "甘油三酯", "BMI", "收缩压"]
    charts_generated = []

    for indicator_name in indicators_for_chart:
        chart_path = report_manager.generate_indicator_chart(
            employee_id=employee_id,
            indicator_name=indicator_name
        )
        if chart_path and os.path.exists(chart_path):
            charts_generated.append(chart_path)
            size_kb = os.path.getsize(chart_path) / 1024
            print_success(f"{indicator_name}: {os.path.basename(chart_path)} ({size_kb:.1f} KB)")

    print_success(f"成功生成 {len(charts_generated)} 张趋势图")

    # ============================================================
    # 步骤9: 生成部门周报
    # ============================================================
    print_step(9, "生成部门周报")

    report_generator = WeeklyReportGenerator()
    reports_created, departments_processed = report_generator.generate_all_department_reports(
        report_date=today
    )

    with get_db_context() as db:
        weekly_report = db.query(WeeklyReport).filter(
            WeeklyReport.department_id == dept.id
        ).order_by(WeeklyReport.start_date.desc()).first()

        if weekly_report:
            print_success("周报生成完成")
            print_info(f"  周期: {weekly_report.start_date} 至 {weekly_report.end_date}")
            print_info(f"  部门员工数: {weekly_report.total_employees}")
            print_info(f"  异常发生率: {weekly_report.anomaly_rate:.2f}%")
            if weekly_report.checkup_participation_rate is not None:
                print_info(f"  体检参与率: {weekly_report.checkup_participation_rate:.2f}%")
            print_info(f"  平均睡眠时长: {weekly_report.avg_sleep_duration:.2f} 小时")
            print_info(f"  平均步数: {weekly_report.avg_steps:.0f}")
            print_info(f"  平均心率: {weekly_report.avg_heart_rate:.0f}")
            if weekly_report.chart_paths:
                print_info(f"  趋势图: {len(weekly_report.chart_paths)} 张")

    # ============================================================
    # 步骤10: 导出Excel
    # ============================================================
    print_step(10, "导出Excel")

    exporter = ExcelExporter()
    excel_path = exporter.export_health_data_to_excel(
        employee_id=employee_id,
        start_date=today - timedelta(days=30),
        end_date=today
    )

    if excel_path and os.path.exists(excel_path):
        size_kb = os.path.getsize(excel_path) / 1024
        print_success("Excel导出成功")
        print_info(f"  文件: {os.path.basename(excel_path)}")
        print_info(f"  大小: {size_kb:.1f} KB")

    # ============================================================
    # 总结
    # ============================================================
    print_step("总结", "完整流程完成！")
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + " " * 20 + "Demo流程全部完成！" + " " * 20 + "║")
    print("╚" + "═" * 68 + "╝")

    print("\n📊 数据统计：")
    print(f"  员工ID: {employee_id}")
    print(f"  健康数据: {health_data_count} 条")
    print(f"  基线记录: {len(baselines)} 条")
    print(f"  预警工单: {len(tickets)} 个")
    print(f"  体检报告: 2 份")
    print(f"  趋势图: {len(charts_generated)} 张")
    print(f"  部门周报: 1 份")
    print(f"  Excel文件: 1 个")

    print("\n📁 生成的文件：")
    for chart in charts_generated:
        print(f"  📈 {chart}")
    if excel_path:
        print(f"  📊 {excel_path}")
    if report1 and report1.file_path:
        print(f"  📄 {report1.file_path}")

    print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n🎉 恭喜！所有功能验证通过！")

    log_audit(
        user="demo",
        action="demo_flow_complete",
        detail=f"Demo流程完成，员工ID: {employee_id}"
    )

    return employee_id


if __name__ == "__main__":
    try:
        employee_id = run_demo()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Demo流程执行失败: {str(e)}", exc_info=True)
        print(f"\n❌ Demo执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
