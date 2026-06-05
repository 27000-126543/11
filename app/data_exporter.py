import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple, Any
from sqlalchemy.orm import Session
import pandas as pd
import numpy as np

from .database import get_db_context
from .models import (
    Employee, Department, HealthData, HealthBaseline, AlertTicket,
    MedicalReport, WeeklyReport, HealthPromotionActivity, OperationLog
)
from .logging_config import get_logger, log_audit
from .alert_ticket import AlertSeverity, METRIC_NAMES_CN
from .anomaly_detection import MetricType

logger = get_logger(__name__)

os.makedirs("data/exports", exist_ok=True)


class HealthDataQuery:
    def query_health_data(
        self,
        department_id: Optional[int] = None,
        employee_id: Optional[int] = None,
        employee_no: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        metric_types: Optional[List[str]] = None,
        is_anomaly: Optional[bool] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Dict], int]:
        with get_db_context() as db:
            query = db.query(HealthData).join(Employee).join(Department, Employee.department_id == Department.id, isouter=True)

            if department_id:
                query = query.filter(Employee.department_id == department_id)
            if employee_id:
                query = query.filter(HealthData.employee_id == employee_id)
            if employee_no:
                query = query.filter(Employee.employee_no == employee_no)
            if start_date:
                query = query.filter(HealthData.data_date >= start_date)
            if end_date:
                query = query.filter(HealthData.data_date <= end_date)
            if is_anomaly is not None:
                query = query.filter(HealthData.is_anomaly == is_anomaly)

            total = query.count()
            health_data_list = query.order_by(HealthData.data_date.desc(), HealthData.employee_id)\
                .offset((page - 1) * page_size)\
                .limit(page_size)\
                .all()

            results = []
            for hd in health_data_list:
                data = {
                    "id": hd.id,
                    "employee_id": hd.employee_id,
                    "employee_name": hd.employee.name if hd.employee else "",
                    "employee_no": hd.employee.employee_no if hd.employee else "",
                    "department": hd.employee.department.name if hd.employee and hd.employee.department else "",
                    "data_date": hd.data_date.isoformat() if hd.data_date else "",
                    "data_source": hd.data_source,
                    "heart_rate": hd.heart_rate,
                    "heart_rate_resting": hd.heart_rate_resting,
                    "steps": hd.steps,
                    "sleep_duration": hd.sleep_duration,
                    "deep_sleep": hd.deep_sleep,
                    "sleep_score": hd.sleep_score,
                    "systolic_bp": hd.systolic_bp,
                    "diastolic_bp": hd.diastolic_bp,
                    "blood_oxygen": hd.blood_oxygen,
                    "stress_level": hd.stress_level,
                    "is_anomaly": hd.is_anomaly,
                    "anomaly_details": hd.anomaly_details,
                    "created_at": hd.created_at.isoformat() if hd.created_at else ""
                }
                results.append(data)

            return results, total

    def get_health_trend(
        self,
        employee_id: int,
        metric_name: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        days: int = 30
    ) -> List[Dict]:
        if not start_date:
            end_date = end_date or date.today()
            start_date = end_date - timedelta(days=days)

        with get_db_context() as db:
            health_data = db.query(HealthData).filter(
                HealthData.employee_id == employee_id,
                HealthData.data_date >= start_date,
                HealthData.data_date <= end_date
            ).order_by(HealthData.data_date).all()

            baseline = db.query(HealthBaseline).filter(
                HealthBaseline.employee_id == employee_id,
                HealthBaseline.metric_name == metric_name
            ).order_by(HealthBaseline.calculation_date.desc()).first()

            trend = []
            for hd in health_data:
                value = getattr(hd, metric_name, None)
                if value is not None:
                    trend.append({
                        "date": hd.data_date.isoformat(),
                        "value": value,
                        "is_anomaly": hd.is_anomaly,
                        "baseline": baseline.baseline_value if baseline else None,
                        "baseline_upper": baseline.baseline_value + 2 * baseline.std_dev if baseline else None,
                        "baseline_lower": baseline.baseline_value - 2 * baseline.std_dev if baseline else None
                    })

            return trend


