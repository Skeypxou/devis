
"""Génération PDF des devis et factures."""
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

def generer_pdf(document, entreprise, type_document="DEVIS"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SmallRight", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=9))
    story = []
    story.append(Paragraph(entreprise.get("entreprise_nom", "Atelier PVC Pro"), styles["Title"]))
    coords = " · ".join(filter(None, [
        entreprise.get("entreprise_adresse", ""),
        entreprise.get("entreprise_telephone", ""),
        entreprise.get("entreprise_email", "")
    ]))
    if coords:
        story.append(Paragraph(coords, styles["Normal"]))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph(f"<b>{type_document} {document.get('numero','')}</b>", styles["Heading1"]))
    story.append(Paragraph(f"Date : {document.get('date','')} &nbsp;&nbsp; Client : {document.get('client_nom','')}", styles["Normal"]))
    story.append(Spacer(1, 5*mm))
    rows = [["Désignation", "Dimensions (m)", "Qté", "PVC (DA)", "Vitrage (DA)", "Total (DA)"]]
    for ligne in document.get("lignes", []):
        dims = f"{ligne.get('largeur',0):.2f} × {ligne.get('hauteur',0):.2f}"
        rows.append([
            str(ligne.get("designation", "Menuiserie"))[:70], dims,
            str(ligne.get("quantite", 1)),
            f"{ligne.get('cout_pvc',0):,.2f}",
            f"{ligne.get('cout_vitrage',0):,.2f}",
            f"{ligne.get('total_ligne',0):,.2f}"
        ])
    table = Table(rows, repeatRows=1, colWidths=[47*mm, 23*mm, 10*mm, 25*mm, 25*mm, 28*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#176B87")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1),8),
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#D7DEE8")),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F4F7FB")]),
        ("ALIGN",(2,1),(-1,-1),"RIGHT"),
        ("LEFTPADDING",(0,0),(-1,-1),5),
        ("RIGHTPADDING",(0,0),(-1,-1),5),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    story.extend([table, Spacer(1, 6*mm)])
    total = document.get("total_ttc", document.get("total", 0))
    story.append(Paragraph(f"<b>Total : {total:,.2f} DA</b>", styles["Heading2"]))
    if document.get("conditions"):
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph(f"Conditions : {document['conditions']}", styles["Normal"]))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Signature / cachet", styles["Normal"]))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
