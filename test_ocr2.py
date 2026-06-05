#!/usr/bin/env python
# -*- coding: utf-8 -*-
from app.medical_report import get_medical_report_manager, PDFTextExtractor
from app.database import get_db_context
from app.models import Employee
from datetime import date
import os

manager = get_medical_report_manager()
extractor = PDFTextExtractor()

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
            print("\n=== 全部文本 ===")
            print(repr(text))
            print("\n=== 按行显示 ===")
            for i, line in enumerate(text.split('\n')):
                if line.strip():
                    print(f"{i:3d}: {repr(line)}")

        if os.path.exists(pdf_path):
            os.remove(pdf_path)
