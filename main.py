import os
import sys
import uvicorn
import argparse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from app.config import get_settings
from app.database import get_db, init_db
from app.logging_config import setup_logging, get_logger, log_audit
from app.models import (
    Department, Employee, HealthAdmin, HealthData, HealthBaseline,
    AlertTicket, FollowUpRecord, MedicalReport, MedicalIndicator,
    HealthProfile, WeeklyReport, DepartmentHealthMonitor,
    HealthPromotionActivity, ActivityParticipant, OperationLog
)
from app.data_collection import get_data_collector
from app.anomaly_detection import get_anomaly_detector, get_baseline_calculator
from app.alert_ticket import get_alert_ticket_manager
from app.medical_report import get_medical_report_manager
from app.report_generator import get_weekly_report_generator
from app.health_promotion import get_health_promotion_manager
from app.data_exporter import (
    HealthDataQuery, AlertTicketQuery, ExcelExporter, OperationLogQuery
)
from app.scheduler import get_scheduler

settings = get_settings()
logger = get_logger(__name__)


class HealthDataQueryRequest(BaseModel):
    department_id: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    metric_type: Optional[str] = None
    employee_id: Optional[int] = None
    page: int = 1
    page_size: int = 50


class FollowUpRequest(BaseModel):
    ticket_id: int
    admin_id: int
    followup_method: str
    employee_feedback: str
    admin_notes: str
    followup_result: str
    next_followup_date: Optional[str] = None


class TicketUpdateRequest(BaseModel):
    status: str
    admin_notes: Optional[str] = None


def initialize_system():
    setup_logging()
    logger.info("正在初始化数据库...")
    init_db()
    logger.info("数据库初始化完成")


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_system()

    scheduler = get_scheduler()
    if settings.SCHEDULER_ENABLED:
        logger.info("正在启动定时任务调度器...")
        scheduler.start()
        logger.info("定时任务调度器已启动")

    yield

    if settings.SCHEDULER_ENABLED:
        logger.info("正在关闭定时任务调度器...")
        scheduler.stop()
        logger.info("定时任务调度器已关闭")