class AlertTicketQuery:
    def query_tickets(
        self,
        department_id: Optional[int] = None,
        employee_id: Optional[int] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        assigned_admin_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Dict], int]:
        with get_db_context() as db:
            query = db.query(AlertTicket).join(Employee).join(Department, Employee.department_id == Department.id, isouter=True)

            if department_id:
                query = query.filter(Employee.department_id == department_id)
            if employee_id:
                query = query.filter(AlertTicket.employee_id == employee_id)
            if status:
                query = query.filter(AlertTicket.status == status)
            if severity:
                query = query.filter(AlertTicket.severity == severity)
            if alert_type:
                query = query.filter(AlertTicket.alert_type == alert_type)
            if start_date:
                query = query.filter(AlertTicket.created_at >= start_date)
            if end_date:
                query = query.filter(AlertTicket.created_at <= end_date + timedelta(days=1))
            if assigned_admin_id:
                query = query.filter(AlertTicket.assigned_admin_id == assigned_admin_id)

            total = query.count()
            tickets = query.order_by(AlertTicket.created_at.desc())\
                .offset((page - 1) * page_size)\
                .limit(page_size)\
                .all()

            results = []
            for ticket in tickets:
                data = {
                    "id": ticket.id,
                    "ticket_no": ticket.ticket_no,
                    "employee_id": ticket.employee_id,
                    "employee_name": ticket.employee.name if ticket.employee else "",
                    "employee_no": ticket.employee.employee_no if ticket.employee else "",
                    "department": ticket.employee.department.name if ticket.employee and ticket.employee.department else "",
                    "alert_type": ticket.alert_type,
                    "severity": ticket.severity,
                    "metric_name": ticket.metric_name,
                    "metric_name_cn": METRIC_NAMES_CN.get(ticket.metric_name, ticket.metric_name),
                    "current_value": ticket.current_value,
                    "baseline_value": ticket.baseline_value,
                    "deviation_percent": ticket.deviation_percent,
                    "title": ticket.title,
                    "description": ticket.description,
                    "personal_advice": ticket.personal_advice,
                    "assigned_admin": ticket.assigned_admin.name if ticket.assigned_admin else "",
                    "status": ticket.status,
                    "follow_up_result": ticket.follow_up_result,
                    "follow_up_time": ticket.follow_up_time.isoformat() if ticket.follow_up_time else "",
                    "follow_up_by": ticket.follow_up_by,
                    "created_at": ticket.created_at.isoformat() if ticket.created_at else ""
                }
                results.append(data)

            return results, total

    def get_ticket_statistics(
        self,
        department_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict:
        with get_db_context() as db:
            query = db.query(AlertTicket).join(Employee)

            if department_id:
                query = query.filter(Employee.department_id == department_id)
            if start_date:
                query = query.filter(AlertTicket.created_at >= start_date)
            if end_date:
                query = query.filter(AlertTicket.created_at <= end_date + timedelta(days=1))

            tickets = query.all()

            stats = {
                "total": len(tickets),
                "by_severity": {},
                "by_status": {},
                "by_metric": {}
            }

            severity_map = {
                AlertSeverity.LOW: "低",
                AlertSeverity.MEDIUM: "中",
                AlertSeverity.HIGH: "高",
                AlertSeverity.CRITICAL: "危急"
            }

            for ticket in tickets:
                severity_cn = severity_map.get(ticket.severity, ticket.severity)
                stats["by_severity"][severity_cn] = stats["by_severity"].get(severity_cn, 0) + 1
                stats["by_status"][ticket.status] = stats["by_status"].get(ticket.status, 0) + 1

                metric_cn = METRIC_NAMES_CN.get(ticket.metric_name, ticket.metric_name)
                stats["by_metric"][metric_cn] = stats["by_metric"].get(metric_cn, 0) + 1

            return stats


class ExcelExporter:
    def export_health_data_to_excel(
        self,
        output_path: Optional[str] = None,
        **query_params
    ) -> str:
        query = HealthDataQuery()
        all_data = []
        page = 1
        page_size = 1000

        while True:
            params = query_params.copy()
            params["page"] = page
            params["page_size"] = page_size
            data, total = query.query_health_data(**params)
            all_data.extend(data)
            if len(data) < page_size or len(all_data) >= total:
                break
            page += 1

        df = pd.DataFrame(all_data)

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/exports/health_data_{timestamp}.xlsx"

        column_mapping = {
            "id": "ID",
            "employee_id": "员工ID",
            "employee_name": "员工姓名",
            "employee_no": "工号",
            "department": "部门",
            "data_date": "数据日期",
            "data_source": "数据来源",
            "heart_rate": "心率",
            "heart_rate_resting": "静息心率",
            "steps": "步数",
            "sleep_duration": "睡眠时长(小时)",
            "deep_sleep": "深睡时长(小时)",
            "sleep_score": "睡眠评分",
            "systolic_bp": "收缩压",
            "diastolic_bp": "舒张压",
            "blood_oxygen": "血氧饱和度(%)",
            "stress_level": "压力水平",
            "is_anomaly": "是否异常",
            "created_at": "创建时间"
        }

        df = df.rename(columns=column_mapping)

        columns_to_keep = [v for v in column_mapping.values() if v in df.columns]
        df = df[columns_to_keep]

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='健康数据', index=False)

            summary_df = self._create_summary_sheet(all_data)
            summary_df.to_excel(writer, sheet_name='数据汇总', index=False)

        log_audit(
            user="system",
            action="export_health_data",
            detail=f"导出健康数据Excel: {output_path}, 共{len(all_data)}条记录"
        )

        logger.info(f"健康数据导出完成: {output_path}, {len(all_data)}条记录")
        return output_path

    def export_tickets_to_excel(
        self,
        output_path: Optional[str] = None,
        **query_params
    ) -> str:
        query = AlertTicketQuery()
        all_data = []
        page = 1
        page_size = 1000

        while True:
            params = query_params.copy()
            params["page"] = page
            params["page_size"] = page_size
            data, total = query.query_tickets(**params)
            all_data.extend(data)
            if len(data) < page_size or len(all_data) >= total:
                break
            page += 1

        df = pd.DataFrame(all_data)

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/exports/alert_tickets_{timestamp}.xlsx"

        column_mapping = {
            "id": "工单ID",
            "ticket_no": "工单号",
            "employee_id": "员工ID",
            "employee_name": "员工姓名",
            "employee_no": "工号",
            "department": "部门",
            "alert_type": "预警类型",
            "severity": "严重程度",
            "metric_name_cn": "指标名称",
            "current_value": "当前值",
            "baseline_value": "基线值",
            "deviation_percent": "偏离幅度(%)",
            "title": "标题",
            "description": "描述",
            "personal_advice": "个性化建议",
            "assigned_admin": "分配管理员",
            "status": "状态",
            "follow_up_result": "回访结果",
            "follow_up_time": "回访时间",
            "follow_up_by": "回访人",
            "created_at": "创建时间"
        }

        df = df.rename(columns=column_mapping)

        columns_to_keep = [v for v in column_mapping.values() if v in df.columns]
        df = df[columns_to_keep]

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='预警工单', index=False)

            stats = query.get_ticket_statistics(
                department_id=query_params.get("department_id"),
                start_date=query_params.get("start_date"),
                end_date=query_params.get("end_date")
            )
            stats_df = self._stats_to_dataframe(stats)
            stats_df.to_excel(writer, sheet_name='统计汇总', index=False)

        log_audit(
            user="system",
            action="export_alert_tickets",
            detail=f"导出预警工单Excel: {output_path}, 共{len(all_data)}条记录"
        )

        logger.info(f"预警工单导出完成: {output_path}, {len(all_data)}条记录")
        return output_path

    def export_employee_health_report(
        self,
        employee_id: int,
        output_path: Optional[str] = None
    ) -> str:
        with get_db_context() as db:
            employee = db.query(Employee).filter(Employee.id == employee_id).first()
            if not employee:
                raise ValueError(f"员工不存在")

            end_date = date.today()
            start_date = end_date - timedelta(days=90)

            health_data = db.query(HealthData).filter(
                HealthData.employee_id == employee_id,
                HealthData.data_date >= start_date,
                HealthData.data_date <= end_date
            ).order_by(HealthData.data_date).all()

            tickets = db.query(AlertTicket).filter(
                AlertTicket.employee_id == employee_id,
                AlertTicket.created_at >= start_date
            ).order_by(AlertTicket.created_at.desc()).all()

            medical_reports = db.query(MedicalReport).filter(
                MedicalReport.employee_id == employee_id
            ).order_by(MedicalReport.report_date.desc()).all()

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/exports/employee_{employee_id}_health_report_{timestamp}.xlsx"

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            info_df = pd.DataFrame([
                {"项目": "员工姓名", "信息": employee.name},
                {"项目": "工号", "信息": employee.employee_no},
                {"项目": "部门", "信息": employee.department.name if employee.department else ""},
                {"项目": "职位", "信息": employee.position},
                {"项目": "年龄", "信息": employee.age},
                {"项目": "报告周期", "信息": f"{start_date.isoformat()} 至 {end_date.isoformat()}"}
            ])
            info_df.to_excel(writer, sheet_name='员工信息', index=False)

            health_df = pd.DataFrame([{
                "数据日期": hd.data_date.isoformat(),
                "心率": hd.heart_rate,
                "静息心率": hd.heart_rate_resting,
                "步数": hd.steps,
                "睡眠时长(小时)": hd.sleep_duration,
                "深睡时长(小时)": hd.deep_sleep,
                "睡眠评分": hd.sleep_score,
                "是否异常": "是" if hd.is_anomaly else "否"
            } for hd in health_data])
            health_df.to_excel(writer, sheet_name='健康数据', index=False)

            ticket_df = pd.DataFrame([{
                "工单号": t.ticket_no,
                "预警类型": t.alert_type,
                "严重程度": t.severity,
                "指标": METRIC_NAMES_CN.get(t.metric_name, t.metric_name),
                "当前值": t.current_value,
                "基线值": t.baseline_value,
                "偏离(%)": t.deviation_percent,
                "状态": t.status,
                "创建时间": t.created_at.isoformat() if t.created_at else ""
            } for t in tickets])
            ticket_df.to_excel(writer, sheet_name='预警记录', index=False)

            report_df = pd.DataFrame([{
                "报告日期": r.report_date.isoformat() if r.report_date else "",
                "报告类型": r.report_type,
                "医院": r.hospital,
                "总结": r.overall_summary
            } for r in medical_reports])
            report_df.to_excel(writer, sheet_name='体检报告', index=False)

        log_audit(
            user="system",
            action="export_employee_report",
            detail=f"导出员工健康报告: {output_path}, 员工{employee_id}"
        )

        logger.info(f"员工健康报告导出完成: {output_path}")
        return output_path

    def export_department_weekly_report(
        self,
        department_id: int,
        report_week: str,
        output_path: Optional[str] = None
    ) -> str:
        with get_db_context() as db:
            report = db.query(WeeklyReport).filter(
                WeeklyReport.department_id == department_id,
                WeeklyReport.report_week == report_week
            ).first()

            if not report:
                raise ValueError(f"周报不存在")

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/exports/department_{department_id}_weekly_{report_week}_{timestamp}.xlsx"

        data = report.report_data or {}

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            summary_df = pd.DataFrame([
                {"指标": "员工总数", "数值": report.total_employees},
                {"指标": "活跃员工数", "数值": report.active_employees},
                {"指标": "异常记录数", "数值": report.anomaly_count},
                {"指标": "异常率(%)", "数值": report.anomaly_rate},
                {"指标": "平均步数", "数值": report.avg_steps},
                {"指标": "平均睡眠(小时)", "数值": report.avg_sleep_duration},
                {"指标": "平均心率", "数值": report.avg_heart_rate},
                {"指标": "体检参与率(%)", "数值": report.checkup_participation_rate},
                {"指标": "高危员工数", "数值": report.high_risk_count},
                {"指标": "中危员工数", "数值": report.medium_risk_count},
                {"指标": "低危员工数", "数值": report.low_risk_count}
            ])
            summary_df.to_excel(writer, sheet_name='汇总数据', index=False)

            if data.get('daily_anomaly_trend'):
                trend_df = pd.DataFrame(data['daily_anomaly_trend'])
                trend_df.columns = ['日期', '总记录数', '异常数', '异常率(%)']
                trend_df.to_excel(writer, sheet_name='每日趋势', index=False)

            if data.get('top_5_anomaly_employees'):
                top_df = pd.DataFrame(data['top_5_anomaly_employees'])
                top_df.columns = ['员工ID', '姓名', '工号', '预警总数', '高危预警数']
                top_df.to_excel(writer, sheet_name='预警TOP5', index=False)

        log_audit(
            user="system",
            action="export_department_weekly",
            detail=f"导出部门周报Excel: {output_path}, 部门{department_id}, 周{report_week}"
        )

        logger.info(f"部门周报导出完成: {output_path}")
        return output_path

    def _create_summary_sheet(self, data: List[Dict]) -> pd.DataFrame:
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        summary = []

        if 'department' in df.columns:
            dept_stats = df.groupby('department').agg({
                'is_anomaly': ['count', 'sum']}).reset_index()
            dept_stats.columns = ['部门', '总记录数', '异常数']
            dept_stats['异常率(%)'] = (dept_stats['异常数'] / dept_stats['总记录数'] * 100).round(2)
            summary.append(('按部门统计', dept_stats))

        if 'is_anomaly' in df.columns:
            anomaly_count = df['is_anomaly'].sum()
            total_count = len(df)
            anomaly_rate = round(anomaly_count / max(total_count, 1) * 100, 2)
            overall = pd.DataFrame([
                {'统计项': '总记录数', '数值': total_count},
                {'统计项': '异常记录数', '数值': anomaly_count},
                {'统计项': '异常率(%)', '数值': anomaly_rate}
            ])
            summary.append(('总体统计', overall))

        result = pd.DataFrame()
        for title, df_part in summary:
            result = pd.concat([result, pd.DataFrame([{0: ''}]), pd.DataFrame([{0: title}]), df_part], ignore_index=True)

        return result

    def _stats_to_dataframe(self, stats: Dict) -> pd.DataFrame:
        rows = []
        rows.append({'类别': '总体统计', '项目': '总工单数', '数值': stats['total']})

        for severity, count in stats.get('by_severity', {}).items():
            rows.append({'类别': '按严重程度', '项目': severity, '数值': count})

        for status, count in stats.get('by_status', {}).items():
            rows.append({'类别': '按状态', '项目': status, '数值': count})

        for metric, count in stats.get('by_metric', {}).items():
            rows.append({'类别': '按指标', '项目': metric, '数值': count})

        return pd.DataFrame(rows)


