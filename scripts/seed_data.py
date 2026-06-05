import sys
import os
from datetime import datetime, timedelta, date
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db_context
from app.models import (
    Department, Employee, HealthAdmin, HealthData, HealthBaseline,
    AlertTicket, FollowUpRecord, MedicalReport, MedicalIndicator,
    HealthProfile, OperationLog
)
from app.config import get_settings

settings = get_settings()

DEPARTMENTS = [
    ("技术研发部", "负责产品研发和技术支持"),
    ("产品设计部", "负责产品设计和用户体验"),
    ("市场销售部", "负责市场推广和销售业务"),
    ("人力资源部", "负责招聘、培训和员工关系"),
    ("财务部", "负责财务核算和资金管理"),
    ("行政后勤部", "负责行政事务和后勤保障"),
    ("客户服务部", "负责客户服务和技术支持"),
]

FIRST_NAMES = ["张", "李", "王", "刘", "陈", "杨", "黄", "赵", "周", "吴", "徐", "孙", "马", "朱", "胡"]
LAST_NAMES = ["伟", "芳", "娜", "敏", "静", "强", "磊", "军", "洋", "勇", "艳", "杰", "娟", "涛", "明"]

ADMIN_NAMES = ["王健康", "李医生", "张护士", "刘顾问", "陈医师"]
ADMIN_SPECIALTIES = ["心血管健康", "睡眠管理", "运动健康", "心理健康", "营养咨询"]


_used_employee_nos = set()
_used_ticket_nos = set()

def generate_employee_no():
    while True:
        emp_no = f"EMP{random.randint(10000, 99999)}"
        if emp_no not in _used_employee_nos:
            _used_employee_nos.add(emp_no)
            return emp_no

def generate_ticket_no():
    while True:
        ticket_no = f"HLT{datetime.now().strftime('%Y%m%d')}{random.randint(1000, 9999)}"
        if ticket_no not in _used_ticket_nos:
            _used_ticket_nos.add(ticket_no)
            return ticket_no


def generate_phone():
    return f"1{random.choice(['3', '5', '7', '8', '9'])}{''.join([str(random.randint(0, 9)) for _ in range(9)])}"


def generate_email(emp_no):
    return f"{emp_no.lower()}@company.com"


def seed_departments(db):
    print("正在创建部门数据...")
    departments = []
    for name, description in DEPARTMENTS:
        dept = Department(
            name=name,
            description=description
        )
        departments.append(dept)
        db.add(dept)
    db.flush()
    print(f"已创建 {len(departments)} 个部门")
    return departments


def seed_employees(db, departments):
    print("正在创建员工数据...")
    employees = []
    for dept in departments:
        emp_count = random.randint(30, 80)
        for _ in range(emp_count):
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            full_name = first_name + last_name
            emp_no = generate_employee_no()
            employee = Employee(
                employee_no=emp_no,
                name=full_name,
                gender=random.choice(["男", "女"]),
                age=random.randint(22, 55),
                phone=generate_phone(),
                email=generate_email(emp_no),
                department_id=dept.id,
                position=random.choice(["工程师", "经理", "主管", "专员", "分析师", "设计师"]),
                hire_date=datetime.now() - timedelta(days=random.randint(30, 3650)),
                is_active=True,
                device_id=f"DEV{random.randint(100000, 999999)}",
                health_app_account=emp_no.lower()
            )
            employees.append(employee)
            db.add(employee)
    db.flush()
    print(f"已创建 {len(employees)} 名员工")
    return employees


def seed_health_admins(db, employees):
    print("正在创建健康管理员数据...")
    admins = []
    for i, (name, specialty) in enumerate(zip(ADMIN_NAMES, ADMIN_SPECIALTIES)):
        emp = employees[i] if i < len(employees) else None
        admin = HealthAdmin(
            name=name,
            employee_id=emp.id if emp else None,
            specialty=specialty,
            severity_level=random.randint(1, 3),
            phone=generate_phone(),
            email=f"admin{i + 1}@company.com",
            is_active=True
        )
        admins.append(admin)
        db.add(admin)
    db.flush()
    print(f"已创建 {len(admins)} 名健康管理员")
    return admins