app = FastAPI(
    title="企业级员工健康管理与异常预警系统",
    description="自动化健康数据采集、异常检测、预警工单、健康促进活动的综合管理系统",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/", tags=["系统"])
async def root():
    return {
        "name": "企业级员工健康管理与异常预警系统",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health", tags=["系统"])
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/departments", tags=["部门管理"])
def get_departments(db: Session = Depends(get_db)):
    departments = db.query(Department).all()
    return {"code": 200, "message": "success", "data": departments}


@app.get("/api/employees", tags=["员工管理"])
def get_employees(
    department_id: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(Employee).filter(Employee.is_active == True)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if keyword:
        query = query.filter(
            (Employee.name.like(f"%{keyword}%")) |
            (Employee.employee_id.like(f"%{keyword}%"))
        )
    total = query.count()
    employees = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"code": 200, "message": "success", "data": employees, "total": total}


@app.get("/api/employees/{employee_id}", tags=["员工管理"])
def get_employee_detail(employee_id: int, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="员工不存在")
    return {"code": 200, "message": "success", "data": employee}


@app.get("/api/employees/{employee_id}/profile", tags=["员工管理"])
def get_employee_profile(employee_id: int, db: Session = Depends(get_db)):
    profile = db.query(HealthProfile).filter(HealthProfile.employee_id == employee_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="健康档案不存在")
    return {"code": 200, "message": "success", "data": profile}


@app.get("/api/employees/{employee_id}/health-data", tags=["健康数据"])
def get_employee_health_data(
    employee_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(HealthData).filter(HealthData.employee_id == employee_id)
    if start_date:
        query = query.filter(HealthData.data_date >= start_date)
    if end_date:
        query = query.filter(HealthData.data_date <= end_date)
    data = query.order_by(HealthData.data_date.desc()).limit(30).all()
    return {"code": 200, "message": "success", "data": data}


@app.post("/api/health-data/query", tags=["健康数据"])
def query_health_data(
    request: HealthDataQueryRequest
):
    query = HealthDataQuery()
    metric_types = [request.metric_type] if request.metric_type else None
    data, total = query.query_health_data(
        department_id=request.department_id,
        employee_id=request.employee_id,
        start_date=request.start_date,
        end_date=request.end_date,
        metric_types=metric_types,
        page=request.page,
        page_size=request.page_size
    )
    return {"code": 200, "message": "success", "data": {"items": data, "total": total, "page": request.page, "page_size": request.page_size}}


@app.post("/api/health-data/export", tags=["健康数据"])
def export_health_data(
    request: HealthDataQueryRequest
):
    exporter = ExcelExporter()
    metric_types = [request.metric_type] if request.metric_type else None
    file_path = exporter.export_health_data_to_excel(
        department_id=request.department_id,
        employee_id=request.employee_id,
        start_date=request.start_date,
        end_date=request.end_date,
        metric_types=metric_types
    )
    log_audit("数据导出", f"导出健康数据Excel: {os.path.basename(file_path)}", "admin")
    
    filename = os.path.basename(file_path)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        "Access-Control-Expose-Headers": "Content-Disposition"
    }
    
    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
        headers=headers
    )


@app.get("/api/tickets", tags=["预警工单"])
def get_tickets(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    admin_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50
):
    query = AlertTicketQuery()
    data, total = query.query_tickets(
        status=status,
        severity=severity,
        assigned_admin_id=admin_id,
        page=page,
        page_size=page_size
    )
    return {"code": 200, "message": "success", "data": {"items": data, "total": total, "page": page, "page_size": page_size}}


@app.put("/api/tickets/{ticket_id}", tags=["预警工单"])
def update_ticket(
    ticket_id: int,
    request: TicketUpdateRequest,
    db: Session = Depends(get_db)
):
    ticket = db.query(AlertTicket).filter(AlertTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    ticket.status = request.status
    if request.status in ["已解决", "已关闭"]:
        ticket.resolved_at = datetime.now()

    db.commit()
    log_audit("工单更新", f"更新工单状态: {ticket.ticket_no} -> {request.status}", "admin")
    return {"code": 200, "message": "success", "data": ticket}


@app.post("/api/followups", tags=["回访管理"])
def create_followup(
    request: FollowUpRequest,
    db: Session = Depends(get_db)
):
    ticket = db.query(AlertTicket).filter(AlertTicket.id == request.ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    followup_manager = get_alert_ticket_manager()
    next_date = datetime.strptime(request.next_followup_date, "%Y-%m-%d") if request.next_followup_date else None

    followup = followup_manager.create_follow_up_record(
        ticket_id=request.ticket_id,
        employee_id=ticket.employee_id,
        admin_id=request.admin_id,
        followup_method=request.followup_method,
        employee_feedback=request.employee_feedback,
        admin_notes=request.admin_notes,
        followup_result=request.followup_result,
        next_followup_date=next_date
    )

    db.commit()
    log_audit("回访记录", f"创建工单回访记录: {ticket.ticket_no}", "admin", request.admin_id)
    return {"code": 200, "message": "success", "data": followup}


@app.get("/api/followups/{ticket_id}", tags=["回访管理"])
def get_ticket_followups(ticket_id: int, db: Session = Depends(get_db)):
    followups = db.query(FollowUpRecord).filter(FollowUpRecord.ticket_id == ticket_id).order_by(FollowUpRecord.followup_date.desc()).all()
    return {"code": 200, "message": "success", "data": followups}


@app.post("/api/medical-reports/upload", tags=["体检报告"])
async def upload_medical_report(
    employee_id: int,
    report_date: str,
    hospital: str,
    report_type: str = "年度体检",
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    upload_dir = os.path.join(settings.UPLOAD_DIR, "medical_reports")
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = os.path.splitext(file.filename)[1]
    file_name = f"MED_{employee_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{file_ext}"
    file_path = os.path.join(upload_dir, file_name)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    manager = get_medical_report_manager()
    report = manager.process_report_ocr(
        employee_id=employee_id,
        file_path=file_path,
        report_date=datetime.strptime(report_date, "%Y-%m-%d").date(),
        hospital=hospital,
        report_type=report_type
    )

    db.commit()
    log_audit("体检报告", f"员工{employee_id}上传体检报告: {file_name}", "employee", employee_id)
    return {"code": 200, "message": "success", "data": report}


@app.get("/api/medical-reports/{employee_id}", tags=["体检报告"])
def get_employee_medical_reports(employee_id: int, db: Session = Depends(get_db)):
    manager = get_medical_report_manager()
    history = manager.get_employee_medical_history(employee_id)
    return {"code": 200, "message": "success", "data": history}


@app.get("/api/medical-reports/{employee_id}/chart/{indicator_name}", tags=["体检报告"])
def get_indicator_chart(employee_id: int, indicator_name: str, db: Session = Depends(get_db)):
    manager = get_medical_report_manager()
    chart_path = manager.generate_indicator_chart(employee_id, indicator_name)
    if not chart_path:
        raise HTTPException(status_code=404, detail="图表生成失败")
    return FileResponse(chart_path, media_type="image/png")


@app.get("/api/weekly-reports", tags=["健康报告"])
def get_weekly_reports(
    department_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    query = db.query(WeeklyReport)
    if department_id:
        query = query.filter(WeeklyReport.department_id == department_id)
    total = query.count()
    reports = query.order_by(WeeklyReport.week_start_date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"code": 200, "message": "success", "data": reports, "total": total}


@app.get("/api/weekly-reports/{report_id}", tags=["健康报告"])
def get_weekly_report_detail(report_id: int, db: Session = Depends(get_db)):
    report = db.query(WeeklyReport).filter(WeeklyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"code": 200, "message": "success", "data": report}


@app.get("/api/health-activities", tags=["健康促进"])
def get_health_activities(
    status: Optional[str] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(HealthPromotionActivity)
    if status:
        query = query.filter(HealthPromotionActivity.status == status)
    if department_id:
        query = query.filter(HealthPromotionActivity.department_id == department_id)
    activities = query.order_by(HealthPromotionActivity.created_at.desc()).all()
    return {"code": 200, "message": "success", "data": activities}


@app.post("/api/health-activities/{activity_id}/join", tags=["健康促进"])
def join_activity(
    activity_id: int,
    employee_id: int,
    db: Session = Depends(get_db)
):
    activity = db.query(HealthPromotionActivity).filter(HealthPromotionActivity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="活动不存在")

    existing = db.query(ActivityParticipant).filter(
        ActivityParticipant.activity_id == activity_id,
        ActivityParticipant.employee_id == employee_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="已报名该活动")

    participant = ActivityParticipant(
        activity_id=activity_id,
        employee_id=employee_id,
        joined_at=datetime.now()
    )
    activity.current_participants += 1
    db.add(participant)
    db.commit()

    log_audit("活动报名", f"员工{employee_id}报名活动: {activity.activity_name}", "employee", employee_id)
    return {"code": 200, "message": "success", "data": participant}


@app.get("/api/department-monitor", tags=["健康监控"])
def get_department_monitor(
    department_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(DepartmentHealthMonitor).order_by(DepartmentHealthMonitor.monitor_date.desc())
    if department_id:
        query = query.filter(DepartmentHealthMonitor.department_id == department_id)
    data = query.limit(30).all()
    return {"code": 200, "message": "success", "data": data}


@app.get("/api/operation-logs", tags=["系统日志"])
def get_operation_logs(
    operation_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 50
):
    query = OperationLogQuery()
    data, total = query.query_operation_logs(
        operation_type=operation_type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size
    )
    return {"code": 200, "message": "success", "data": {"items": data, "total": total, "page": page, "page_size": page_size}}


@app.post("/api/scheduler/tasks/run/{task_id}", tags=["定时任务"])
def run_scheduled_task(task_id: str, db: Session = Depends(get_db)):
    scheduler = get_scheduler()
    try:
        scheduler.run_task_now(task_id)
        log_audit("定时任务", f"手动执行任务: {task_id}", "admin")
        return {"code": 200, "message": f"任务 {task_id} 已启动执行"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"任务执行失败: {str(e)}")


@app.get("/api/scheduler/tasks", tags=["定时任务"])
def get_scheduled_tasks():
    scheduler = get_scheduler()
    tasks = scheduler.get_jobs()
    return {"code": 200, "message": "success", "data": tasks}


@app.post("/api/scheduler/tasks/{task_id}/pause", tags=["定时任务"])
def pause_task(task_id: str):
    scheduler = get_scheduler()
    scheduler.pause_job(task_id)
    log_audit("定时任务", f"暂停任务: {task_id}", "admin")
    return {"code": 200, "message": f"任务 {task_id} 已暂停"}


@app.post("/api/scheduler/tasks/{task_id}/resume", tags=["定时任务"])
def resume_task(task_id: str):
    scheduler = get_scheduler()
    scheduler.resume_job(task_id)
    log_audit("定时任务", f"恢复任务: {task_id}", "admin")
    return {"code": 200, "message": f"任务 {task_id} 已恢复"}


@app.get("/api/stats/summary", tags=["统计概览"])
def get_stats_summary(db: Session = Depends(get_db)):
    total_employees = db.query(Employee).filter(Employee.is_active == True).count()
    total_departments = db.query(Department).count()
    pending_tickets = db.query(AlertTicket).filter(AlertTicket.status == "pending").count()
    today_health_data = db.query(HealthData).filter(HealthData.data_date == date.today()).count()
    total_reports = db.query(WeeklyReport).count()
    active_activities = db.query(HealthPromotionActivity).filter(HealthPromotionActivity.status == "in_progress").count()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_employees": total_employees,
            "total_departments": total_departments,
            "pending_tickets": pending_tickets,
            "today_health_data_count": today_health_data,
            "total_reports": total_reports,
            "active_activities": active_activities
        }
    }


def main():
    parser = argparse.ArgumentParser(description="企业级员工健康管理与异常预警系统")
    parser.add_argument("--init-db", action="store_true", help="初始化数据库")
    parser.add_argument("--seed-data", action="store_true", help="插入示例数据")
    parser.add_argument("--host", default="0.0.0.0", help="服务监听地址")
    parser.add_argument("--port", type=int, default=8000, help="服务监听端口")
    parser.add_argument("--no-scheduler", action="store_true", help="禁用定时任务")

    args = parser.parse_args()

    if args.init_db:
        print("正在初始化数据库...")
        initialize_system()
        print("数据库初始化完成！")
        return

    if args.seed_data:
        print("正在插入示例数据...")
        from scripts.seed_data import main as seed_main
        seed_main()
        print("示例数据插入完成！")
        return

    if args.no_scheduler:
        settings.SCHEDULER_ENABLED = False

    print(f"启动服务: {args.host}:{args.port}")
    print(f"定时任务: {'已启用' if settings.SCHEDULER_ENABLED else '已禁用'}")
    print(f"API文档: http://{args.host}:{args.port}/docs")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
