from celery import shared_task
from django.core.mail import EmailMessage
from django.conf import settings
from .models import Booking
from .ticket_generator import generate_ticket_pdf
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def send_ticket_email_task(self, booking_id):
    """
    Task to generate PDF and send email to movie booker.
    Automatically retries on failure.
    """
    try:
        booking = Booking.objects.select_related(
            'user', 'schedule__movie', 'schedule__theater', 'payment'
        ).get(pk=booking_id)
        
        pdf_buffer = generate_ticket_pdf(booking)
        
        email = EmailMessage(
            subject=f"Your MovieApp Ticket — {booking.schedule.movie.title}",
            body=(
                f"Hi {booking.user.username},\n\n"
                f"Your booking for '{booking.schedule.movie.title}' is confirmed!\n\n"
                f"  Booking ID  : #{booking.id}\n"
                f"  Theater     : {booking.schedule.theater.name}\n"
                f"  Date & Time : {booking.schedule.start_time.strftime('%d %b %Y, %I:%M %p')}\n"
                f"  Seats       : {booking.seat_numbers}\n"
                f"  Amount Paid : INR {booking.total_price}\n\n"
                f"Find your e-ticket PDF attached. Scan the QR code at the venue.\n\n"
                f"Enjoy the show! 🎬\n— MovieApp Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[booking.user.email] if booking.user.email else [],
        )
        
        if booking.user.email:
            email.attach(
                f'ticket_booking_{booking.id}.pdf',
                pdf_buffer.read(),
                'application/pdf'
            )
            email.send(fail_silently=False)
        else:
            logger.warning(f"No email for user: {booking.user.username}")
    except Exception as exc:
        logger.error(f"Error sending ticket email for booking {booking_id}: {exc}. Retrying...")
        raise self.retry(exc=exc)
