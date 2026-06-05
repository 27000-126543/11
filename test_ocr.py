#!/usr/bin/env python
# -*- coding: utf-8 -*-
from app.medical_report import get_medical_report_manager, PDFTextExtractor, IndicatorExtractor
from app.database import get_db_context
from app.models import Employee
from datetime import date
import os

manager = get_medical_report_manager()
extractor = PDFTextExtractor()
indicator_extractor = IndicatorExtractor()

with get_db_context() as db:
    emp = db.query(Employee).first()
    if emp:
        output_path = 'test_sample_report.pdf'
        pdf_path = manager.sample_generator.generate_sample_report(
            employee=emp,
            report_date=date.today(),
            output_path=output_path,
            include_abnormal=True
        )

        if pdf_path and os.path.exists(pdf_path):
            text = extractor.extract_text_from_pdf(pdf_path)
            print(f"文本长度: {len(text)}")

            for line in text.split('\n'):
                if '空腹血糖' in line or '总胆固醇' in line:
                    print(f"找到匹配行: {repr(line)}")

            indicators = indicator_extractor.extract_indicators(text)
            print(f"\n提取到 {len(indicators)} 项指标")
            for ind in indicators[:10]:
                status = '✗' if ind['is_abnormal'] else '✓'
                print(f"  {status} {ind['indicator_name']}: {ind['value']} {ind['unit']}")

        if os.path.exists(pdf_path):
            os.remove(pdf_path)
