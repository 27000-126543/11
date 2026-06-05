from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, Date, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, date

from .database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    manager_id = Column(Integer, ForeignKey("employees.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employees = relationship("Employee", back_populates="department", foreign_keys="Employee.department_id")
    manager = relationship("Employee", foreign_keys=[manager_id])
    weekly_reports = relationship("WeeklyReport", back_populates="department")
    health_monitors = relationship("DepartmentHealthMonitor", back_populates="department")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_no = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    gender = Column(String(10))
    age = Column(Integer)
    phone = Column(String(20))
    email = Column(String(100))
    department_id = Column(Integer, ForeignKey("departments.id"))
    position = Column(String(100))
    hire_date = Column(Date)
    is_active = Column(Boolean, default=True)
    device_id = Column(String(100), index=True)
    health_app_account = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    department = relationship("Department", back_populates="employees", foreign_keys=[department_id])
    health_data = relationship("HealthData", back_populates="employee")
    baselines = relationship("HealthBaseline", back_populates="employee")
    alert_tickets = relationship("AlertTicket", back_populates="employee")
    medical_reports = relationship("MedicalReport", back_populates="employee")
    health_profile = relationship("HealthProfile", uselist=False, back_populates="employee")
    activity_participations = relationship("ActivityParticipant", back_populates="employee")


class HealthAdmin(Base):
    __tablename__ = "health_admins"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    specialty = Column(String(100))
    severity_level = Column(Integer, default=1)
    phone = Column(String(20))
    email = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    assigned_tickets = relationship("AlertTicket", back_populates="assigned_admin")


class HealthData(Base):
    __tablename__ = "health_data"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    data_date = Column(Date, index=True, default=date.today)
    record_time = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    data_source = Column(String(50))

    heart_rate = Column(Integer)
    heart_rate_resting = Column(Integer)
    heart_rate_variability = Column(Float)
    steps = Column(Integer)
    distance = Column(Float)
    calories_burned = Column(Float)
    sleep_duration = Column(Float)
    deep_sleep = Column(Float)
    light_sleep = Column(Float)
    rem_sleep = Column(Float)
    sleep_awake_time = Column(Float)
    sleep_score = Column(Integer)

    systolic_bp = Column(Integer)
    diastolic_bp = Column(Integer)
    blood_oxygen = Column(Float)
    stress_level = Column(Integer)

    is_anomaly = Column(Boolean, default=False)
    anomaly_details = Column(JSON)
    processed = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee", back_populates="health_data")


class HealthBaseline(Base):
    __tablename__ = "health_baselines"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    metric_name = Column(String(50), index=True)
    baseline_value = Column(Float)
    std_dev = Column(Float)
    min_value = Column(Float)
    max_value = Column(Float)
    percentile_25 = Column(Float)
    percentile_50 = Column(Float)
    percentile_75 = Column(Float)
    data_count = Column(Integer)
    calculation_date = Column(Date, index=True, default=date.today)
    baseline_days = Column(Integer, default=30)

    employee = relationship("Employee", back_populates="baselines")


class AlertTicket(Base):
    __tablename__ = "alert_tickets"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    ticket_no = Column(String(50), unique=True, index=True)
    alert_type = Column(String(50), index=True)
    severity = Column(String(20), index=True)
    metric_name = Column(String(50))
    current_value = Column(Float)
    baseline_value = Column(Float)
    deviation_percent = Column(Float)
    threshold = Column(Float)

    title = Column(String(200))
    description = Column(Text)
    personal_advice = Column(Text)

    assigned_admin_id = Column(Integer, ForeignKey("health_admins.id"))
    status = Column(String(20), default="pending", index=True)

    follow_up_result = Column(Text)
    follow_up_time = Column(DateTime(timezone=True))
    follow_up_by = Column(String(100))

    health_data_id = Column(Integer, ForeignKey("health_data.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", back_populates="alert_tickets")
    assigned_admin = relationship("HealthAdmin", back_populates="assigned_tickets")
    follow_up_records = relationship("FollowUpRecord", back_populates="alert_ticket")


class FollowUpRecord(Base):
    __tablename__ = "follow_up_records"

    id = Column(Integer, primary_key=True, index=True)
    alert_ticket_id = Column(Integer, ForeignKey("alert_tickets.id"), index=True)
    follow_up_time = Column(DateTime(timezone=True), server_default=func.now())
    follow_up_by = Column(String(100))
    contact_method = Column(String(50))
    employee_response = Column(Text)
    admin_assessment = Column(Text)
    action_taken = Column(Text)
    next_follow_up = Column(DateTime(timezone=True))
    is_resolved = Column(Boolean, default=False)

    alert_ticket = relationship("AlertTicket", back_populates="follow_up_records")


class MedicalReport(Base):
    __tablename__ = "medical_reports"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    report_date = Column(Date, index=True)
    report_type = Column(String(50))
    hospital = Column(String(200))
    file_path = Column(String(500))
    ocr_processed = Column(Boolean, default=False)
    ocr_text = Column(Text)
    overall_summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee", back_populates="medical_reports")
    indicators = relationship("MedicalIndicator", back_populates="medical_report")


class MedicalIndicator(Base):
    __tablename__ = "medical_indicators"

    id = Column(Integer, primary_key=True, index=True)
    medical_report_id = Column(Integer, ForeignKey("medical_reports.id"), index=True)
    indicator_name = Column(String(100), index=True)
    indicator_code = Column(String(50))
    value = Column(Float)
    unit = Column(String(20))
    reference_range = Column(String(100))
    status = Column(String(20))
    is_abnormal = Column(Boolean, default=False)
    change_from_last = Column(Float)
    change_percent = Column(Float)

    medical_report = relationship("MedicalReport", back_populates="indicators")


class HealthProfile(Base):
    __tablename__ = "health_profiles"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), unique=True, index=True)
    blood_type = Column(String(10))
    height = Column(Float)
    weight = Column(Float)
    bmi = Column(Float)
    allergies = Column(Text)
    chronic_diseases = Column(Text)
    medications = Column(Text)
    emergency_contact = Column(String(100))
    emergency_phone = Column(String(20))
    last_checkup_date = Column(Date)
    risk_level = Column(String(20), default="normal")
    health_score = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", back_populates="health_profile")


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), index=True)
    report_week = Column(String(20), index=True)
    start_date = Column(Date)
    end_date = Column(Date)

    total_employees = Column(Integer)
    active_employees = Column(Integer)

    anomaly_count = Column(Integer)
    anomaly_rate = Column(Float)
    heart_rate_anomalies = Column(Integer)
    sleep_anomalies = Column(Integer)
    steps_anomalies = Column(Integer)

    avg_steps = Column(Float)
    avg_sleep_duration = Column(Float)
    avg_heart_rate = Column(Float)

    checkup_participation_rate = Column(Float)
    checkup_count = Column(Integer)

    high_risk_count = Column(Integer)
    medium_risk_count = Column(Integer)
    low_risk_count = Column(Integer)

    alerts_resolved = Column(Integer)
    alerts_pending = Column(Integer)

    report_data = Column(JSON)
    chart_paths = Column(JSON)

    sent = Column(Boolean, default=False)
    sent_to = Column(String(200))
    sent_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    department = relationship("Department", back_populates="weekly_reports")


