import os
import json
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from collections import defaultdict
import pandas as pd
import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
sns.set_style("whitegrid")
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

from .database import get_db_context
from .models import (
    Employee, Department, HealthData, AlertTicket,
    WeeklyReport, HealthProfile, MedicalReport
)
from .logging_config import get_logger, log_audit
from .alert_ticket import TicketStatus, AlertSeverity
from .anomaly_detection import MetricType
from .config import get_settings
from .medical_report import get_medical_report_manager

settings = get_settings()
logger = get_logger(__name__)

os.makedirs("data/reports", exist_ok=True)
os.makedirs("data/charts", exist_ok=True)


class WeeklyReportGenerator:
    def __init__(self):
        self.report_manager = get_medical_report_manager()

    def get_week_range(self, report_date: Optional[date] = None) -> Tuple[date, date, str]:
        report_date = report_date or date.today()
        end_date = report_date - timedelta(days=1)
        start_date = end_date - timedelta(days=6)
        week_str = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"
        return start_date, end_date, week_str

    def generate_all_department_reports(
        self,
        report_date: Optional[date] = None
    ) -> Tuple[int, int]:
        report_date = report_date or date.today()
        start_date, end_date, week_str = self.get_week_range(report_date)

        with get_db_context() as db:
            departments = db.query(Department).all()

        total = len(departments)
        success = 0

        for dept in departments:
            try:
                report = self.generate_department_report(
                    department_id=dept.id,
                    start_date=start_date,
                    end_date=end_date,
                    week_str=week_str
                )
                if report:
                    success += 1
            except Exception as e:
                logger.error(f"生成部门{dept.id}周报失败: {str(e)}")

        self._generate_company_summary_report(start_date, end_date, week_str)

        logger.info(f"周报生成完成: {success}/{total}个部门")
        return total, success

    def generate_department_report(
        self,
        department_id: int,
        start_date: date,
        end_date: date,
        week_str: str
    ) -> Optional[WeeklyReport]:
        with get_db_context() as db:
            department = db.query(Department).filter(Department.id == department_id).first()
            if not department:
                return None

            existing = db.query(WeeklyReport).filter(
                WeeklyReport.department_id == department_id,
                WeeklyReport.report_week == week_str
            ).first()

            if existing:
                return existing

            employees = db.query(Employee).filter(
                Employee.department_id == department_id,
                Employee.is_active == True
            ).all()
            employee_ids = [e.id for e in employees]

            total_employees = len(employees)

            health_data = db.query(HealthData).filter(
                HealthData.employee_id.in_(employee_ids),
                HealthData.data_date >= start_date,
                HealthData.data_date <= end_date
            ).all()

            alert_tickets = db.query(AlertTicket).filter(
                AlertTicket.employee_id.in_(employee_ids),
                AlertTicket.created_at >= start_date,
                AlertTicket.created_at <= end_date + timedelta(days=1)
            ).all()

            health_profiles = db.query(HealthProfile).filter(
                HealthProfile.employee_id.in_(employee_ids)
            ).all()

            anomaly_count = sum(1 for d in health_data if d.is_anomaly)
            active_days_data = defaultdict(set)
            for d in health_data:
                active_days_data[d.employee_id].add(d.data_date)
            active_employees = len([e for e in employee_ids if len(active_days_data.get(e, [])) >= 3])

            anomaly_rate = round(anomaly_count / max(len(health_data), 1) * 100, 2) if health_data else 0

            heart_rate_anomalies = 0
            sleep_anomalies = 0
            steps_anomalies = 0

            for ticket in alert_tickets:
                if ticket.metric_name in [MetricType.HEART_RATE, MetricType.HEART_RATE_RESTING]:
                    heart_rate_anomalies += 1
                elif ticket.metric_name in [MetricType.SLEEP_DURATION, MetricType.DEEP_SLEEP, MetricType.SLEEP_SCORE]:
                    sleep_anomalies += 1
                elif ticket.metric_name == MetricType.STEPS:
                    steps_anomalies += 1

            avg_steps = np.mean([d.steps for d in health_data if d.steps]) if health_data else 0
            avg_sleep = np.mean([d.sleep_duration for d in health_data if d.sleep_duration]) if health_data else 0
            avg_heart_rate = np.mean([d.heart_rate for d in health_data if d.heart_rate]) if health_data else 0

            report_stats = self.report_manager.get_report_statistics(
                department_id=department_id,
                start_date=start_date - timedelta(days=30),
                end_date=end_date
            )

            high_risk = sum(1 for p in health_profiles if p.risk_level == "high")
            medium_risk = sum(1 for p in health_profiles if p.risk_level == "medium")
            low_risk = sum(1 for p in health_profiles if p.risk_level == "low")

            alerts_resolved = sum(1 for t in alert_tickets if t.status == TicketStatus.RESOLVED)
            alerts_pending = sum(1 for t in alert_tickets if t.status in [
                TicketStatus.PENDING, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS
            ])

            chart_paths = self._generate_department_charts(
                department_id=department_id,
                department_name=department.name,
                start_date=start_date,
                end_date=end_date,
                health_data=health_data,
                alert_tickets=alert_tickets
            )

            report_data = {
                "department_name": department.name,
                "period": f"{start_date.isoformat()} 至 {end_date.isoformat()}",
                "daily_anomaly_trend": self._get_daily_anomaly_trend(health_data, start_date, end_date),
                "top_5_anomaly_employees": self._get_top_anomaly_employees(alert_tickets),
                "metric_averages": {
                    "avg_steps": round(float(avg_steps), 1),
                    "avg_sleep": round(float(avg_sleep), 2),
                    "avg_heart_rate": round(float(avg_heart_rate), 1),
                },
                "risk_distribution": {
                    "high": high_risk,
                    "medium": medium_risk,
                    "low": low_risk,
                    "normal": total_employees - high_risk - medium_risk - low_risk
                }
            }

            report = WeeklyReport(
                department_id=department_id,
                report_week=week_str,
                start_date=start_date,
                end_date=end_date,
                total_employees=total_employees,
                active_employees=active_employees,
                anomaly_count=anomaly_count,
                anomaly_rate=anomaly_rate,
                heart_rate_anomalies=heart_rate_anomalies,
                sleep_anomalies=sleep_anomalies,
                steps_anomalies=steps_anomalies,
                avg_steps=round(float(avg_steps), 1),
                avg_sleep_duration=round(float(avg_sleep), 2),
                avg_heart_rate=round(float(avg_heart_rate), 1),
                checkup_participation_rate=report_stats["participation_rate"],
                checkup_count=report_stats["participated_employees"],
                high_risk_count=high_risk,
                medium_risk_count=medium_risk,
                low_risk_count=low_risk,
                alerts_resolved=alerts_resolved,
                alerts_pending=alerts_pending,
                report_data=report_data,
                chart_paths=chart_paths,
                sent=False
            )

            db.add(report)
            db.commit()
            db.refresh(report)

            self._save_report_html(report, department.name)

            log_audit(
                user="system",
                action="generate_weekly_report",
                detail=f"生成部门{department.name}周报: {week_str}"
            )

            return report

    def _generate_company_summary_report(
        self,
        start_date: date,
        end_date: date,
        week_str: str
    ):
        with get_db_context() as db:
            reports = db.query(WeeklyReport).filter(
                WeeklyReport.report_week == week_str
            ).all()

            if not reports:
                return

            summary = {
                "report_week": week_str,
                "period": f"{start_date.isoformat()} 至 {end_date.isoformat()}",
                "generated_at": datetime.now().isoformat(),
                "total_departments": len(reports),
                "total_employees": sum(r.total_employees for r in reports),
                "total_anomalies": sum(r.anomaly_count for r in reports),
                "company_avg_anomaly_rate": round(np.mean([r.anomaly_rate for r in reports]), 2),
                "company_avg_steps": round(np.mean([r.avg_steps for r in reports if r.avg_steps]), 1),
                "company_avg_sleep": round(np.mean([r.avg_sleep_duration for r in reports if r.avg_sleep_duration]), 2),
                "department_anomaly_rates": [
                    {
                        "department_id": r.department_id,
                        "department_name": r.department.name if r.department else "",
                        "anomaly_rate": r.anomaly_rate,
                        "anomaly_count": r.anomaly_count
                    } for r in reports
                ],
                "department_risk_distribution": [
                    {
                        "department_id": r.department_id,
                        "department_name": r.department.name if r.department else "",
                        "high_risk": r.high_risk_count,
                        "medium_risk": r.medium_risk_count,
                        "low_risk": r.low_risk_count
                    } for r in reports
                ],
                "total_alerts_resolved": sum(r.alerts_resolved for r in reports),
                "total_alerts_pending": sum(r.alerts_pending for r in reports),
                "avg_checkup_participation": round(np.mean([r.checkup_participation_rate for r in reports]), 2)
            }

            self._generate_company_charts(reports, week_str)

            summary_path = f"data/reports/company_summary_{week_str}.json"
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            logger.info(f"公司汇总报告已生成: {summary_path}")

    def _generate_department_charts(
        self,
        department_id: int,
        department_name: str,
        start_date: date,
        end_date: date,
        health_data: List[HealthData],
        alert_tickets: List[AlertTicket]
    ) -> Dict[str, str]:
        chart_paths = {}
        date_range = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]

        daily_data = defaultdict(lambda: {"anomalies": 0, "total": 0, "steps": [], "sleep": []})
        for d in health_data:
            day = d.data_date
            daily_data[day]["total"] += 1
            if d.is_anomaly:
                daily_data[day]["anomalies"] += 1
            if d.steps:
                daily_data[day]["steps"].append(d.steps)
            if d.sleep_duration:
                daily_data[day]["sleep"].append(d.sleep_duration)

        anomaly_counts = [daily_data[d]["anomalies"] for d in date_range]
        avg_steps = [np.mean(daily_data[d]["steps"]) if daily_data[d]["steps"] else 0 for d in date_range]
        avg_sleep = [np.mean(daily_data[d]["sleep"]) if daily_data[d]["sleep"] else 0 for d in date_range]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

        dates_str = [d.strftime("%m-%d") for d in date_range]

        ax1.bar(dates_str, anomaly_counts, color='salmon', alpha=0.7, label='异常数量')
        ax1.set_title(f'{department_name} - 每日异常趋势', fontsize=14, fontweight='bold')
        ax1.set_ylabel('异常数量')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        ax3 = ax1.twinx()
        ax3.plot(dates_str, [c / max(t, 1) * 100 for c, t in zip(
            anomaly_counts, [daily_data[d]["total"] for d in date_range]
        )], color='red', marker='o', label='异常率(%)')
        ax3.set_ylabel('异常率(%)')
        ax3.legend(loc='upper right')

        ax2.plot(dates_str, avg_steps, color='blue', marker='s', label='平均步数', linewidth=2)
        ax4 = ax2.twinx()
        ax4.plot(dates_str, avg_sleep, color='green', marker='^', label='平均睡眠(h)', linewidth=2)

        ax2.set_title(f'{department_name} - 平均步数与睡眠时长', fontsize=14, fontweight='bold')
        ax2.set_xlabel('日期')
        ax2.set_ylabel('平均步数')
        ax4.set_ylabel('平均睡眠时长(小时)')

        lines1, labels1 = ax2.get_legend_handles_labels()
        lines2, labels2 = ax4.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        trend_path = f"data/charts/dept_{department_id}_trend_{start_date.strftime('%Y%m%d')}.png"
        plt.savefig(trend_path, dpi=300, bbox_inches='tight')
        plt.close()
        chart_paths["trend"] = trend_path

        severity_counts = defaultdict(int)
        for ticket in alert_tickets:
            severity_counts[ticket.severity] += 1

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        labels = ['低', '中', '高', '危急']
        values = [
            severity_counts.get(AlertSeverity.LOW, 0),
            severity_counts.get(AlertSeverity.MEDIUM, 0),
            severity_counts.get(AlertSeverity.HIGH, 0),
            severity_counts.get(AlertSeverity.CRITICAL, 0)
        ]
        colors = ['#90EE90', '#FFD700', '#FFA500', '#FF4444']

        ax1.pie(values, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        ax1.set_title('预警严重程度分布', fontsize=12, fontweight='bold')

        metric_counts = defaultdict(int)
        for ticket in alert_tickets:
            metric_counts[ticket.metric_name] += 1

        if metric_counts:
            metrics = sorted(metric_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            metric_names = [m[0] for m in metrics]
            metric_values = [m[1] for m in metrics]

            ax2.barh(metric_names, metric_values, color='skyblue')
            ax2.set_title('异常指标分布Top5', fontsize=12, fontweight='bold')
            ax2.set_xlabel('数量')
        else:
            ax2.text(0.5, 0.5, '无异常数据', ha='center', va='center', fontsize=14)
            ax2.set_title('异常指标分布Top5', fontsize=12, fontweight='bold')

        plt.tight_layout()
        severity_path = f"data/charts/dept_{department_id}_severity_{start_date.strftime('%Y%m%d')}.png"
        plt.savefig(severity_path, dpi=300, bbox_inches='tight')
        plt.close()
        chart_paths["severity"] = severity_path

        logger.info(f"部门{department_id}图表已生成: {list(chart_paths.keys())}")
        return chart_paths

    def _generate_company_charts(self, reports: List[WeeklyReport], week_str: str):
        if not reports:
            return

        dept_names = [r.department.name if r.department else f"部门{r.department_id}" for r in reports]
        anomaly_rates = [r.anomaly_rate for r in reports]
        avg_steps = [r.avg_steps for r in reports]
        avg_sleep = [r.avg_sleep_duration for r in reports]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12))

        y_pos = np.arange(len(dept_names))
        ax1.barh(y_pos, anomaly_rates, color='salmon', alpha=0.7)
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(dept_names)
        ax1.set_xlabel('异常率(%)')
        ax1.set_title('各部门异常率对比', fontsize=14, fontweight='bold')
        ax1.axvline(x=np.mean(anomaly_rates), color='red', linestyle='--', label=f'公司均值: {np.mean(anomaly_rates):.1f}%')
        ax1.legend()
        ax1.grid(True, alpha=0.3, axis='x')

        x = np.arange(len(dept_names))
        width = 0.35
        ax2.bar(x - width/2, [s / 1000 for s in avg_steps], width, label='平均步数(千)', color='skyblue')
        ax3 = ax2.twinx()
        ax3.bar(x + width/2, avg_sleep, width, label='平均睡眠(h)', color='lightgreen')

        ax2.set_xticks(x)
        ax2.set_xticklabels(dept_names, rotation=45, ha='right')
        ax2.set_ylabel('平均步数(千)')
        ax3.set_ylabel('平均睡眠时长(小时)')
        ax2.set_title('各部门健康指标对比', fontsize=14, fontweight='bold')

        lines1, labels1 = ax2.get_legend_handles_labels()
        lines2, labels2 = ax3.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        chart_path = f"data/charts/company_comparison_{week_str}.png"
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"公司汇总图表已生成: {chart_path}")

    def _get_daily_anomaly_trend(
        self,
        health_data: List[HealthData],
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        date_range = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        trend = []

        for d in date_range:
            day_data = [hd for hd in health_data if hd.data_date == d]
            total = len(day_data)
            anomalies = sum(1 for hd in day_data if hd.is_anomaly)
            trend.append({
                "date": d.isoformat(),
                "total": total,
                "anomalies": anomalies,
                "anomaly_rate": round(anomalies / max(total, 1) * 100, 2)
            })

        return trend

    def _get_top_anomaly_employees(self, alert_tickets: List[AlertTicket]) -> List[Dict]:
        employee_counts = defaultdict(lambda: {"count": 0, "high_count": 0, "name": "", "employee_no": ""})

        for ticket in alert_tickets:
            emp_id = ticket.employee_id
            employee_counts[emp_id]["count"] += 1
            if ticket.severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL]:
                employee_counts[emp_id]["high_count"] += 1
            if ticket.employee:
                employee_counts[emp_id]["name"] = ticket.employee.name
                employee_counts[emp_id]["employee_no"] = ticket.employee.employee_no

        sorted_employees = sorted(
            employee_counts.items(),
            key=lambda x: (-x[1]["count"], -x[1]["high_count"])
        )[:5]

        return [
            {
                "employee_id": emp_id,
                "name": data["name"],
                "employee_no": data["employee_no"],
                "total_alerts": data["count"],
                "high_severity_alerts": data["high_count"]
            }
            for emp_id, data in sorted_employees
        ]

    def _save_report_html(self, report: WeeklyReport, department_name: str):
        html_content = self._generate_report_html(report, department_name)
        report_path = f"data/reports/report_{report.id}_{report.report_week}.html"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    def _generate_report_html(self, report: WeeklyReport, department_name: str) -> str:
        data = report.report_data or {}
        chart_paths = report.chart_paths or {}

        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>健康周报 - {department_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ text-align: center; background: #f0f8ff; padding: 20px; border-radius: 10px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
        .stat-card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
        .stat-label {{ font-size: 12px; color: #7f8c8d; }}
        .high {{ color: #e74c3c; }}
        .medium {{ color: #f39c12; }}
        .low {{ color: #27ae60; }}
        .chart-container {{ margin: 30px 0; text-align: center; }}
        .chart-container img {{ max-width: 100%; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; }}
        tr:hover {{ background: #f9f9f9; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 {department_name} 健康周报</h1>
        <p>统计周期: {data.get('period', '')}</p>
        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value">{report.total_employees}</div>
            <div class="stat-label">员工总数</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.anomaly_count}</div>
            <div class="stat-label">异常记录数</div>
        </div>
        <div class="stat-card">
            <div class="stat-value {'high' if report.anomaly_rate > 15 else 'medium' if report.anomaly_rate > 8 else 'low'}">{report.anomaly_rate}%</div>
            <div class="stat-label">异常率</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.checkup_participation_rate}%</div>
            <div class="stat-label">体检参与率</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.avg_steps:,.0f}</div>
            <div class="stat-label">平均步数</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.avg_sleep_duration:.1f}h</div>
            <div class="stat-label">平均睡眠</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.avg_heart_rate}</div>
            <div class="stat-label">平均心率</div>
        </div>
        <div class="stat-card">
            <div class="stat-value high">{report.high_risk_count}</div>
            <div class="stat-label">高危员工</div>
        </div>
    </div>

    <h2>📈 趋势图表</h2>
    <div class="chart-container">
        <img src="{chart_paths.get('trend', '')}" alt="趋势图">
    </div>
    <div class="chart-container">
        <img src="{chart_paths.get('severity', '')}" alt="严重程度分布图">
    </div>

    <h2>⚠️ 预警分布</h2>
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value">{report.heart_rate_anomalies}</div>
            <div class="stat-label">心率异常</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.sleep_anomalies}</div>
            <div class="stat-label">睡眠异常</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.steps_anomalies}</div>
            <div class="stat-label">步数异常</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.alerts_resolved}/{report.alerts_resolved + report.alerts_pending}</div>
            <div class="stat-label">已处理/总数</div>
        </div>
    </div>

    <h2>🔔 预警最多员工 Top 5</h2>
    <table>
        <tr>
            <th>排名</th>
            <th>员工姓名</th>
            <th>工号</th>
            <th>预警总数</th>
            <th>高危预警</th>
        </tr>
        """

        for i, emp in enumerate(data.get('top_5_anomaly_employees', []), 1):
            html += f"""
        <tr>
            <td>{i}</td>
            <td>{emp['name']}</td>
            <td>{emp['employee_no']}</td>
            <td>{emp['total_alerts']}</td>
            <td class="high">{emp['high_severity_alerts']}</td>
        </tr>
            """

        html += f"""
    </table>

    <h2>🎯 风险分布</h2>
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value high">{report.high_risk_count}</div>
            <div class="stat-label">高风险</div>
        </div>
        <div class="stat-card">
            <div class="stat-value medium">{report.medium_risk_count}</div>
            <div class="stat-label">中风险</div>
        </div>
        <div class="stat-card">
            <div class="stat-value low">{report.low_risk_count}</div>
            <div class="stat-label">低风险</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.total_employees - report.high_risk_count - report.medium_risk_count - report.low_risk_count}</div>
            <div class="stat-label">正常</div>
        </div>
    </div>

    <footer style="text-align: center; margin-top: 50px; color: #999; font-size: 12px;">
        <p>本报告由员工健康管理系统自动生成</p>
    </footer>
</body>
</html>
        """
        return html

    def send_reports(self, week_str: str):
        with get_db_context() as db:
            reports = db.query(WeeklyReport).filter(
                WeeklyReport.report_week == week_str,
                WeeklyReport.sent == False
            ).all()

            for report in reports:
                sent = self._send_report_to_hr(report)
                if sent:
                    report.sent = True
                    report.sent_to = settings.HR_EMAIL
                    report.sent_at = datetime.now()
                    db.commit()

                    log_audit(
                        "发送周报",
                        f"发送周报给 {settings.HR_EMAIL}: {report.report_week}",
                        "system"
                    )

            logger.info(f"已发送周报: {len(reports)}份")

    def _send_report_to_hr(self, report: WeeklyReport) -> bool:
        logger.info(f"[模拟] 发送周报给 {settings.HR_EMAIL}: 部门{report.department_id}, 周{report.report_week}")
        return True


def get_weekly_report_generator() -> WeeklyReportGenerator:
    return WeeklyReportGenerator()