def seed_health_data(db, employees, days=45):
    print("正在创建健康数据...")
    health_data_list = []
    today = date.today()

    for employee in employees:
        base_heart_rate = random.randint(60, 85)
        base_steps = random.randint(6000, 10000)
        base_sleep = random.uniform(6.0, 8.0)
        base_calories = random.randint(1800, 2500)
        base_spo2 = random.randint(95, 99)
        base_stress = random.randint(20, 50)

        for day_offset in range(days, 0, -1):
            data_date = today - timedelta(days=day_offset)
            if random.random() < 0.95:
                heart_rate = base_heart_rate + random.randint(-10, 15)
                if random.random() < 0.05:
                    heart_rate += random.randint(20, 40)

                steps = max(0, base_steps + random.randint(-3000, 5000))
                if random.random() < 0.1:
                    steps = max(0, steps - 5000)

                sleep_duration = max(3.0, min(12.0, base_sleep + random.uniform(-2.0, 1.5)))
                if random.random() < 0.08:
                    sleep_duration = max(3.0, sleep_duration - 3.0)

                calories_burned = max(1000, base_calories + random.randint(-300, 500))
                blood_oxygen = min(100, max(90, base_spo2 + random.randint(-3, 2)))
                stress_level = min(100, max(0, base_stress + random.randint(-15, 20)))

                health_data = HealthData(
                    employee_id=employee.id,
                    data_date=data_date,
                    record_time=datetime.combine(data_date, datetime.min.time()) + timedelta(hours=random.randint(6, 23)),
                    data_source=random.choice(["智能手环", "手机健康App", "智能手表"]),
                    heart_rate=heart_rate,
                    heart_rate_resting=max(40, heart_rate - random.randint(5, 15)),
                    heart_rate_variability=random.uniform(20, 60),
                    steps=steps,
                    distance=round(steps * 0.0007, 2),
                    calories_burned=calories_burned,
                    sleep_duration=sleep_duration,
                    deep_sleep=sleep_duration * random.uniform(0.15, 0.35),
                    light_sleep=sleep_duration * random.uniform(0.40, 0.60),
                    rem_sleep=sleep_duration * random.uniform(0.10, 0.25),
                    sleep_awake_time=sleep_duration * random.uniform(0.05, 0.15),
                    sleep_score=random.randint(60, 95),
                    blood_oxygen=blood_oxygen,
                    stress_level=stress_level,
                    systolic_bp=random.randint(110, 140),
                    diastolic_bp=random.randint(70, 90),
                    is_anomaly=False,
                    processed=True
                )
                health_data_list.append(health_data)
                db.add(health_data)

        if len(health_data_list) >= 1000:
            db.flush()
            health_data_list = []

    db.flush()
    total = db.query(HealthData).count()
    print(f"已创建 {total} 条健康数据")


def seed_health_baselines(db, employees):
    print("正在创建健康基线数据...")
    baselines = []
    metrics = [
        ("heart_rate", 65, 80, 5, 12),
        ("heart_rate_resting", 55, 70, 3, 8),
        ("steps", 6000, 9000, 1000, 2500),
        ("sleep_duration", 6.5, 8.0, 0.5, 1.5),
        ("calories_burned", 1800, 2400, 200, 400),
        ("blood_oxygen", 96, 98, 0.5, 1.5),
        ("stress_level", 25, 45, 5, 15),
    ]

    for employee in employees:
        for metric_name, min_val, max_val, std_min, std_max in metrics:
            baseline = HealthBaseline(
                employee_id=employee.id,
                metric_name=metric_name,
                baseline_value=random.uniform(min_val, max_val),
                std_dev=random.uniform(std_min, std_max),
                min_value=random.uniform(min_val - std_max * 2, min_val),
                max_value=random.uniform(max_val, max_val + std_max * 2),
                percentile_25=random.uniform(min_val, (min_val + max_val) / 2),
                percentile_50=random.uniform(min_val, max_val),
                percentile_75=random.uniform((min_val + max_val) / 2, max_val),
                data_count=random.randint(25, 30),
                calculation_date=date.today(),
                baseline_days=30
            )
            baselines.append(baseline)
            db.add(baseline)

    db.flush()
    print(f"已创建 {len(baselines)} 条健康基线数据")


