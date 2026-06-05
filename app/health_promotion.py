import uuid
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from collections import defaultdict
import numpy as np

from .database import get_db_context
from .models import (
    Department, Employee, HealthData, AlertTicket, DepartmentHealthMonitor,
    HealthPromotionActivity, ActivityParticipant
)
from .logging_config import get_logger, log_audit
from .config import get_settings
from .anomaly_detection import MetricType

settings = get_settings()
logger = get_logger(__name__)


ACTIVITY_TEMPLATES = {
    "sleep_improvement": {
        "title": "睡眠质量提升计划",
        "description": "针对部门睡眠问题，开展为期2周的睡眠改善活动",
        "target_metric": MetricType.SLEEP_DURATION,
        "duration_days": 14,
        "plan": {
            "activities": [
                {
                    "day": 1,
                    "type": "lecture",
                    "title": "健康睡眠知识讲座",
                    "content": "邀请睡眠专家讲解睡眠生理机制、睡眠对健康的影响、改善睡眠的方法"
                },
                {
                    "day": 3,
                    "type": "challenge",
                    "title": "早睡挑战",
                    "content": "连续7天晚上11点前入睡打卡，成功者获得健康积分"
                },
                {
                    "day": 7,
                    "type": "workshop",
                    "title": "睡前放松训练工作坊",
                    "content": "学习冥想、呼吸调节、渐进性肌肉放松等放松技巧"
                },
                {
                    "day": 10,
                    "type": "consultation",
                    "title": "一对一睡眠咨询",
                    "content": "健康管理员为员工提供个性化睡眠改善建议"
                },
                {
                    "day": 14,
                    "type": "review",
                    "title": "活动总结与效果评估",
                    "content": "对比活动前后睡眠数据，表彰进步显著的员工"
                }
            ],
            "goals": [
                "部门平均睡眠时长提升0.5小时以上",
                "深睡比例提升5%",
                "员工睡眠满意度达到80%"
            ],
            "resources": [
                "睡眠专家1名",
                "健康管理员2名",
                "睡眠监测设备",
                "健康积分奖励"
            ]
        }
    },
    "exercise_promotion": {
        "title": "活力提升运动计划",
        "description": "针对部门运动量不足问题，开展为期4周的运动促进活动",
        "target_metric": MetricType.STEPS,
        "duration_days": 28,
        "plan": {
            "activities": [
                {
                    "day": 1,
                    "type": "launch",
                    "title": "活动启动仪式",
                    "content": "介绍活动目标、规则、奖励机制，组建运动小组"
                },
                {
                    "day": 3,
                    "type": "challenge",
                    "title": "每日万步挑战",
                    "content": "每日步数达标者累计积分，每周评选步数达人"
                },
                {
                    "day": 7,
                    "type": "group_activity",
                    "title": "周末徒步活动",
                    "content": "组织部门员工进行户外徒步，增强团队凝聚力"
                },
                {
                    "day": 10,
                    "type": "lecture",
                    "title": "科学运动知识讲座",
                    "content": "讲解运动损伤预防、运动营养、运动计划制定"
                },
                {
                    "day": 14,
                    "type": "competition",
                    "title": "办公室运动比赛",
                    "content": "开展跳绳、平板支撑等适合办公室的运动比赛"
                },
                {
                    "day": 21,
                    "type": "workshop",
                    "title": "办公室微运动教学",
                    "content": "教授工间操、拉伸运动等可在办公室进行的运动"
                },
                {
                    "day": 28,
                    "type": "review",
                    "title": "活动总结表彰大会",
                    "content": "公布活动成果，颁发运动达人、进步之星等奖项"
                }
            ],
            "goals": [
                "部门平均每日步数提升至8000步以上",
                "步数达标率提升至70%以上",
                "员工运动习惯养成率达到60%"
            ],
            "resources": [
                "运动教练1名",
                "健康管理员2名",
                "运动设备（跳绳、瑜伽垫等）",
                "运动服装、奖品"
            ]
        }
    },
    "stress_management": {
        "title": "压力管理与心理健康促进计划",
        "description": "针对部门压力偏高问题，开展为期3周的心理健康促进活动",
        "target_metric": MetricType.STRESS_LEVEL,
        "duration_days": 21,
        "plan": {
            "activities": [
                {
                    "day": 1,
                    "type": "assessment",
                    "title": "心理健康评估",
                    "content": "采用专业量表评估员工压力水平和心理健康状况"
                },
                {
                    "day": 3,
                    "type": "lecture",
                    "title": "压力管理与心理健康讲座",
                    "content": "讲解压力的生理机制、压力对健康的影响、压力应对策略"
                },
                {
                    "day": 7,
                    "type": "workshop",
                    "title": "正念冥想训练",
                    "content": "学习正念冥想技巧，每日练习10-15分钟"
                },
                {
                    "day": 10,
                    "type": "group_activity",
                    "title": "团队建设活动",
                    "content": "组织轻松的团队活动，增进同事间交流与支持"
                },
                {
                    "day": 14,
                    "type": "consultation",
                    "title": "心理咨询服务",
                    "content": "专业心理咨询师为有需要的员工提供一对一咨询"
                },
                {
                    "day": 18,
                    "type": "workshop",
                    "title": "工作生活平衡技巧",
                    "content": "学习时间管理、边界设定、休闲规划等技巧"
                },
                {
                    "day": 21,
                    "type": "review",
                    "title": "活动总结与反馈",
                    "content": "评估活动效果，收集员工反馈，建立长期支持机制"
                }
            ],
            "goals": [
                "部门平均压力水平下降20%",
                "员工心理健康意识显著提升",
                "建立长期心理健康支持机制"
            ],
            "resources": [
                "心理咨询师1名",
                "健康管理员2名",
                "心理健康评估量表",
                "冥想APP会员"
            ]
        }
    },
    "heart_health": {
        "title": "心血管健康保护计划",
        "description": "针对部门心率异常偏高问题，开展为期2周的心血管健康促进活动",
        "target_metric": MetricType.HEART_RATE,
        "duration_days": 14,
        "plan": {
            "activities": [
                {
                    "day": 1,
                    "type": "checkup",
                    "title": "心血管健康筛查",
                    "content": "为员工进行心率、血压、血脂等心血管指标检测"
                },
                {
                    "day": 3,
                    "type": "lecture",
                    "title": "心血管健康知识讲座",
                    "content": "讲解心血管疾病预防、心率监测、紧急情况处理"
                },
                {
                    "day": 6,
                    "type": "workshop",
                    "title": "有氧运动指导",
                    "content": "学习适合的有氧运动方式，如快走、慢跑、游泳等"
                },
                {
                    "day": 10,
                    "type": "consultation",
                    "title": "一对一健康咨询",
                    "content": "根据个人体检结果提供个性化健康建议"
                },
                {
                    "day": 14,
                    "type": "review",
                    "title": "健康成果分享会",
                    "content": "分享健康改善成果，表彰积极参与者"
                }
            ],
            "goals": [
                "部门平均静息心率下降5-10次/分钟",
                "员工心血管健康知识知晓率达到90%",
                "养成定期监测心率的习惯"
            ],
            "resources": [
                "心血管专科医生1名",
                "健康管理员2名",
                "心率监测设备",
                "健康手册"
            ]
        }
    },
    "comprehensive_health": {
        "title": "综合健康提升计划",
        "description": "针对部门整体健康状况不佳问题，开展为期4周的综合健康促进活动",
        "target_metric": "comprehensive",
        "duration_days": 28,
        "plan": {
            "activities": [
                {
                    "day": 1,
                    "type": "assessment",
                    "title": "全面健康评估",
                    "content": "进行全面的健康检查和生活方式评估"
                },
                {
                    "day": 4,
                    "type": "lecture",
                    "title": "健康生活方式讲座",
                    "content": "讲解合理膳食、适量运动、戒烟限酒、心理平衡"
                },
                {
                    "day": 7,
                    "type": "challenge",
                    "title": "健康习惯养成挑战",
                    "content": "21天健康习惯打卡，包括早睡、运动、健康饮食"
                },
                {
                    "day": 11,
                    "type": "workshop",
                    "title": "营养搭配工作坊",
                    "content": "学习如何搭配营养均衡的一日三餐"
                },
                {
                    "day": 14,
                    "type": "group_activity",
                    "title": "运动嘉年华",
                    "content": "组织趣味运动会，让员工在玩乐中运动"
                },
                {
                    "day": 18,
                    "type": "consultation",
                    "title": "健康咨询日",
                    "content": "多学科专家提供一站式健康咨询服务"
                },
                {
                    "day": 21,
                    "type": "workshop",
                    "title": "压力管理与放松训练",
                    "content": "学习多种压力管理和放松技巧"
                },
                {
                    "day": 28,
                    "type": "review",
                    "title": "健康蜕变成果展",
                    "content": "展示每位员工的健康改善成果，颁发健康达人奖"
                }
            ],
            "goals": [
                "各项健康指标均有改善",
                "员工健康素养显著提升",
                "形成健康生活方式的良好氛围"
            ],
            "resources": [
                "多学科医疗团队",
                "健康管理员3名",
                "各种健康检测设备",
                "丰富的奖品和激励"
            ]
        }
    }
}


