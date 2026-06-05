import uuid
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from collections import defaultdict

from .database import get_db_context
from .models import (
    Employee, HealthData, HealthAdmin, AlertTicket,
    FollowUpRecord, HealthProfile, Department
)
from .logging_config import get_logger, log_alert, log_audit
from .anomaly_detection import AlertSeverity, MetricType, METRIC_NAMES_CN, AnomalyDirection
from .config import get_settings

settings = get_settings()
logger = get_logger(__name__)


class TicketStatus:
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    FOLLOWED_UP = "followed_up"
    RESOLVED = "resolved"
    CLOSED = "closed"


PERSONAL_ADVICE_TEMPLATES = {
    (MetricType.HEART_RATE, AnomalyDirection.HIGH, AlertSeverity.LOW): [
        "您的心率略高于正常水平，建议适当休息，避免剧烈运动，多喝水。",
        "心率偏高，建议放松心情，做几次深呼吸，避免咖啡因摄入。",
    ],
    (MetricType.HEART_RATE, AnomalyDirection.HIGH, AlertSeverity.MEDIUM): [
        "您的心率持续偏高，建议减少工作强度，适当午休，保证充足睡眠。",
        "心率明显偏高，建议监测血压，避免情绪激动，必要时就医检查。",
    ],
    (MetricType.HEART_RATE, AnomalyDirection.HIGH, AlertSeverity.HIGH): [
        "⚠️ 心率显著偏高，请立即停止工作，静坐休息，建议尽快就医检查心电图。",
        "⚠️ 严重心率异常，请立即休息并联系健康管理员，建议尽快进行心血管检查。",
    ],
    (MetricType.HEART_RATE, AnomalyDirection.HIGH, AlertSeverity.CRITICAL): [
        "🚨 危急！心率异常偏高，请立即就医，拨打急救电话或联系紧急联系人。",
    ],
    (MetricType.HEART_RATE, AnomalyDirection.LOW, AlertSeverity.LOW): [
        "您的心率略低，如无不适症状可正常活动，建议定期监测。",
    ],
    (MetricType.HEART_RATE, AnomalyDirection.LOW, AlertSeverity.MEDIUM): [
        "心率偏低，建议适当增加轻度运动，如散步、瑜伽等。",
        "心率明显偏低，建议就医检查心脏功能。",
    ],
    (MetricType.HEART_RATE, AnomalyDirection.LOW, AlertSeverity.HIGH): [
        "⚠️ 心率显著偏低，请避免突然站立，建议尽快就医检查。",
    ],
    (MetricType.HEART_RATE, AnomalyDirection.LOW, AlertSeverity.CRITICAL): [
        "🚨 危急！心率异常偏低，请立即就医。",
    ],
    (MetricType.STEPS, AnomalyDirection.LOW, AlertSeverity.LOW): [
        "今天的步数偏少，建议饭后散步，活动一下身体。",
        "运动量不足，建议利用午休时间走一走。",
    ],
    (MetricType.STEPS, AnomalyDirection.LOW, AlertSeverity.MEDIUM): [
        "连续运动量明显不足，建议每天安排30分钟运动时间。",
        "步数偏低，建议参加公司的健身活动，增加日常活动量。",
    ],
    (MetricType.STEPS, AnomalyDirection.LOW, AlertSeverity.HIGH): [
        "⚠️ 严重缺乏运动，请制定运动计划，每天至少步行30分钟。",
    ],
    (MetricType.SLEEP_DURATION, AnomalyDirection.LOW, AlertSeverity.LOW): [
        "昨晚睡眠稍短，建议今晚早点休息，保证充足睡眠。",
        "睡眠时长不足，建议减少睡前使用电子设备。",
    ],
    (MetricType.SLEEP_DURATION, AnomalyDirection.LOW, AlertSeverity.MEDIUM): [
        "睡眠明显不足，建议调整作息，每晚11点前入睡。",
        "连续睡眠不足，影响工作效率和健康，建议改善睡眠环境。",
    ],
    (MetricType.SLEEP_DURATION, AnomalyDirection.LOW, AlertSeverity.HIGH): [
        "⚠️ 严重睡眠不足，请立即调整作息，必要时可申请休假调整。",
        "⚠️ 睡眠严重不足，建议就医咨询睡眠问题。",
    ],
    (MetricType.SLEEP_DURATION, AnomalyDirection.LOW, AlertSeverity.CRITICAL): [
        "🚨 危急！严重睡眠不足，请立即休息并就医。",
    ],
    (MetricType.SLEEP_DURATION, AnomalyDirection.HIGH, AlertSeverity.LOW): [
        "睡眠时间较长，如感疲惫建议适当增加白天活动量。",
    ],
    (MetricType.DEEP_SLEEP, AnomalyDirection.LOW, AlertSeverity.LOW): [
        "深睡时长稍短，建议睡前放松，避免咖啡因。",
    ],
    (MetricType.DEEP_SLEEP, AnomalyDirection.LOW, AlertSeverity.MEDIUM): [
        "深睡明显不足，建议改善睡眠质量，保持规律作息。",
    ],
    (MetricType.SLEEP_SCORE, AnomalyDirection.LOW, AlertSeverity.LOW): [
        "睡眠质量一般，建议睡前放松，保持卧室安静舒适。",
    ],
    (MetricType.SLEEP_SCORE, AnomalyDirection.LOW, AlertSeverity.MEDIUM): [
        "睡眠质量较差，建议调整作息时间和睡眠环境。",
    ],
    (MetricType.BLOOD_OXYGEN, AnomalyDirection.LOW, AlertSeverity.LOW): [
        "血氧略低，建议多做深呼吸，保持室内通风。",
    ],
    (MetricType.BLOOD_OXYGEN, AnomalyDirection.LOW, AlertSeverity.MEDIUM): [
        "血氧偏低，建议增加户外活动，必要时就医检查。",
    ],
    (MetricType.BLOOD_OXYGEN, AnomalyDirection.LOW, AlertSeverity.HIGH): [
        "⚠️ 血氧显著偏低，请立即就医检查。",
    ],
    (MetricType.STRESS_LEVEL, AnomalyDirection.HIGH, AlertSeverity.LOW): [
        "压力略高，建议工作间隙适当放松，听听音乐。",
    ],
    (MetricType.STRESS_LEVEL, AnomalyDirection.HIGH, AlertSeverity.MEDIUM): [
        "压力较高，建议适当运动，与朋友家人交流。",
    ],
    (MetricType.STRESS_LEVEL, AnomalyDirection.HIGH, AlertSeverity.HIGH): [
        "⚠️ 压力过高，建议寻求心理咨询帮助。",
    ],
}