class OperationLogQuery:
    def query_operation_logs(
        self,
        operation_type: Optional[str] = None,
        operator: Optional[str] = None,
        target_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Dict], int]:
        with get_db_context() as db:
            query = db.query(OperationLog)

            if operation_type:
                query = query.filter(OperationLog.operation_type == operation_type)
            if operator:
                query = query.filter(OperationLog.operator.like(f'%{operator}%'))
            if target_type:
                query = query.filter(OperationLog.target_type == target_type)
            if start_date:
                query = query.filter(OperationLog.created_at >= start_date)
            if end_date:
                query = query.filter(OperationLog.created_at <= end_date + timedelta(days=1))

            total = query.count()
            logs = query.order_by(OperationLog.created_at.desc())\
                .offset((page - 1) * page_size)\
                .limit(page_size)\
                .all()

            results = []
            for log in logs:
                results.append({
                    "id": log.id,
                    "operation_type": log.operation_type,
                    "operator": log.operator,
                    "target_type": log.target_type,
                    "target_id": log.target_id,
                    "action": log.action,
                    "detail": log.detail,
                    "ip_address": log.ip_address,
                    "created_at": log.created_at.isoformat() if log.created_at else ""
                })

            return results, total

    def export_logs_to_excel(
        self,
        output_path: Optional[str] = None,
        **query_params
    ) -> str:
        all_data = []
        page = 1
        page_size = 1000

        while True:
            params = query_params.copy()
            params["page"] = page
            params["page_size"] = page_size
            data, total = self.query_operation_logs(**params)
            all_data.extend(data)
            if len(data) < page_size or len(all_data) >= total:
                break
            page += 1

        df = pd.DataFrame(all_data)

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/exports/operation_logs_{timestamp}.xlsx"

        column_mapping = {
            "id": "ID",
            "operation_type": "操作类型",
            "operator": "操作人",
            "target_type": "目标类型",
            "target_id": "目标ID",
            "action": "操作动作",
            "detail": "详情",
            "ip_address": "IP地址",
            "created_at": "操作时间"
        }

        df = df.rename(columns=column_mapping)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='操作日志', index=False)

        logger.info(f"操作日志导出完成: {output_path}, {len(all_data)}条记录")
        return output_path


def get_health_data_query() -> HealthDataQuery:
    return HealthDataQuery()


def get_alert_ticket_query() -> AlertTicketQuery:
    return AlertTicketQuery()


def get_excel_exporter() -> ExcelExporter:
    return ExcelExporter()


def get_operation_log_query() -> OperationLogQuery:
    return OperationLogQuery()
