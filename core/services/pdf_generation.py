import io
import os
from pathlib import Path

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def build_annual_report_pdf(context) -> io.BytesIO:
    """
    Buduje dokument PDF raportu rocznego na podstawie kontekstu
    zwróconego przez get_annual_report_context().
    Zwraca bufor BytesIO gotowy do odczytu (seek(0) jest już wywołany).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18,
    )

    # --- Rejestracja czcionek ---
    font_name = 'Helvetica'
    font_name_bold = 'Helvetica-Bold'
    try:
        font_path_regular = os.path.join(BASE_DIR, 'Roboto', 'static', 'Roboto-Regular.ttf')
        font_path_bold = os.path.join(BASE_DIR, 'Roboto', 'static', 'Roboto-Bold.ttf')
        pdfmetrics.registerFont(TTFont('Roboto-Regular', font_path_regular))
        pdfmetrics.registerFont(TTFont('Roboto-Bold', font_path_bold))
        pdfmetrics.registerFontFamily('Roboto', normal='Roboto-Regular', bold='Roboto-Bold')
        font_name = 'Roboto-Regular'
        font_name_bold = 'Roboto-Bold'
    except Exception:
        pass  # Fallback do wbudowanych czcionek Helvetica

    styles = getSampleStyleSheet()
    styles['Normal'].fontName = font_name
    styles['h1'].fontName = font_name_bold
    styles['h2'].fontName = font_name_bold
    styles['h1'].alignment = 1

    elements = []

    # --- Tytuł ---
    elements.append(Paragraph(context['title'], styles['h1']))
    elements.append(Spacer(1, 0.25 * inch))

    # --- Podsumowanie roczne ---
    elements.append(Paragraph('Podsumowanie roczne', styles['h2']))
    summary_data = [
        ['Suma wpłat:', f"{context['total_payments']:.2f} zł"],
        ['Należny czynsz:', f"{context['total_rent']:.2f} zł"],
        ['Wywóz śmieci:', f"{context['total_waste_cost_year']:.2f} zł"],
        ['Woda:', f"{context['total_water_cost_year']:.2f} zł"],
        ['Suma kosztów:', f"{context['total_costs']:.2f} zł"],
        ['Bilans:', f"{context['final_balance']:.2f} zł"],
    ]
    summary_table = Table(summary_data, colWidths=[2.5 * inch, 2.5 * inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 4), (0, 4), font_name_bold),
        ('FONTNAME', (0, 5), (0, 5), font_name_bold),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.25 * inch))

    # --- Harmonogram Czynszu ---
    elements.append(Paragraph('Harmonogram Czynszu', styles['h2']))
    rent_data = [['Miesiąc', 'Należny Czynsz']]
    for item in context['rent_schedule']:
        rent_data.append([item['month_name'], f"{item['rent']:.2f} zł"])
    rent_data.append(['Suma:', f"{context['total_rent']:.2f} zł"])
    rent_table = Table(rent_data, colWidths=[2.5 * inch, 2.5 * inch])
    rent_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.gray),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTNAME', (0, 0), (-1, 0), font_name_bold),
        ('FONTNAME', (0, -1), (-1, -1), font_name_bold),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(rent_table)
    elements.append(Spacer(1, 0.25 * inch))

    # --- Zestawienie dwumiesięczne ---
    elements.append(Paragraph('Zestawienie dwumiesięczne kosztów wody i wywozu śmieci', styles['h2']))
    bimonthly_header = ['Okres', 'Wywóz śmieci', 'Zużycie wody', 'Koszt wody']
    bimonthly_table_data = [bimonthly_header]
    for p in context['bimonthly_data']:
        bimonthly_table_data.append([
            p['name'],
            f"{p['waste_cost']:.2f} zł",
            f"{p['water_consumption']:.3f} m³",
            f"{p['water_cost']:.2f} zł",
        ])
    bimonthly_table_data.append([
        'Suma roczna:',
        f"{context['total_waste_cost_year']:.2f} zł",
        f"{context['total_water_consumption_year']:.3f} m³",
        f"{context['total_water_cost_year']:.2f} zł",
    ])
    bimonthly_table = Table(bimonthly_table_data)
    bimonthly_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.gray),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTNAME', (0, 0), (-1, 0), font_name_bold),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), font_name_bold),
    ]))
    elements.append(bimonthly_table)
    elements.append(Spacer(1, 0.5 * inch))

    # --- Wpłaty ---
    elements.append(Paragraph('Wpłaty', styles['h2']))
    payment_data = [['Data', 'Opis', 'Kwota']]
    for p in context['cumulative_payments']:
        payment_data.append([
            p['date'].strftime('%Y-%m-%d'),
            p['description'] or '',
            f"{p['amount']:.2f} zł",
        ])
    payment_data.append(['', 'Suma wpłat:', f"{context['total_payments']:.2f} zł"])
    payment_table = Table(payment_data, colWidths=[1 * inch, 2.7 * inch, 1.3 * inch])
    payment_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.gray),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTNAME', (0, 0), (-1, 0), font_name_bold),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), font_name_bold),
    ]))
    elements.append(payment_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer
