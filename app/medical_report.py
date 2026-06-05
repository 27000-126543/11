import os
import re
import json
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
import pandas as pd
import numpy as np

try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from .database import get_db_context
from .models import Employee, MedicalReport, MedicalIndicator, HealthProfile
from .logging_config import get_logger, log_audit
from .config import get_settings

settings = get_settings()
logger = get_logger(__name__)

os.makedirs("uploads/reports", exist_ok=True)
os.makedirs("data/charts", exist_ok=True)


COMMON_INDICATORS = {
    "白细胞计数": {"code": "WBC", "unit": "×10^9/L", "range": "4.0-10.0"},
    "红细胞计数": {"code": "RBC", "unit": "×10^12/L", "range": "4.0-5.5"},
    "血红蛋白": {"code": "HGB", "unit": "g/L", "range": "120-160"},
    "血小板计数": {"code": "PLT", "unit": "×10^9/L", "range": "100-300"},
    "谷丙转氨酶": {"code": "ALT", "unit": "U/L", "range": "0-40"},
    "谷草转氨酶": {"code": "AST", "unit": "U/L", "range": "0-40"},
    "总胆固醇": {"code": "TC", "unit": "mmol/L", "range": "<5.2"},
    "甘油三酯": {"code": "TG", "unit": "mmol/L", "range": "<1.7"},
    "高密度脂蛋白": {"code": "HDL-C", "unit": "mmol/L", "range": ">1.0"},
    "低密度脂蛋白": {"code": "LDL-C", "unit": "mmol/L", "range": "<3.4"},
    "空腹血糖": {"code": "GLU", "unit": "mmol/L", "range": "3.9-6.1"},
    "尿酸": {"code": "UA", "unit": "μmol/L", "range": "150-420"},
    "肌酐": {"code": "CRE", "unit": "μmol/L", "range": "44-133"},
    "尿素氮": {"code": "BUN", "unit": "mmol/L", "range": "2.9-8.2"},
    "收缩压": {"code": "SBP", "unit": "mmHg", "range": "90-140"},
    "舒张压": {"code": "DBP", "unit": "mmHg", "range": "60-90"},
    "身高": {"code": "HEIGHT", "unit": "cm", "range": ""},
    "体重": {"code": "WEIGHT", "unit": "kg", "range": ""},
    "BMI": {"code": "BMI", "unit": "", "range": "18.5-24"},
    "心率": {"code": "HR", "unit": "次/分", "range": "60-100"},
}


class OCRProcessor:
    def __init__(self):
        self.tesseract_cmd = None

    def extract_text_from_image(self, image_path: str) -> str:
        if not OCR_AVAILABLE:
            logger.warning("OCR不可用，返回空文本")
            return ""

        try:
            if self.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            logger.info(f"OCR提取完成: {image_path}")
            return text
        except Exception as e:
            logger.error(f"OCR提取失败: {str(e)}")
            return ""

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(pdf_path)
            all_text = ""
            for img in images:
                text = pytesseract.image_to_string(img, lang="chi_sim+eng")
                all_text += text + "\n"
            return all_text
        except Exception as e:
            logger.error(f"PDF OCR提取失败: {str(e)}")
            return ""