class DepartmentMonitor:
    def __init__(self):
        self.alert_days = settings.CONSECUTIVE_DAYS_THRESHOLD
        self.alert_percent = int(settings.DEPARTMENT_ANOMALY_THRESHOLD * 100)

    def monitor_all_departments(self) -> List[Dict]:
        monitor_date = date.today()

        with get_db_context() as db:
            departments = db.query(Department).all()
            results = []

            company_anomalies = 0
            company_total = 0

            for dept in departments:
                dept_result = self._calculate_department_anomaly_rate(
                    department_id=dept.id,
                    monitor_date=monitor_date,
                    db=db
                )
                results.append(dept_result)
                company_anomalies += dept_result.get("anomaly_count", 0)
                company_total += dept_result.get("total_employees", 0)

            company_avg_rate = round(company_anomalies / max(company_total, 1) * 100, 2) if company_total > 0 else 0

            final_results = []
            for dept_result in results:
                dept_result["company_avg_anomaly_rate"] = company_avg_rate
                deviation = dept_result["anomaly_rate"] - company_avg_rate
                dept_result["deviation_from_avg"] = round(deviation, 2)
                dept_result["above_threshold"] = deviation > self.alert_percent

                monitor = self._save_monitor_record(dept_result, db)
                dept_result["monitor_id"] = monitor.id

                if dept_result["above_threshold"]:
                    consecutive = self._check_consecutive_days(
                        dept_result["department_id"],
                        self.alert_days,
                        db
                    )
                    dept_result["consecutive_days_above"] = consecutive

                    if consecutive >= self.alert_days:
                        dept_result["should_trigger_activity"] = True
                    else:
                        dept_result["should_trigger_activity"] = False
                else:
                    dept_result["consecutive_days_above"] = 0
                    dept_result["should_trigger_activity"] = False

                final_results.append(dept_result)

            db.commit()
            logger.info(f"部门健康监控完成: {len(departments)}个部门, 公司平均异常率{company_avg_rate}%")

            return final_results

    def _calculate_department_anomaly_rate(
        self,
        department_id: int,
        monitor_date: date,
        db: Session
    ) -> Dict:
        employees = db.query(Employee).filter(
            Employee.department_id == department_id,
            Employee.is_active == True
        ).all()

        employee_ids = [e.id for e in employees]
        total_employees = len(employees)

        health_data = db.query(Employee.id, HealthData.is_anomaly).join(
            HealthData, Employee.id == HealthData.employee_id
        ).filter(
            Employee.department_id == department_id,
            HealthData.data_date == monitor_date
        ).all()

        anomaly_count = sum(1 for _, is_anomaly in health_data if is_anomaly)
        anomaly_rate = round(anomaly_count / max(total_employees, 1) * 100, 2)

        return {
            "department_id": department_id,
            "department_name": employees[0].department.name if employees and employees[0].department else "",
            "monitor_date": monitor_date,
            "total_employees": total_employees,
            "anomaly_count": anomaly_count,
            "anomaly_rate": anomaly_rate
        }

    def _save_monitor_record(self, data: Dict, db: Session) -> DepartmentHealthMonitor:
        monitor = DepartmentHealthMonitor(
            department_id=data["department_id"],
            monitor_date=data["monitor_date"],
            total_employees=data["total_employees"],
            anomaly_count=data["anomaly_count"],
            anomaly_rate=data["anomaly_rate"],
            company_avg_anomaly_rate=data.get("company_avg_anomaly_rate", 0),
            deviation_from_avg=data.get("deviation_from_avg", 0),
            above_threshold=data.get("above_threshold", False),
            consecutive_days_above=data.get("consecutive_days_above", 0)
        )
        db.add(monitor)
        return monitor

    def _check_consecutive_days(self, department_id: int, days: int, db: Session) -> int:
        end_date = date.today()
        consecutive = 0

        for i in range(days):
            check_date = end_date - timedelta(days=i)
            monitor = db.query(DepartmentHealthMonitor).filter(
                DepartmentHealthMonitor.department_id == department_id,
                DepartmentHealthMonitor.monitor_date == check_date
            ).first()

            if monitor and monitor.above_threshold:
                consecutive += 1
            else:
                break

        return consecutive


