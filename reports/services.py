import csv
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_csv_report(response, intents):
    writer = csv.writer(response)
    writer.writerow(['ID', 'Customer Name', 'Customer Phone', 'Product', 'Variation', 'Constraint Type', 'Requested Quantity', 'Estimated Value', 'Status', 'Recorded By', 'Created At'])
    
    for intent in intents:
        variation_str = f"{intent.variation.size}/{intent.variation.color}" if intent.variation else "N/A"
        recorded_by_str = intent.recorded_by.username if intent.recorded_by else "System"
        writer.writerow([
            intent.id,
            f"{intent.customer.first_name} {intent.customer.last_name}",
            intent.customer.phone_number,
            intent.product.name,
            variation_str,
            intent.get_constraint_type_display(),
            intent.requested_quantity,
            intent.estimated_value,
            intent.get_status_display(),
            recorded_by_str,
            intent.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    return response

def generate_pdf_report(response, intents):
    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()
    
    # Title Style
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=12,
        textColor=colors.HexColor('#1E3A8A')  # Deep navy color
    )
    story.append(Paragraph("Retail Purchase Constraint Management System (RPCMS)", title_style))
    story.append(Paragraph("Blocked Purchase Intent Report", styles['Heading2']))
    story.append(Spacer(1, 12))
    
    # Table data
    data = [["ID", "Customer", "Product", "Constraint", "Value", "Status", "Date"]]
    for intent in intents:
        cust_name = f"{intent.customer.first_name} {intent.customer.last_name}"
        prod_name = intent.product.name
        if intent.variation:
            prod_name += f" ({intent.variation.size}/{intent.variation.color})"
            
        data.append([
            str(intent.id),
            cust_name,
            prod_name,
            intent.get_constraint_type_display(),
            f"${intent.estimated_value:.2f}" if intent.estimated_value else "$0.00",
            intent.get_status_display(),
            intent.created_at.strftime('%Y-%m-%d')
        ])
        
    t = Table(data, colWidths=[30, 90, 160, 90, 50, 60, 60])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F8FAFC')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
    ]))
    story.append(t)
    doc.build(story)
    return response
