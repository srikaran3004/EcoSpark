#!/usr/bin/env python3
"""
Simple markdown-to-PDF generator using ReportLab.
Reads `docs/SRS.md` (relative to the repo root) and writes `docs/SRS.pdf`.
This minimal converter treats Markdown headings starting with `#` and `##` as title/heading
and preserves other paragraphs. It intentionally avoids extra dependencies so it only
requires `reportlab`.
"""
import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def md_to_pdf(md_path, pdf_path):
    if not os.path.exists(md_path):
        print(f"Markdown file not found: {md_path}")
        sys.exit(1)

    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # Split into paragraphs by blank lines
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=72)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, leading=22)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=14, leading=18)
    normal = styles['Normal']

    story = []

    for p in paragraphs:
        if p.startswith('# '):
            story.append(Paragraph(p[2:].strip(), title_style))
            story.append(Spacer(1, 12))
        elif p.startswith('## '):
            story.append(Paragraph(p[3:].strip(), heading_style))
            story.append(Spacer(1, 8))
        else:
            # Escape XML-sensitive chars and preserve simple newlines
            p_esc = p.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            p_esc = p_esc.replace('\n', '<br/>')
            story.append(Paragraph(p_esc, normal))
            story.append(Spacer(1, 6))

    doc.build(story)


if __name__ == '__main__':
    # Compute paths relative to repo root (two levels up from this script location)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, '..'))
    md_path = os.path.join(repo_root, 'docs', 'SRS.md')
    pdf_path = os.path.join(repo_root, 'docs', 'SRS.pdf')

    print(f"Reading Markdown: {md_path}")
    print(f"Writing PDF: {pdf_path}")

    md_to_pdf(md_path, pdf_path)

    print('PDF generation complete.')