def seed_health_profiles(db, employees):
    print("正在创建健康档案...")
    profiles = []
    for employee in employees:
        height = random.uniform(155, 185)
        weight = random.uniform(45, 90)
        bmi = round(weight / ((height / 100) ** 2), 1)

        profile = HealthProfile(
            employee_id=employee.id,
            blood_type=random.choice(["A", "B", "AB", "O"]),
            height=height,
            weight=weight,
            bmi=bmi,
            allergies=random.choice(["无", "青霉素过敏", "花粉过敏", "海鲜过敏"]),
            chronic_diseases=random.choice(["无", "高血压", "糖尿病", "颈椎病"]),
            medications=random.choice(["无", "降压药", "维生素"]),
            emergency_contact=random.choice(FIRST_NAMES) + random.choice(LAST_NAMES),
            emergency_phone=generate_phone(),
            last_checkup_date=date.today() - timedelta(days=random.randint(30, 365)),
            risk_level=random.choice(["low", "medium", "high"]),
            health_score=random.randint(60, 95)
        )
        profiles.append(profile)
        db.add(profile)
    db.flush()
    print(f"已创建 {len(profiles)} 份健康档案")


def seed_sample_tickets_and_followups(db, employees, admins):
    print("正在创建示例预警工单和回访记录...")
    tickets = []
    followups = []

    metric_names = ["heart_rate", "sleep_duration", "steps", "stress_level", "blood_oxygen"]
    alert_types = ["心率异常", "睡眠异常", "步数异常", "压力异常", "血氧异常"]

    for _ in range(50):
        employee = random.choice(employees)
        admin = random.choice(admins)
        severity = random.choice(["low", "medium", "high", "critical"])
        status = random.choice(["pending", "assigned", "in_progress", "resolved", "closed"])
        metric_idx = random.randint(0, 4)
        metric_name = metric_names[metric_idx]
        alert_type = alert_types[metric_idx]

        baseline_value = random.uniform(60, 100)
        deviation_percent = random.uniform(20, 80)
        current_value = baseline_value * (1 + deviation_percent / 100 * random.choice([1, -1]))

        ticket = AlertTicket(
            employee_id=employee.id,
            ticket_no=generate_ticket_no(),
            alert_type=alert_type,
            severity=severity,
            metric_name=metric_name,
            current_value=round(current_value, 2),
            baseline_value=round(baseline_value, 2),
            deviation_percent=round(deviation_percent, 2),
            threshold=round(baseline_value * 1.2, 2),
            title=f"{alert_type}预警",
            description=f"检测到{alert_type}，当前值{current_value:.1f}，偏离基线{deviation_percent:.1f}%",
            personal_advice=random.choice([
                "建议适当休息，避免过度劳累",
                "建议尽快就医检查",
                "建议调整作息时间，保证充足睡眠",
                "建议减少剧烈运动，注意观察"
            ]),
            status=status,
            assigned_admin_id=admin.id if status != "pending" else None,
            follow_up_result="已跟进处理" if status in ["resolved", "closed"] else None,
            follow_up_time=datetime.now() - timedelta(days=random.randint(0, 15)) if status in ["resolved", "closed"] else None,
            follow_up_by=admin.name if status in ["resolved", "closed"] else None,
            created_at=datetime.now() - timedelta(days=random.randint(0, 30))
        )
        tickets.append(ticket)
        db.add(ticket)
        db.flush()

        if status in ["resolved", "closed"]:
            followup = FollowUpRecord(
                alert_ticket_id=ticket.id,
                follow_up_time=datetime.now() - timedelta(days=random.randint(0, 10)),
                follow_up_by=admin.name,
                contact_method=random.choice(["电话", "面谈", "微信", "邮件"]),
                employee_response=random.choice([
                    "已恢复正常",
                    "有所好转",
                    "已就医检查",
                    "调整作息后改善"
                ]),
                admin_assessment="员工状态良好，建议继续观察",
                action_taken="已提供健康指导",
                next_follow_up=datetime.now() + timedelta(days=random.randint(3, 14)) if random.random() < 0.3 else None,
                is_resolved=True
            )
            followups.append(followup)
            db.add(followup)

    db.flush()
    print(f"已创建 {len(tickets)} 条预警工单，{len(followups)} 条回访记录")