class HealthPromotionManager:
    def __init__(self):
        self.monitor = DepartmentMonitor()

    def generate_activity_no(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d")
        uuid_part = str(uuid.uuid4().hex[:6]).upper()
        return f"ACT-{timestamp}-{uuid_part}"

    def detect_and_trigger_activities(self) -> List[HealthPromotionActivity]:
        monitor_results = self.monitor.monitor_all_departments()
        triggered_activities = []

        for result in monitor_results:
            if result.get("should_trigger_activity"):
                activity = self.create_activity_for_department(result)
                if activity:
                    triggered_activities.append(activity)

        logger.info(f"健康促进活动触发完成: 创建{len(triggered_activities)}个活动")
        return triggered_activities

    def create_activity_for_department(
        self,
        monitor_result: Dict
    ) -> Optional[HealthPromotionActivity]:
        department_id = monitor_result["department_id"]
        anomaly_rate = monitor_result["anomaly_rate"]
        company_avg = monitor_result["company_avg_anomaly_rate"]
        consecutive_days = monitor_result["consecutive_days_above"]

        with get_db_context() as db:
            existing = db.query(HealthPromotionActivity).filter(
                HealthPromotionActivity.department_id == department_id,
                HealthPromotionActivity.status.in_(["draft", "active"])
            ).first()

            if existing:
                logger.info(f"部门{department_id}已有进行中的活动，跳过创建")
                return None

            dominant_anomaly = self._identify_dominant_anomaly(department_id, db)
            template = self._select_activity_template(dominant_anomaly)

            start_date = date.today() + timedelta(days=3)
            end_date = start_date + timedelta(days=template["duration_days"])

            trigger_reason = (
                f"部门连续{consecutive_days}天异常率高于公司均值{self.monitor.alert_percent}%。"
                f"当前异常率: {anomaly_rate}%, 公司均值: {company_avg}%, "
                f"主要问题: {dominant_anomaly}"
            )

            activity = HealthPromotionActivity(
                department_id=department_id,
                activity_no=self.generate_activity_no(),
                activity_type=dominant_anomaly,
                title=template["title"],
                description=template["description"],
                activity_plan=template["plan"],
                target_metric=template["target_metric"],
                start_date=start_date,
                end_date=end_date,
                status="draft",
                auto_generated=True,
                trigger_reason=trigger_reason
            )

            db.add(activity)
            db.flush()

            self._invite_employees(activity.id, department_id, db)
            db.commit()
            db.refresh(activity)

            log_audit(
                user="system",
                action="create_health_activity",
                detail=f"自动创建健康促进活动: {activity.activity_no}, 部门: {department_id}"
            )

            logger.info(f"为部门{department_id}创建健康促进活动: {activity.activity_no}")
            return activity

    def _identify_dominant_anomaly(self, department_id: int, db: Session) -> str:
        from .models import AlertTicket
        from .alert_ticket import TicketStatus

        end_date = date.today()
        start_date = end_date - timedelta(days=7)

        employees = db.query(Employee.id).filter(
            Employee.department_id == department_id,
            Employee.is_active == True
        ).all()
        employee_ids = [e.id for e in employees]

        tickets = db.query(AlertTicket).filter(
            AlertTicket.employee_id.in_(employee_ids),
            AlertTicket.created_at >= start_date,
            AlertTicket.created_at <= end_date + timedelta(days=1)
        ).all()

        metric_counts = defaultdict(int)
        for ticket in tickets:
            metric_counts[ticket.metric_name] += 1

        if not metric_counts:
            return "comprehensive"

        top_metric = max(metric_counts.items(), key=lambda x: x[1])[0]

        if top_metric in [MetricType.SLEEP_DURATION, MetricType.DEEP_SLEEP, MetricType.SLEEP_SCORE]:
            return "sleep_improvement"
        elif top_metric == MetricType.STEPS:
            return "exercise_promotion"
        elif top_metric == MetricType.STRESS_LEVEL:
            return "stress_management"
        elif top_metric in [MetricType.HEART_RATE, MetricType.HEART_RATE_RESTING]:
            return "heart_health"
        else:
            return "comprehensive"

    def _select_activity_template(self, activity_type: str) -> Dict:
        return ACTIVITY_TEMPLATES.get(activity_type, ACTIVITY_TEMPLATES["comprehensive_health"])

    def _invite_employees(self, activity_id: int, department_id: int, db: Session):
        employees = db.query(Employee).filter(
            Employee.department_id == department_id,
            Employee.is_active == True
        ).all()

        invited_count = 0
        for emp in employees:
            participant = ActivityParticipant(
                activity_id=activity_id,
                employee_id=emp.id,
                status="invited"
            )
            db.add(participant)
            invited_count += 1

        activity = db.query(HealthPromotionActivity).filter(
            HealthPromotionActivity.id == activity_id
        ).first()

        if activity:
            activity.invited_count = invited_count

    def update_participant_status(
        self,
        activity_id: int,
        employee_id: int,
        status: str,
        participation_score: Optional[int] = None,
        feedback: Optional[str] = None
    ) -> Optional[ActivityParticipant]:
        with get_db_context() as db:
            participant = db.query(ActivityParticipant).filter(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.employee_id == employee_id
            ).first()

            if not participant:
                return None

            participant.status = status
            if status == "accepted":
                participant.accepted_at = datetime.now()
            if participation_score is not None:
                participant.participation_score = participation_score
            if feedback:
                participant.feedback = feedback

            if status == "completed":
                activity = db.query(HealthPromotionActivity).filter(
                    HealthPromotionActivity.id == activity_id
                ).first()
                if activity:
                    participated = db.query(ActivityParticipant).filter(
                        ActivityParticipant.activity_id == activity_id,
                        ActivityParticipant.status == "completed"
                    ).count()
                    activity.participated_count = participated

            db.commit()
            db.refresh(participant)

            return participant

    def get_activity_list(
        self,
        department_id: Optional[int] = None,
        status: Optional[str] = None,
        auto_generated: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[HealthPromotionActivity], int]:
        with get_db_context() as db:
            query = db.query(HealthPromotionActivity)

            if department_id:
                query = query.filter(HealthPromotionActivity.department_id == department_id)
            if status:
                query = query.filter(HealthPromotionActivity.status == status)
            if auto_generated is not None:
                query = query.filter(HealthPromotionActivity.auto_generated == auto_generated)

            total = query.count()
            activities = query.order_by(HealthPromotionActivity.created_at.desc())\
                .offset((page - 1) * page_size)\
                .limit(page_size)\
                .all()

            return activities, total


def get_department_monitor() -> DepartmentMonitor:
    return DepartmentMonitor()


def get_health_promotion_manager() -> HealthPromotionManager:
    return HealthPromotionManager()
