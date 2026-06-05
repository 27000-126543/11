import os
import re
import json
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
import pandas as pd
import numpy as np

try:
    from pdfminer.high_level import extract_text as pdf_extract_text
    PDF_EXTRACT_AVAILABLE = True
except ImportError:
    PDF_EXTRACT_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    PDF_GENERATE_AVAILABLE = True
except ImportError:
    PDF_GENERATE_AVAILABLE = False

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


class PDFTextExtractor:
    def __init__(self):
        pass

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        if not PDF_EXTRACT_AVAILABLE:
            logger.warning("PDF文本提取不可用，返回空文本")
            return ""

        try:
            text = pdf_extract_text(pdf_path)
            logger.info(f"PDF文本提取完成: {pdf_path}, 提取{len(text)}字符")
            return text
        except Exception as e:
            logger.error(f"PDF文本提取失败: {str(e)}")
            return ""

    def extract_text_from_image(self, image_path: str) -> str:
        logger.warning("图片OCR功能需要外部依赖，返回空文本")
        return ""


class IndicatorExtractor:
    def __init__(self):
        self.patterns = [
            r'([\u4e00-\u9fa5]+)\s*[:：]\s*([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)',
            r'([\u4e00-\u9fa5]+)\s+([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)\s+([\d.]+-[\d.]+)',
            r'\*\s*([\u4e00-\u9fa5]+)\s*[:：]\s*([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)\s*\(参考范围[:：]?\s*([\d.<>-]+)\)',
            r'\s*([\u4e00-\u9fa5]+)\s*[:：]\s*([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)\s*\(参考范围[:：]?\s*([\d.<>-]+)\)',
        ]

    def extract_indicators(self, text: str) -> List[Dict]:
        indicators = []

        for indicator_name, meta in COMMON_INDICATORS.items():
            patterns = [
                rf'\*\s*{indicator_name}\s*[:：]\s*([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)\s*\(参考范围[:：]?\s*([\d.<>-]+)\)',
                rf'\s*{indicator_name}\s*[:：]\s*([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)\s*\(参考范围[:：]?\s*([\d.<>-]+)\)',
                rf'{indicator_name}\s*[:：]?\s*([\d.]+)\s*([\u4e00-\u9fa5/^%×a-zA-Z0-9]*)\s*(?:参考范围[:：]?\s*([\d.<>-]+))?',
            ]

            match = None
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    break

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
                    reference = ""
                    if len(match.groups()) > 3 and match.group(4):
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


class SampleReportGenerator:
    def __init__(self):
        self._chinese_font_registered = False

    def _register_chinese_font(self):
        if self._chinese_font_registered:
            return

        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            font_paths = [
                '/System/Library/Fonts/STHeiti Medium.ttc',
                '/System/Library/Fonts/STHeiti Light.ttc',
                '/Library/Fonts/Arial Unicode.ttf',
            ]

            font_path = None
            for path in font_paths:
                if os.path.exists(path):
                    font_path = path
                    break

            if font_path:
                pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                self._chinese_font_name = 'ChineseFont'
                self._chinese_font_registered = True
                logger.info(f"中文字体注册成功: {font_path}")
        except Exception as e:
            logger.warning(f"中文字体注册失败: {str(e)}")
            self._chinese_font_name = 'Helvetica'

    def generate_sample_report(
        self,
        employee,
        report_date: date,
        output_path: str,
        include_abnormal: bool = True
    ) -> str:
        if not PDF_GENERATE_AVAILABLE:
            logger.error("PDF生成不可用")
            return ""

        self._register_chinese_font()

        doc = SimpleDocTemplate(output_path, pagesize=A4,
                               rightMargin=2*cm, leftMargin=2*cm,
                               topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        font_name = getattr(self, '_chinese_font_name', 'Helvetica')

        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                    alignment=TA_CENTER, fontSize=18, spaceAfter=20,
                                    fontName=font_name)
        normal_style = ParagraphStyle('NormalText', parent=styles['Normal'], fontName=font_name)
        header_style = ParagraphStyle('Header', parent=normal_style, fontSize=12, spaceAfter=10)
        section_style = ParagraphStyle('SectionTitle', parent=styles['Heading2'], spaceAfter=10, fontName=font_name)
        text_style = ParagraphStyle('TextSummary', parent=normal_style, fontSize=9, leading=14, fontName=font_name)

        story = []

        story.append(Paragraph("员工体检报告", title_style))
        story.append(Spacer(1, 0.5*cm))

        info_data = [
            ["姓名", employee.name, "员工编号", employee.employee_no],
            ["性别", employee.gender, "年龄", str(employee.age)],
            ["部门", employee.department.name if employee.department else "未分配",
             "体检日期", report_date.strftime("%Y-%m-%d")],
        ]
        info_table = Table(info_data, colWidths=[3*cm, 4*cm, 3*cm, 4*cm])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.8*cm))

        story.append(Paragraph("体检指标", section_style))
        story.append(Spacer(1, 0.3*cm))

        table_data = [["检查项目", "结果", "单位", "参考范围", "状态"]]

        height = round(random.uniform(155, 185), 1)
        weight = round(random.uniform(45, 90), 1)
        bmi = round(weight / ((height / 100) ** 2), 1)

        indicators_data = [
            ("身高", height, "cm", ""),
            ("体重", weight, "kg", ""),
            ("BMI", bmi, "", "18.5-24"),
            ("收缩压", random.randint(110, 150), "mmHg", "90-140"),
            ("舒张压", random.randint(70, 95), "mmHg", "60-90"),
            ("心率", random.randint(60, 100), "次/分", "60-100"),
            ("白细胞计数", round(random.uniform(4.0, 11.0), 2), "×10^9/L", "4.0-10.0"),
            ("红细胞计数", round(random.uniform(4.0, 5.8), 2), "×10^12/L", "4.0-5.5"),
            ("血红蛋白", random.randint(110, 170), "g/L", "120-160"),
            ("血小板计数", random.randint(90, 320), "×10^9/L", "100-300"),
            ("谷丙转氨酶", round(random.uniform(15, 60), 1), "U/L", "0-40"),
            ("谷草转氨酶", round(random.uniform(15, 55), 1), "U/L", "0-40"),
            ("总胆固醇", round(random.uniform(3.5, 6.0), 2), "mmol/L", "<5.2"),
            ("甘油三酯", round(random.uniform(0.8, 2.5), 2), "mmol/L", "<1.7"),
            ("高密度脂蛋白", round(random.uniform(0.8, 1.8), 2), "mmol/L", ">1.0"),
            ("低密度脂蛋白", round(random.uniform(2.0, 4.0), 2), "mmol/L", "<3.4"),
            ("空腹血糖", round(random.uniform(4.0, 7.0), 2), "mmol/L", "3.9-6.1"),
            ("尿酸", random.randint(120, 480), "μmol/L", "150-420"),
            ("肌酐", random.randint(50, 150), "μmol/L", "44-133"),
            ("尿素氮", round(random.uniform(2.5, 9.0), 2), "mmol/L", "2.9-8.2"),
        ]

        if not include_abnormal:
            indicators_data = self._normalize_to_normal(indicators_data)

        text_summary_lines = []
        text_summary_lines.append("【体检指标汇总】")

        for name, value, unit, ref_range in indicators_data:
            is_abn = self._is_value_abnormal(value, ref_range)
            status = "↑" if (is_abn and ref_range and "-" in ref_range and value > float(ref_range.split("-")[1])) else \
                     "↓" if (is_abn and ref_range and "-" in ref_range and value < float(ref_range.split("-")[0])) else \
                     "异常" if is_abn else "正常"

            table_data.append([name, str(value), unit, ref_range, status])

            status_text = "*" if is_abn else " "
            summary_line = f"{status_text}{name}: {value} {unit}"
            if ref_range:
                summary_line += f" (参考范围: {ref_range})"
            if is_abn:
                summary_line += " 【异常】"
            text_summary_lines.append(summary_line)

        indicator_table = Table(table_data, colWidths=[3.5*cm, 2.5*cm, 2.5*cm, 3*cm, 2*cm])
        indicator_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        story.append(indicator_table)
        story.append(Spacer(1, 1*cm))

        story.append(Paragraph("指标明细（文本版）", section_style))
        story.append(Spacer(1, 0.3*cm))

        for line in text_summary_lines:
            story.append(Paragraph(line, text_style))

        doc.build(story)
        logger.info(f"生成示例体检报告: {output_path}")
        return output_path

    def _is_value_abnormal(self, value: float, reference: str) -> bool:
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

    def _normalize_to_normal(self, indicators_data):
        normalized = []
        for name, value, unit, ref_range in indicators_data:
            if ref_range and "-" in ref_range:
                try:
                    parts = ref_range.split("-")
                    low = float(parts[0])
                    high = float(parts[1])
                    value = round(random.uniform(low + 0.1, high - 0.1), 2)
                except:
                    pass
            elif ref_range and "<" in ref_range:
                try:
                    threshold = float(re.search(r'[\d.]+', ref_range).group())
                    value = round(random.uniform(threshold * 0.5, threshold - 0.1), 2)
                except:
                    pass
            elif ref_range and ">" in ref_range:
                try:
                    threshold = float(re.search(r'[\d.]+', ref_range).group())
                    value = round(random.uniform(threshold + 0.1, threshold * 1.5), 2)
                except:
                    pass
            normalized.append((name, value, unit, ref_range))
        return normalized


class MedicalReportManager:
    def __init__(self):
        self.text_extractor = PDFTextExtractor()
        self.indicator_extractor = IndicatorExtractor()
        self.sample_generator = SampleReportGenerator()

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

    def generate_and_upload_sample_report(
        self,
        employee_id: int,
        report_date: Optional[date] = None,
        include_abnormal: bool = True
    ) -> Optional[MedicalReport]:
        report_date = report_date or date.today()

        with get_db_context() as db:
            employee = db.query(Employee).filter(Employee.id == employee_id).first()
            if not employee:
                return None

            filename = f"体检报告_{employee.employee_no}_{report_date.strftime('%Y%m%d')}.pdf"
            file_path = os.path.join("uploads/reports", filename)

            self.sample_generator.generate_sample_report(
                employee=employee,
                report_date=report_date,
                output_path=file_path,
                include_abnormal=include_abnormal
            )

            report = self.upload_report(
                employee_id=employee_id,
                file_path=file_path,
                report_date=report_date,
                report_type="年度体检",
                hospital="示例体检中心"
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
                    ocr_text = self.text_extractor.extract_text_from_image(report.file_path)
                elif report.file_path.lower().endswith(".pdf"):
                    ocr_text = self.text_extractor.extract_text_from_pdf(report.file_path)

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

        critical_indicators = ["空腹血糖", "总胆固醇", "甘油三酯", "收缩压", "舒张压", "尿酸"]
        critical_abnormal = sum(1 for i in indicators 
                               if i["indicator_name"] in critical_indicators and i["is_abnormal"])

        if critical_abnormal >= 3 or abnormal_count >= 7:
            profile.risk_level = "high"
        elif critical_abnormal >= 2 or abnormal_count >= 5:
            profile.risk_level = "medium"
        elif critical_abnormal >= 1 or abnormal_count >= 2:
            profile.risk_level = "low"
        else:
            profile.risk_level = "normal"

        profile.health_score = max(0, min(100, 100 - abnormal_count * 3 - critical_abnormal * 8))

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
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib import font_manager

            for font_path in [
                '/System/Library/Fonts/PingFang.ttc',
                '/System/Library/Fonts/STHeiti Medium.ttc',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            ]:
                if os.path.exists(font_path):
                    font_manager.fontManager.addfont(font_path)
                    plt.rcParams['font.sans-serif'] = [font_manager.FontProperties(fname=font_path).get_name()]
                    break

            plt.rcParams['axes.unicode_minus'] = False
        except Exception as e:
            logger.error(f"matplotlib初始化失败: {str(e)}")
            return None

        history = self.get_employee_medical_history(employee_id, indicator_name)
        trends = history.get("indicator_trends", {}).get(indicator_name, [])

        if not trends or len(trends) < 2:
            logger.warning(f"数据不足，无法生成趋势图: {indicator_name}, 数据点: {len(trends)}")
            return None

        try:
            dates = [datetime.strptime(t["date"], "%Y-%m-%d").date() for t in trends]
            values = [t["value"] for t in trends]
            colors = ["#ff6b6b" if t["is_abnormal"] else "#4ecdc4" for t in trends]

            fig, ax = plt.subplots(figsize=(12, 6))
            ax.plot(dates, values, marker='o', linestyle='-', color='#888888', 
                   alpha=0.5, linewidth=2, markersize=0, zorder=1)
            ax.scatter(dates, values, c=colors, s=120, zorder=5, edgecolors='white', linewidth=2)

            for i, (d, v) in enumerate(zip(dates, values)):
                ax.annotate(str(v), (d, v), textcoords="offset points",
                           xytext=(0, 12), ha='center', fontsize=10, fontweight='bold')

            ref_info = COMMON_INDICATORS.get(indicator_name, {})
            if ref_info.get("range"):
                ref_range = ref_info["range"]
                if "-" in ref_range:
                    try:
                        parts = ref_range.split("-")
                        low = float(parts[0])
                        high = float(parts[1])
                        ax.axhline(y=low, color='#95e1d3', linestyle='--', alpha=0.7, linewidth=1.5, label='参考下限')
                        ax.axhline(y=high, color='#95e1d3', linestyle='--', alpha=0.7, linewidth=1.5, label='参考上限')
                        ax.fill_between(dates, low, high, alpha=0.15, color='#95e1d3', label='正常范围')
                    except ValueError:
                        pass
                elif "<" in ref_range:
                    try:
                        threshold = float(re.search(r'[\d.]+', ref_range).group())
                        ax.axhline(y=threshold, color='#f38181', linestyle='--', alpha=0.7, linewidth=1.5, label='参考上限')
                    except:
                        pass
                elif ">" in ref_range:
                    try:
                        threshold = float(re.search(r'[\d.]+', ref_range).group())
                        ax.axhline(y=threshold, color='#f38181', linestyle='--', alpha=0.7, linewidth=1.5, label='参考下限')
                    except:
                        pass

            ax.set_title(f'{indicator_name} 变化趋势图', fontsize=16, fontweight='bold', pad=20)
            ax.set_xlabel('体检日期', fontsize=12)
            ax.set_ylabel(f'{indicator_name} ({ref_info.get("unit", "")})', fontsize=12)
            ax.tick_params(axis='x', rotation=45)
            ax.legend(loc='best', fontsize=10)
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

            plt.tight_layout()

            if not output_path:
                safe_indicator = re.sub(r'[^\w\u4e00-\u9fa5]', '_', indicator_name)
                output_path = f"data/charts/employee_{employee_id}_{safe_indicator}_trend.png"

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            logger.info(f"生成指标趋势图: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"生成趋势图失败: {str(e)}", exc_info=True)
            return None

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