def seed_medical_reports(db, employees):
    print("正在创建示例体检报告...")
    reports = []
    indicators = []

    indicator_names = [
        ("身高", "cm", 155, 185),
        ("体重", "kg", 45, 90),
        ("BMI", "", 18, 28),
        ("血压", "mmHg", 110, 140),
        ("心率", "次/分", 60, 90),
        ("血糖", "mmol/L", 4.0, 7.0),
        ("胆固醇", "mmol/L", 3.0, 6.0),
        ("甘油三酯", "mmol/L", 0.5, 2.5),
        ("高密度脂蛋白", "mmol/L", 1.0, 2.0),
        ("低密度脂蛋白", "mmol/L", 2.0, 4.0),
        ("血红蛋白", "g/L", 120, 160),
        ("白细胞计数", "×10^9/L", 4.0, 10.0),
        ("红细胞计数", "×10^12/L", 4.0, 5.5),
        ("血小板计数", "×10^9/L", 100, 300),
        ("谷丙转氨酶", "U/L", 0, 50),
        ("谷草转氨酶", "U/L", 0, 50),
        ("肌酐", "μmol/L", 40, 100),
        ("尿素氮", "mmol/L", 2.5, 7.5),
        ("尿酸", "μmol/L", 150, 420),
        ("视力", "", 0.8, 1.5),
    ]

    for _ in range(30):
        employee = random.choice(employees)
        report_date = date.today() - timedelta(days=random.randint(30, 365))
        report = MedicalReport(
            employee_id=employee.id,
            report_date=report_date,
            report_type=random.choice(["年度体检", "季度体检", "专项检查"]),
            hospital=random.choice(["市第一人民医院", "中心医院", "协和医院", "仁爱体检中心"]),
            file_path=f"/uploads/medical_reports/{employee.id}_{report_date.strftime('%Y%m%d')}.pdf",
            ocr_processed=True,
            ocr_text="",
            overall_summary=random.choice(["健康", "基本健康", "需关注", "建议复查"])
        )
        reports.append(report)
        db.add(report)
        db.flush()

        for name, unit, min_val, max_val in indicator_names:
            value = random.uniform(min_val, max_val)
            is_abnormal = random.random() < 0.1

            indicator = MedicalIndicator(
                medical_report_id=report.id,
                indicator_name=name,
                indicator_code=name[:4].upper(),
                value=round(value, 2),
                unit=unit,
                reference_range=f"{min_val}-{max_val}",
                status=("异常" if is_abnormal else "正常"),
                is_abnormal=is_abnormal,
                change_from_last=round(random.uniform(-5, 5), 2) if random.random() < 0.7 else None,
                change_percent=round(random.uniform(-10, 10), 2) if random.random() < 0.7 else None
            )
            indicators.append(indicator)
            db.add(indicator)

    db.flush()
    print(f"已创建 {len(reports)} 份体检报告，{len(indicators)} 项体检指标")


def seed_operation_logs(db, employees, admins):
    print("正在创建操作日志...")
    logs = []
    operations = [
        ("data_collection", "系统自动采集健康数据"),
        ("anomaly_detection", "检测到健康数据异常"),
        ("ticket_generation", "自动生成预警工单"),
        ("ticket_assignment", "工单已分配给管理员"),
        ("follow_up", "管理员完成回访"),
        ("report_upload", "员工上传体检报告"),
        ("data_export", "导出健康数据Excel"),
        ("baseline_update", "更新员工健康基线"),
    ]

    for _ in range(100):
        op_type, action = random.choice(operations)
        target_type = random.choice(["employee", "ticket", "report", "system"])
        operator = random.choice(["system"] + [a.name for a in admins] + [e.name for e in employees[:10]])

        log = OperationLog(
            operation_type=op_type,
            operator=operator,
            target_type=target_type,
            target_id=random.randint(1, 500),
            action=action,
            detail=f"{action}操作完成",
            ip_address=f"192.168.{random.randint(1, 255)}.{random.randint(1, 255)}",
            user_agent="Mozilla/5.0",
            created_at=datetime.now() - timedelta(days=random.randint(0, 30))
        )
        logs.append(log)
        db.add(log)

    db.flush()
    print(f"已创建 {len(logs)} 条操作日志")


def main():
    print("=" * 60)
    print("企业级员工健康管理系统 - 示例数据初始化脚本")
    print("=" * 60)

    with get_db_context() as db:
        print("\n开始初始化数据...\n")

        departments = seed_departments(db)
        employees = seed_employees(db, departments)
        admins = seed_health_admins(db, employees)
        seed_health_data(db, employees)
        seed_health_baselines(db, employees)
        seed_health_profiles(db, employees)
        seed_sample_tickets_and_followups(db, employees, admins)
        seed_medical_reports(db, employees)
        seed_operation_logs(db, employees, admins)

        db.commit()

    print("\n" + "=" * 60)
    print("数据初始化完成！")
    print("=" * 60)
    print(f"部门数: {len(DEPARTMENTS)}")
    print(f"健康管理员数: {len(ADMIN_NAMES)}")
    print(f"员工数: {len(employees)}")
    print(f"健康数据: 约{len(employees) * 45}条")
    print("=" * 60)


if __name__ == "__main__":
    main()