class IndicatorExtractor:
    def __init__(self):
        self.patterns = [
            r'([\u4e00-\u9fa5]+)\s*[:：]\s*([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)',
            r'([\u4e00-\u9fa5]+)\s+([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)\s+([\d.]+-[\d.]+)',
        ]

    def extract_indicators(self, text: str) -> List[Dict]:
        indicators = []

        for indicator_name, meta in COMMON_INDICATORS.items():
            pattern = rf'{indicator_name}\s*[:：]?\s*([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)\s*(?:参考范围[:：]?\s*([\d.<>-]+))?'
            match = re.search(pattern, text)

            if match:
                try:
                    value = float(match.group(1))
                    unit = match.group(2) or meta.get("unit", "")
                    reference = match.group(3) or meta.get("range", "")

                    is_abnormal = self._check_abnormal(value, reference)

                    indicators.append({
                        "indicator_name": indicator_name,
                        "indicator_code": meta.get("code", ""),
                        "value": value,
                        "unit": unit,
                        "reference_range": reference,
                        "status": "异常" if is_abnormal else "正常",
                        "is_abnormal": is_abnormal
                    })
                except (ValueError, TypeError):
                    continue

        for pattern in self.patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1)
                try:
                    value = float(match.group(2))
                    unit = match.group(3) if len(match.groups()) > 2 else ""

                    if name in [i["indicator_name"] for i in indicators]:
                        continue

                    is_abnormal = False
                    if len(match.groups()) > 3:
                        reference = match.group(4)
                        is_abnormal = self._check_abnormal(value, reference)
                    else:
                        reference = COMMON_INDICATORS.get(name, {}).get("range", "")
                        if reference:
                            is_abnormal = self._check_abnormal(value, reference)

                    indicators.append({
                        "indicator_name": name,
                        "indicator_code": COMMON_INDICATORS.get(name, {}).get("code", ""),
                        "value": value,
                        "unit": unit,
                        "reference_range": reference,
                        "status": "异常" if is_abnormal else "正常",
                        "is_abnormal": is_abnormal
                    })
                except (ValueError, TypeError):
                    continue

        return indicators

    def _check_abnormal(self, value: float, reference: str) -> bool:
        if not reference:
            return False

        try:
            if "<" in reference:
                threshold = float(re.search(r'[\d.]+', reference).group())
                return value >= threshold
            elif ">" in reference:
                threshold = float(re.search(r'[\d.]+', reference).group())
                return value <= threshold
            elif "-" in reference:
                parts = reference.split("-")
                if len(parts) == 2:
                    low = float(parts[0])
                    high = float(parts[1])
                    return value < low or value > high
        except Exception:
            pass

        return False


class MedicalReportManager:
    def __init__(self):
        self.ocr_processor = OCRProcessor()
        self.indicator_extractor = IndicatorExtractor()

    def upload_report(
        self,
        employee_id: int,
        file_path: str,
        report_date: date,
        report_type: str = "年度体检",
        hospital: str = ""
    ) -> Optional[MedicalReport]:
        with get_db_context() as db:
            employee = db.query(Employee).filter(Employee.id == employee_id).first()
            if not employee:
                return None

            report = MedicalReport(
                employee_id=employee_id,
                report_date=report_date,
                report_type=report_type,
                hospital=hospital,
                file_path=file_path
            )

            db.add(report)
            db.commit()
            db.refresh(report)

            log_audit(
                user=f"employee_{employee_id}",
                action="upload_medical_report",
                detail=f"上传体检报告: {report.id}, 日期: {report_date}"
            )

            return report

    def process_report_ocr(self, report_id: int) -> Optional[MedicalReport]:
        with get_db_context() as db:
            report = db.query(MedicalReport).filter(MedicalReport.id == report_id).first()
            if not report:
                return None

            if report.ocr_processed:
                return report

            ocr_text = ""
            if report.file_path:
                if report.file_path.lower().endswith((".png", ".jpg", ".jpeg")):
                    ocr_text = self.ocr_processor.extract_text_from_image(report.file_path)
                elif report.file_path.lower().endswith(".pdf"):
                    ocr_text = self.ocr_processor.extract_text_from_pdf(report.file_path)

            report.ocr_text = ocr_text
            report.ocr_processed = True

            if ocr_text:
                indicators = self.indicator_extractor.extract_indicators(ocr_text)
                self._save_indicators(report.id, indicators, db)

                self._calculate_changes(report, indicators, db)
                self._update_health_profile(report.employee_id, indicators, db)

                abnormal_count = sum(1 for i in indicators if i["is_abnormal"])
                report.overall_summary = self._generate_summary(indicators, abnormal_count)

            db.commit()
            db.refresh(report)

            log_audit(
                user="system",
                action="process_report_ocr",
                detail=f"处理体检报告OCR: {report_id}, 提取{len(report.indicators)}项指标"
            )

            return report

    def _save_indicators(self, report_id: int, indicators: List[Dict], db: Session):
        for ind in indicators:
            indicator = MedicalIndicator(
                medical_report_id=report_id,
                indicator_name=ind["indicator_name"],
                indicator_code=ind.get("indicator_code", ""),
                value=ind["value"],
                unit=ind.get("unit", ""),
                reference_range=ind.get("reference_range", ""),
                status=ind.get("status", ""),
                is_abnormal=ind.get("is_abnormal", False)
            )
            db.add(indicator)

    def _calculate_changes(self, report: MedicalReport, current_indicators: List[Dict], db: Session):
        last_report = db.query(MedicalReport).filter(
            MedicalReport.employee_id == report.employee_id,
            MedicalReport.id < report.id,
            MedicalReport.ocr_processed == True
        ).order_by(MedicalReport.report_date.desc()).first()

        if not last_report:
            return

        last_indicators = {i.indicator_name: i for i in last_report.indicators}

        for ind_data in current_indicators:
            name = ind_data["indicator_name"]
            if name in last_indicators:
                last_value = last_indicators[name].value
                current_value = ind_data["value"]

                if last_value and last_value != 0:
                    change = current_value - last_value
                    change_percent = (change / last_value) * 100

                    indicator = db.query(MedicalIndicator).filter(
                        MedicalIndicator.medical_report_id == report.id,
                        MedicalIndicator.indicator_name == name
                    ).first()

                    if indicator:
                        indicator.change_from_last = change
                        indicator.change_percent = round(change_percent, 2)

    def _update_health_profile(self, employee_id: int, indicators: List[Dict], db: Session):
        profile = db.query(HealthProfile).filter(
            HealthProfile.employee_id == employee_id
        ).first()

        if not profile:
            profile = HealthProfile(employee_id=employee_id)
            db.add(profile)

        ind_map = {i["indicator_name"]: i for i in indicators}

        if "身高" in ind_map:
            profile.height = ind_map["身高"]["value"]
        if "体重" in ind_map:
            profile.weight = ind_map["体重"]["value"]
        if "BMI" in ind_map:
            profile.bmi = ind_map["BMI"]["value"]
        elif profile.height and profile.weight:
            profile.bmi = round(profile.weight / ((profile.height / 100) ** 2), 1)

        profile.last_checkup_date = date.today()

        abnormal_count = sum(1 for i in indicators if i["is_abnormal"])
        if abnormal_count > 5:
            profile.risk_level = "high"
        elif abnormal_count > 2:
            profile.risk_level = "medium"
        else:
            profile.risk_level = "normal"

        profile.health_score = max(0, min(100, 100 - abnormal_count * 5))

    def _generate_summary(self, indicators: List[Dict], abnormal_count: int) -> str:
        total = len(indicators)
        abnormal_items = [i for i in indicators if i["is_abnormal"]]

        summary = f"本次体检共{total}项指标，其中{abnormal_count}项异常。\n\n"

        if abnormal_items:
            summary += "异常指标：\n"
            for item in abnormal_items[:10]:
                change_info = ""
                if item.get("change_percent"):
                    change = item["change_percent"]
                    direction = "上升" if change > 0 else "下降"
                    change_info = f"（较上次{direction}{abs(change)}%）"
                summary += f"- {item['indicator_name']}: {item['value']}{item.get('unit','')} " \
                           f"(参考: {item.get('reference_range','')}){change_info}\n"

            if len(abnormal_items) > 10:
                summary += f"... 另有{len(abnormal_items) - 10}项异常\n"

            summary += "\n建议：请关注异常指标，必要时就医复查。"
        else:
            summary += "所有指标正常，请继续保持健康的生活方式！"

        return summary

    def get_employee_medical_history(
        self,
        employee_id: int,
        indicator_name: Optional[str] = None
    ) -> Dict:
        with get_db_context() as db:
            reports = db.query(MedicalReport).filter(
                MedicalReport.employee_id == employee_id,
                MedicalReport.ocr_processed == True
            ).order_by(MedicalReport.report_date).all()

            history = {
                "reports": [],
                "indicator_trends": {}
            }

            indicator_names = set()
            for report in reports:
                report_data = {
                    "id": report.id,
                    "report_date": report.report_date.isoformat(),
                    "report_type": report.report_type,
                    "hospital": report.hospital,
                    "summary": report.overall_summary,
                    "indicators": []
                }

                for ind in report.indicators:
                    if indicator_name and ind.indicator_name != indicator_name:
                        continue

                    indicator_names.add(ind.indicator_name)
                    report_data["indicators"].append({
                        "name": ind.indicator_name,
                        "code": ind.indicator_code,
                        "value": ind.value,
                        "unit": ind.unit,
                        "reference_range": ind.reference_range,
                        "is_abnormal": ind.is_abnormal,
                        "change_from_last": ind.change_from_last,
                        "change_percent": ind.change_percent
                    })

                if not indicator_name or report_data["indicators"]:
                    history["reports"].append(report_data)

            for name in indicator_names:
                trend_data = []
                for report in reports:
                    ind = next((i for i in report.indicators if i.indicator_name == name), None)
                    if ind:
                        trend_data.append({
                            "date": report.report_date.isoformat(),
                            "value": ind.value,
                            "is_abnormal": ind.is_abnormal
                        })

                if trend_data:
                    history["indicator_trends"][name] = trend_data

            return history

    def generate_indicator_chart(
        self,
        employee_id: int,
        indicator_name: str,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')

        history = self.get_employee_medical_history(employee_id, indicator_name)
        trends = history.get("indicator_trends", {}).get(indicator_name, [])

        if not trends or len(trends) < 2:
            return None

        dates = [t["date"] for t in trends]
        values = [t["value"] for t in trends]
        colors = ["red" if t["is_abnormal"] else "blue" for t in trends]

        plt.figure(figsize=(12, 6))
        plt.plot(dates, values, marker='o', linestyle='-', color='gray', alpha=0.5)
        plt.scatter(dates, values, c=colors, s=100, zorder=5)

        for i, (date, value) in enumerate(zip(dates, values)):
            plt.annotate(str(value), (date, value), textcoords="offset points",
                        xytext=(0, 10), ha='center')

        ref_info = COMMON_INDICATORS.get(indicator_name, {})
        if ref_info.get("range") and "-" in ref_info["range"]:
            parts = ref_info["range"].split("-")
            try:
                low = float(parts[0])
                high = float(parts[1])
                plt.axhline(y=low, color='green', linestyle='--', alpha=0.5, label='参考下限')
                plt.axhline(y=high, color='green', linestyle='--', alpha=0.5, label='参考上限')
                plt.fill_between(dates, low, high, alpha=0.1, color='green', label='正常范围')
            except ValueError:
                pass

        plt.title(f'{indicator_name} 变化趋势图', fontsize=14, fontweight='bold')
        plt.xlabel('体检日期')
        plt.ylabel(f'{indicator_name} ({ref_info.get("unit", "")})')
        plt.xticks(rotation=45)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        if not output_path:
            output_path = f"data/charts/employee_{employee_id}_{indicator_name}_trend.png"

        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"生成指标趋势图: {output_path}")
        return output_path

    def get_report_statistics(self, department_id: Optional[int] = None,
                            start_date: Optional[date] = None,
                            end_date: Optional[date] = None) -> Dict:
        with get_db_context() as db:
            query = db.query(MedicalReport).join(Employee)

            if department_id:
                query = query.filter(Employee.department_id == department_id)
            if start_date:
                query = query.filter(MedicalReport.report_date >= start_date)
            if end_date:
                query = query.filter(MedicalReport.report_date <= end_date)

            reports = query.all()
            total_employees = db.query(Employee).filter(
                Employee.is_active == True,
                (Employee.department_id == department_id) if department_id else True
            ).count()

            participated_employees = set(r.employee_id for r in reports)

            stats = {
                "total_reports": len(reports),
                "participated_employees": len(participated_employees),
                "total_employees": total_employees,
                "participation_rate": round(len(participated_employees) / total_employees * 100, 2) if total_employees > 0 else 0,
                "processed_reports": sum(1 for r in reports if r.ocr_processed),
                "avg_abnormal_indicators": 0
            }

            processed = [r for r in reports if r.ocr_processed]
            if processed:
                total_abnormal = sum(
                    sum(1 for i in r.indicators if i.is_abnormal)
                    for r in processed
                )
                stats["avg_abnormal_indicators"] = round(total_abnormal / len(processed), 2)

            return stats


def get_medical_report_manager() -> MedicalReportManager:
    return MedicalReportManager()
