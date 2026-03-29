"""
SIRH — Générateur de bulletins PDF
Utilise ReportLab pour la génération.
"""

import os
from datetime import datetime

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'exports')


def generer_bulletin_pdf(bulletin, agent, lignes):
    """
    Générer un bulletin de paie PDF.
    bulletin : dict avec les données du bulletin
    agent : dict avec les données de l'agent
    lignes : list de dicts (lignes de bulletin)
    Retourne : chemin du fichier PDF
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

    os.makedirs(EXPORTS_DIR, exist_ok=True)

    matricule = agent.get('matricule', 'UNKNOWN')
    periode = bulletin.get('periode', '2026-03')
    filename = f"bulletin_{matricule}_{periode}.pdf"
    filepath = os.path.join(EXPORTS_DIR, filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
    )

    styles = getSampleStyleSheet()

    # Couleurs
    navy = HexColor('#1A3A5C')
    green = HexColor('#1E4A2E')
    gold = HexColor('#D4AF37')
    light_bg = HexColor('#F0F4F8')
    white_bg = HexColor('#FFFFFF')

    # Styles personnalisés
    title_style = ParagraphStyle('BulletinTitle', parent=styles['Title'], fontSize=16,
                                  textColor=navy, alignment=TA_CENTER, spaceAfter=4)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10,
                                     textColor=HexColor('#666666'), alignment=TA_CENTER, spaceAfter=12)
    section_style = ParagraphStyle('Section', parent=styles['Heading3'], fontSize=11,
                                    textColor=navy, spaceAfter=6, spaceBefore=12)
    normal_style = ParagraphStyle('Norm', parent=styles['Normal'], fontSize=9)
    small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, textColor=HexColor('#888888'))

    def fmt(n):
        if n is None or n == 0: return ''
        return '{:,.0f}'.format(n).replace(',', ' ')

    elements = []

    # ── En-tête ─────────────────────────────────────────────────────
    elements.append(Paragraph("🇸🇳 RÉPUBLIQUE DU SÉNÉGAL", subtitle_style))
    elements.append(Paragraph("BULLETIN DE PAIE", title_style))
    elements.append(Paragraph(f"Période : {periode}", subtitle_style))
    elements.append(Spacer(1, 8))

    # ── Employeur ───────────────────────────────────────────────────
    elements.append(Paragraph("EMPLOYEUR", section_style))
    emp_data = [
        ['Ministère :', agent.get('ministere_nom', '-')],
        ['Direction :', agent.get('direction_nom', '-')],
        ['Service :', agent.get('service_nom', '-')],
    ]
    emp_table = Table(emp_data, colWidths=[4*cm, 14*cm])
    emp_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, -1), light_bg),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CCCCCC')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(emp_table)
    elements.append(Spacer(1, 8))

    # ── Agent ───────────────────────────────────────────────────────
    elements.append(Paragraph("AGENT", section_style))
    ag_data = [
        ['Nom & Prénom :', f"{agent.get('nom','')} {agent.get('prenom','')}", 'Matricule :', matricule],
        ['Statut :', agent.get('statut',''), 'Corps :', agent.get('corps','')],
        ['Grade :', agent.get('grade',''), 'Échelon :', str(agent.get('echelon',''))],
        ['Indice :', str(agent.get('indice','')), 'Situation :', agent.get('situation_matrimoniale','')],
        ['Enfants :', str(agent.get('nb_enfants',0)), 'Date entrée :', agent.get('date_entree','')],
    ]
    ag_table = Table(ag_data, colWidths=[3.5*cm, 5*cm, 3.5*cm, 6*cm])
    ag_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CCCCCC')),
        ('BACKGROUND', (0, 0), (-1, -1), white_bg),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(ag_table)
    elements.append(Spacer(1, 12))

    # ── Tableau principal ───────────────────────────────────────────
    elements.append(Paragraph("DÉTAIL DE LA RÉMUNÉRATION", section_style))

    header = ['Code', 'Rubrique', 'Base', 'Taux', 'Gains', 'Retenues']
    table_data = [header]

    for l in lignes:
        table_data.append([
            l.get('rubrique_code', ''),
            l.get('rubrique_libelle', ''),
            fmt(l.get('base', 0)),
            str(l.get('taux', '')) if l.get('taux') else '',
            fmt(l.get('montant_gain', 0)),
            fmt(l.get('montant_retenue', 0)),
        ])

    # Totaux
    total_gains = sum(l.get('montant_gain', 0) for l in lignes)
    total_retenues = sum(l.get('montant_retenue', 0) for l in lignes)

    table_data.append(['', 'TOTAUX', '', '', fmt(total_gains), fmt(total_retenues)])
    table_data.append(['', '', '', '', '', ''])
    table_data.append(['', 'NET À PAYER', '', '', fmt(bulletin.get('salaire_net', 0)), ''])

    main_table = Table(table_data, colWidths=[2*cm, 6.5*cm, 2.5*cm, 1.8*cm, 2.5*cm, 2.5*cm])
    styles_table = [
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), navy),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CCCCCC')),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    # Style totaux
    total_row = len(table_data) - 3
    net_row = len(table_data) - 1
    styles_table.extend([
        ('FONTNAME', (0, total_row), (-1, total_row), 'Helvetica-Bold'),
        ('BACKGROUND', (0, total_row), (-1, total_row), light_bg),
        ('LINEABOVE', (0, total_row), (-1, total_row), 1.5, navy),
        ('FONTNAME', (0, net_row), (-1, net_row), 'Helvetica-Bold'),
        ('FONTSIZE', (0, net_row), (-1, net_row), 11),
        ('BACKGROUND', (0, net_row), (-1, net_row), HexColor('#D1FAE5')),
        ('TEXTCOLOR', (0, net_row), (-1, net_row), green),
    ])

    main_table.setStyle(TableStyle(styles_table))
    elements.append(main_table)
    elements.append(Spacer(1, 12))

    # ── Charges patronales ──────────────────────────────────────────
    elements.append(Paragraph("CHARGES PATRONALES", section_style))

    cp_data = [
        ['Rubrique', 'Montant (FCFA)'],
        ['IPRES RG Employeur', fmt(bulletin.get('charges_patronales_ipres_rg', 0))],
        ['IPRES RC Employeur', fmt(bulletin.get('charges_patronales_ipres_rc', 0))],
        ['CSS Allocations Familiales', fmt(bulletin.get('charges_patronales_css_af', 0))],
        ['CSS Accidents du Travail', fmt(bulletin.get('charges_patronales_css_at', 0))],
        ['CFCE', fmt(bulletin.get('charges_patronales_cfce', 0))],
        ['TOTAL CHARGES', fmt(bulletin.get('total_charges_patronales', 0))],
        ['COÛT EMPLOYEUR TOTAL', fmt(bulletin.get('cout_employeur', 0))],
    ]

    cp_table = Table(cp_data, colWidths=[10*cm, 4*cm])
    cp_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), navy),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CCCCCC')),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -2), (-1, -2), light_bg),
        ('BACKGROUND', (0, -1), (-1, -1), HexColor('#FEF3C7')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(cp_table)
    elements.append(Spacer(1, 20))

    # ── Pied de page ────────────────────────────────────────────────
    elements.append(Paragraph(
        f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — "
        "Ce bulletin est confidentiel et destiné uniquement à l'agent concerné.",
        small_style
    ))

    # Générer
    doc.build(elements)
    return filepath


if __name__ == '__main__':
    print("Module PDF chargé. Utilisez generer_bulletin_pdf() pour générer un bulletin.")