class DepartmentHealthMonitor(Base):
    __tablename__ = "department_health_monitors"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), index=True)
    monitor_date = Column(Date, index=True)

    total_employees = Column(Integer)
    anomaly_count = Column(Integer)
    anomaly_rate = Column(Float)
    company_avg_anomaly_rate = Column(Float)
    deviation_from_avg = Column(Float)

    above_threshold = Column(Boolean, default=False)
    consecutive_days_above = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    department = relationship("Department", back_populates="health_monitors")


class HealthPromotionActivity(Base):
    __tablename__ = "health_promotion_activities"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), index=True)
    activity_no = Column(String(50), unique=True, index=True)
    activity_type = Column(String(50))
    title = Column(String(200))
    description = Column(Text)
    activity_plan = Column(JSON)
    target_metric = Column(String(50))
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(20), default="draft")
    invited_count = Column(Integer, default=0)
    participated_count = Column(Integer, default=0)
    auto_generated = Column(Boolean, default=False)
    trigger_reason = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    participants = relationship("ActivityParticipant", back_populates="activity")


class ActivityParticipant(Base):
    __tablename__ = "activity_participants"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("health_promotion_activities.id"), index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    status = Column(String(20), default="invited")
    invited_at = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at = Column(DateTime(timezone=True))
    participation_score = Column(Integer)
    feedback = Column(Text)

    activity = relationship("HealthPromotionActivity", back_populates="participants")
    employee = relationship("Employee", back_populates="activity_participations")


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    operation_type = Column(String(50), index=True)
    operator = Column(String(100), index=True)
    target_type = Column(String(50))
    target_id = Column(Integer)
    action = Column(String(200))
    detail = Column(Text)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
