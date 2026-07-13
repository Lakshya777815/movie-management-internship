"""
Utility to generate a PDF ticket for a confirmed booking.
Uses reportlab and qrcode libraries.
"""
import io
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def generate_ticket_pdf(booking):
    """
    Generate a PDF ticket for the given Booking object.
    Returns a BytesIO object containing the PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=22, textColor=colors.HexColor('#1e40af'), spaceAfter=10)
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#64748b'), spaceBefore=6)
    value_style = ParagraphStyle('Value', parent=styles['Normal'], fontSize=13, textColor=colors.HexColor('#1e293b'), spaceBefore=2, fontName='Helvetica-Bold')
    center_style = ParagraphStyle('Center', parent=styles['Normal'], alignment=TA_CENTER, fontSize=10, textColor=colors.HexColor('#64748b'))

    story = []

    # Header bar
    story.append(Paragraph("🎬 MovieApp — Booking Ticket", title_style))
    story.append(Spacer(1, 0.3*cm))

    # Divider line via table
    divider = Table([['']], colWidths=[17*cm], rowHeights=[3])
    divider.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#3b82f6'))]))
    story.append(divider)
    story.append(Spacer(1, 0.5*cm))

    # Ticket details table
    movie = booking.schedule.movie
    schedule = booking.schedule
    theater = schedule.theater

    booking_data = [
        ['MOVIE', movie.title],
        ['THEATER', theater.name],
        ['SCREEN', getattr(theater, 'screen', 'Screen 1')],
        ['LOCATION', theater.location],
        ['DATE', schedule.start_time.strftime('%A, %d %B %Y')],
        ['SHOW TIME', schedule.start_time.strftime('%I:%M %p')],
        ['SEATS', booking.seat_numbers],
        ['BOOKING ID', f'#{booking.id}'],
        ['PASSENGER', booking.user.username],
        ['AMOUNT PAID', f'INR {booking.total_price}'],
        ['PAYMENT REF', booking.payment.transaction_id if hasattr(booking, 'payment') and booking.payment else 'N/A'],
        ['STATUS', 'CONFIRMED ✓'],
    ]

    table = Table(booking_data, colWidths=[5*cm, 12*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#ffffff')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#64748b')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#0f172a')),
        ('FONT', (0, 0), (0, -1), 'Helvetica', 9),
        ('FONT', (1, 0), (1, -1), 'Helvetica-Bold', 11),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f8fafc'), colors.HexColor('#ffffff')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        # Highlight confirmed row
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dcfce7')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#166534')),
    ]))
    story.append(table)
    story.append(Spacer(1, 1*cm))

    # QR Code
    qr_data = f"MOVIEAPP|BKG:{booking.id}|USER:{booking.user.username}|SEATS:{booking.seat_numbers}|REF:{getattr(booking.payment, 'transaction_id', 'N/A') if hasattr(booking, 'payment') else 'N/A'}"
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='#1e293b', back_color='white')
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)

    qr_rl_img = Image(qr_buffer, width=4*cm, height=4*cm)

    qr_table = Table([[qr_rl_img, Paragraph(
        "<b>Scan QR code at the venue</b><br/><br/>Present this ticket on your phone or as a printout.<br/><br/>"
        f"Booking ID: #{booking.id}<br/>This ticket is non-transferable.",
        ParagraphStyle('qr_text', fontSize=10, textColor=colors.HexColor('#334155'), leading=16)
    )]], colWidths=[5*cm, 12*cm])
    qr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(qr_table)
    story.append(Spacer(1, 0.8*cm))

    # Footer
    story.append(Paragraph("Thank you for booking with MovieApp! Arrive 15 minutes early. Enjoy the show! 🍿", center_style))

    doc.build(story)
    buffer.seek(0)
    return buffer