SEVERITY_ORDER = [AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH, AlertSeverity.CRITICAL]


class AlertTicketManager:
    def generate_ticket_no(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d")
        uuid_part = str(uuid.uuid4().hex[:8]).upper()
        return f"ALT-{timestamp}-{uuid_part}"

    def generate_tickets_from_anomalies(self, data_date: Optional[date] = None) -> Tuple[int, int]:
        data_date = data_date or date.today()
        tickets_created = 0
        tickets_total = 0

        with get_db_context() as db:
            anomalous_data = db.query(HealthData).filter(
                HealthData.data_date == data_date,
                HealthData.is_anomaly == True
            ).all()

            for health_data in anomalous_data:
                if not health_data.anomaly_details or "anomalies" not in health_data.anomaly_details:
                    continue

                anomalies = health_data.anomaly_details["anomalies"]
                tickets_total += len(anomalies)

                for anomaly in anomalies:
                    try:
                        ticket = self._create_ticket_from_anomaly(
                            employee_id=health_data.employee_id,
                            health_data=health_data,
                            anomaly=anomaly,
                            db=db
                        )
                        if ticket:
                            tickets_created += 1
                    except Exception as e:
                        logger.error(f"创建工单失败 - 员工{health_data.employee_id}, 异常{anomaly}: {e}")

            db.commit()

        logger.info(f"工单生成完成: 应创建{tickets_total}张, 成功创建{tickets_created}张")
        return tickets_total, tickets_created

    def _create_ticket_from_anomaly(
        self,
        employee_id: int,
        health_data: HealthData,
        anomaly: Dict,
        db: Session
    ) -> Optional[AlertTicket]:
        existing = db.query(AlertTicket).filter(
            AlertTicket.employee_id == employee_id,
            AlertTicket.metric_name == anomaly["metric_name"],
            AlertTicket.health_data_id == health_data.id
        ).first()

        if existing:
            return None

        employee = db.query(Employee).filter(Employee.id == employee_id).first()
        if not employee:
            return None

        metric_name = anomaly["metric_name"]
        metric_name_cn = anomaly["metric_name_cn"]
        severity = anomaly["severity"]
        direction = anomaly["direction"]
        current_value = anomaly["current_value"]
        baseline_value = anomaly["baseline_value"]
        deviation_percent = anomaly["deviation_percent"]
        threshold = anomaly["threshold"]

        if direction == AnomalyDirection.HIGH:
            alert_type = f"{metric_name_cn}偏高"
            direction_cn = "偏高"
        else:
            alert_type = f"{metric_name_cn}偏低"
            direction_cn = "偏低"

        if severity == AlertSeverity.CRITICAL:
            title_prefix = "【危急】"
        elif severity == AlertSeverity.HIGH:
            title_prefix = "【高危】"
        elif severity == AlertSeverity.MEDIUM:
            title_prefix = "【注意】"
        else:
            title_prefix = "【提醒】"

        title = f"{title_prefix}{employee.name} - {alert_type}"

        description = (
            f"员工{employee.name}（工号：{employee.employee_no}）"
            f"{metric_name_cn}{direction_cn}。\n"
            f"当前值：{current_value}，基线值：{baseline_value}，"
            f"偏离幅度：{abs(deviation_percent)}%，阈值：{threshold}%\n"
            f"数据日期：{health_data.data_date}\n"
            f"数据来源：{health_data.data_source}"
        )

        personal_advice = self._generate_personal_advice(
            metric_name=metric_name,
            direction=direction,
            severity=severity,
            employee=employee
        )

        admin = self._assign_admin(severity=severity, metric_name=metric_name, db=db)

        ticket = AlertTicket(
            employee_id=employee_id,
            ticket_no=self.generate_ticket_no(),
            alert_type=alert_type,
            severity=severity,
            metric_name=metric_name,
            current_value=current_value,
            baseline_value=baseline_value,
            deviation_percent=deviation_percent,
            threshold=threshold,
            title=title,
            description=description,
            personal_advice=personal_advice,
            assigned_admin_id=admin.id if admin else None,
            status=TicketStatus.ASSIGNED if admin else TicketStatus.PENDING,
            health_data_id=health_data.id
        )

        db.add(ticket)
        db.flush()

        log_alert(
            alert_id=ticket.id,
            employee_id=employee_id,
            severity=severity,
            message=f"创建工单: {title}"
        )

        return ticket

    def _generate_personal_advice(
        self,
        metric_name: str,
        direction: str,
        severity: str,
        employee: Employee
    ) -> str:
        key = (metric_name, direction, severity)
        templates = PERSONAL_ADVICE_TEMPLATES.get(key)

        if not templates:
            for s in reversed(SEVERITY_ORDER[:SEVERITY_ORDER.index(severity) + 1]):
                alt_key = (metric_name, direction, s)
                if alt_key in PERSONAL_ADVICE_TEMPLATES:
                    templates = PERSONAL_ADVICE_TEMPLATES[alt_key]
                    break

        if not templates:
            templates = ["建议关注健康状况，必要时就医检查。"]

        base_advice = templates[hash(str(employee.id)) % len(templates)]

        extra_advice = ""
        with get_db_context() as db:
            profile = db.query(HealthProfile).filter(
                HealthProfile.employee_id == employee.id
            ).first()

            if profile:
                if profile.chronic_diseases:
                    extra_advice += f"\n\n注意：您有{profile.chronic_diseases}，请特别关注。"
                if profile.allergies:
                    extra_advice += f"\n过敏史：{profile.allergies}"
                if profile.emergency_contact:
                    extra_advice += f"\n紧急联系人：{profile.emergency_contact}，电话：{profile.emergency_phone}"

        return base_advice + extra_advice

    def _assign_admin(
        self,
        severity: str,
        metric_name: str,
        db: Session
    ) -> Optional[HealthAdmin]:
        severity_level = SEVERITY_ORDER.index(severity) + 1

        admins = db.query(HealthAdmin).filter(
            HealthAdmin.is_active == True
        ).order_by(HealthAdmin.severity_level.desc()).all()

        if not admins:
            return None

        suitable_admins = [a for a in admins if a.severity_level >= severity_level]

        if not suitable_admins:
            suitable_admins = admins

        admin_load = {}
        for admin in suitable_admins:
            pending_count = db.query(AlertTicket).filter(
                AlertTicket.assigned_admin_id == admin.id,
                AlertTicket.status.in_([
                    TicketStatus.PENDING,
                    TicketStatus.ASSIGNED,
                    TicketStatus.IN_PROGRESS
                ])
            ).count()
            admin_load[admin.id] = pending_count

        min_load_admin = min(suitable_admins, key=lambda a: admin_load.get(a.id, 0))

        return min_load_admin

    def reassign_ticket(
        self,
        ticket_id: int,
        admin_id: int,
        operator: str
    ) -> Optional[AlertTicket]:
        with get_db_context() as db:
            ticket = db.query(AlertTicket).filter(AlertTicket.id == ticket_id).first()
            admin = db.query(HealthAdmin).filter(HealthAdmin.id == admin_id).first()

            if not ticket or not admin:
                return None

            old_admin_id = ticket.assigned_admin_id
            ticket.assigned_admin_id = admin_id
            ticket.status = TicketStatus.ASSIGNED

            db.commit()
            db.refresh(ticket)

            log_audit(
                user=operator,
                action="reassign_ticket",
                detail=f"工单{ticket.ticket_no}从管理员{old_admin_id}转派给{admin_id}"
            )

            return ticket

    def update_ticket_status(
        self,
        ticket_id: int,
        status: str,
        operator: str
    ) -> Optional[AlertTicket]:
        with get_db_context() as db:
            ticket = db.query(AlertTicket).filter(AlertTicket.id == ticket_id).first()

            if not ticket:
                return None

            old_status = ticket.status
            ticket.status = status

            db.commit()
            db.refresh(ticket)

            log_audit(
                user=operator,
                action="update_ticket_status",
                detail=f"工单{ticket.ticket_no}状态从{old_status}变更为{status}"
            )

            return ticket

    def get_ticket_list(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        department_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[AlertTicket], int]:
        with get_db_context() as db:
            query = db.query(AlertTicket).join(Employee).join(Department, Employee.department_id == Department.id, isouter=True)

            if status:
                query = query.filter(AlertTicket.status == status)
            if severity:
                query = query.filter(AlertTicket.severity == severity)
            if department_id:
                query = query.filter(Employee.department_id == department_id)
            if start_date:
                query = query.filter(AlertTicket.created_at >= start_date)
            if end_date:
                query = query.filter(AlertTicket.created_at <= end_date)

            total = query.count()
            tickets = query.order_by(AlertTicket.created_at.desc())\
                .offset((page - 1) * page_size)\
                .limit(page_size)\
                .all()

            return tickets, total

    def get_employee_ticket_stats(self, employee_id: int) -> Dict:
        with get_db_context() as db:
            tickets = db.query(AlertTicket).filter(
                AlertTicket.employee_id == employee_id
            ).all()

            stats = defaultdict(int)
            severity_stats = defaultdict(int)

            for ticket in tickets:
                stats[ticket.status] += 1
                severity_stats[ticket.severity] += 1

            return {
                "total": len(tickets),
                "by_status": dict(stats),
                "by_severity": dict(severity_stats),
                "pending": stats.get(TicketStatus.PENDING, 0) + stats.get(TicketStatus.ASSIGNED, 0),
                "resolved": stats.get(TicketStatus.RESOLVED, 0)
            }


class FollowUpManager:
    def create_follow_up_record(
        self,
        ticket_id: int,
        follow_up_by: str,
        contact_method: str,
        employee_response: str,
        admin_assessment: str,
        action_taken: str,
        is_resolved: bool = False,
        next_follow_up: Optional[datetime] = None
    ) -> Optional[FollowUpRecord]:
        with get_db_context() as db:
            ticket = db.query(AlertTicket).filter(AlertTicket.id == ticket_id).first()

            if not ticket:
                return None

            record = FollowUpRecord(
                alert_ticket_id=ticket_id,
                follow_up_by=follow_up_by,
                contact_method=contact_method,
                employee_response=employee_response,
                admin_assessment=admin_assessment,
                action_taken=action_taken,
                is_resolved=is_resolved,
                next_follow_up=next_follow_up
            )

            db.add(record)

            ticket.follow_up_result = admin_assessment
            ticket.follow_up_time = datetime.now()
            ticket.follow_up_by = follow_up_by

            if is_resolved:
                ticket.status = TicketStatus.RESOLVED

            db.commit()
            db.refresh(record)

            self._update_health_profile(ticket.employee_id, admin_assessment, is_resolved)

            log_audit(
                user=follow_up_by,
                action="create_follow_up",
                detail=f"工单{ticket.ticket_no}回访记录已创建"
            )

            return record

    def _update_health_profile(
        self,
        employee_id: int,
        assessment: str,
        is_resolved: bool
    ):
        with get_db_context() as db:
            profile = db.query(HealthProfile).filter(
                HealthProfile.employee_id == employee_id
            ).first()

            if not profile:
                profile = HealthProfile(employee_id=employee_id)
                db.add(profile)

            tickets = db.query(AlertTicket).filter(
                AlertTicket.employee_id == employee_id,
                AlertTicket.severity.in_([AlertSeverity.HIGH, AlertSeverity.CRITICAL]),
                AlertTicket.status == TicketStatus.RESOLVED
            ).count()

            high_risk_tickets = db.query(AlertTicket).filter(
                AlertTicket.employee_id == employee_id,
                AlertTicket.severity.in_([AlertSeverity.HIGH, AlertSeverity.CRITICAL]),
                AlertTicket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED])
            ).count()

            if high_risk_tickets > 0:
                profile.risk_level = "high"
            elif tickets > 5:
                profile.risk_level = "medium"
            else:
                profile.risk_level = "normal"

            all_tickets = db.query(AlertTicket).filter(
                AlertTicket.employee_id == employee_id
            ).count()

            if all_tickets > 0:
                resolved_tickets = db.query(AlertTicket).filter(
                    AlertTicket.employee_id == employee_id,
                    AlertTicket.status.in_([TicketStatus.RESOLVED, TicketStatus.CLOSED])
                ).count()
                profile.health_score = max(0, min(100, int(100 - (all_tickets - resolved_tickets) * 10)))

            db.commit()

    def get_follow_up_history(self, ticket_id: int) -> List[FollowUpRecord]:
        with get_db_context() as db:
            return db.query(FollowUpRecord).filter(
                FollowUpRecord.alert_ticket_id == ticket_id
            ).order_by(FollowUpRecord.follow_up_time.desc()).all()


def get_alert_ticket_manager() -> AlertTicketManager:
    return AlertTicketManager()


def get_follow_up_manager() -> FollowUpManager:
    return FollowUpManager()
