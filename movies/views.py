from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib import messages
from django.db.models import Avg, Count, Sum, Q, Min, Max
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator
from django.core.mail import EmailMessage
from django.conf import settings
from django.urls import reverse
from datetime import timedelta
import uuid, json, threading, stripe
from .models import Movie, Review, Booking, ShowSchedule, SeatReservation, Payment, Genre, Language, Theater, MoviePoster
from .forms import ReviewForm, UserRegisterForm, MovieUploadForm
from .ticket_generator import generate_ticket_pdf
from .tasks import send_ticket_email_task


# ─────────────────────────────────────────────
#  EMAIL HELPER (runs in background thread)
# ─────────────────────────────────────────────

def _send_ticket_email(booking_id):
    """Background thread: generate PDF and email it to the user."""
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
            email.send(fail_silently=True)
    except Exception as e:
        print(f"[Ticket Email] Error for booking {booking_id}: {e}")


def send_ticket_email_async(booking_id):
    """Start email sending in a background thread so booking doesn't wait."""
    thread = threading.Thread(target=_send_ticket_email, args=(booking_id,), daemon=True)
    thread.start()


def send_ticket_email_safe(booking_id):
    """Try queuing email via Celery. Fall back to local background thread if Redis is offline."""
    try:
        send_ticket_email_task.delay(booking_id)
        print(f"[Ticket Email] Enqueued in Celery for booking {booking_id}")
    except Exception as e:
        print(f"[Ticket Email] Celery/Redis connection failed: {e}. Falling back to background thread.")
        send_ticket_email_async(booking_id)


# ─────────────────────────────────────────────
#  HOME + MOVIE DETAIL
# ─────────────────────────────────────────────

def home(request):
    trending_movies = Movie.objects.annotate(num_reviews=Count('reviews')).order_by('-num_reviews')[:6]
    recent_movies = Movie.objects.order_by('-release_date')[:6]
    return render(request, 'movies/home.html', {
        'trending_movies': trending_movies,
        'recent_movies': recent_movies,
    })


def movie_detail(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    reviews = movie.reviews.all().order_by('-created_at')
    similar_movies = Movie.objects.filter(
        Q(genres__in=movie.genres.all()) | Q(languages__in=movie.languages.all())
    ).exclude(pk=movie.pk).distinct()[:4]

    review_form = None
    has_watched = False
    user_review = None
    schedules = movie.schedules.filter(start_time__gt=timezone.now()).order_by('start_time')[:5]

    if request.user.is_authenticated:
        has_watched = Booking.objects.filter(
            user=request.user,
            schedule__movie=movie,
            schedule__start_time__lte=timezone.now(),
            payment_status='success'
        ).exists()
        user_review = reviews.filter(user=request.user).first()

        if request.method == 'POST' and has_watched:
            review_form = ReviewForm(request.POST, instance=user_review)
            if review_form.is_valid():
                review = review_form.save(commit=False)
                review.movie = movie
                review.user = request.user
                review.save()
                messages.success(request, "Your review has been saved!")
                return redirect('movie_detail', pk=movie.pk)
        else:
            review_form = ReviewForm(instance=user_review)

    return render(request, 'movies/movie_detail.html', {
        'movie': movie,
        'reviews': reviews,
        'similar_movies': similar_movies,
        'review_form': review_form,
        'has_watched': has_watched,
        'user_review': user_review,
        'schedules': schedules,
    })


# ─────────────────────────────────────────────
#  TASK 5: ENHANCED SEARCH & DISCOVERY
# ─────────────────────────────────────────────

def search_movies(request):
    query = request.GET.get('q', '').strip()
    genre_id = request.GET.get('genre', '')
    language_id = request.GET.get('language', '')
    city = request.GET.get('city', '').strip()
    theater_id = request.GET.get('theater', '')
    min_rating = request.GET.get('min_rating', '')
    max_price = request.GET.get('max_price', '')
    min_price = request.GET.get('min_price', '')
    show_date = request.GET.get('show_date', '')
    sort_by = request.GET.get('sort', '-release_date')

    movies = Movie.objects.all()

    if query:
        movies = movies.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(cast__name__icontains=query)
        ).distinct()

    if genre_id:
        movies = movies.filter(genres__id=genre_id)

    if language_id:
        movies = movies.filter(languages__id=language_id)

    if city:
        movies = movies.filter(schedules__theater__location__icontains=city)

    if theater_id:
        movies = movies.filter(schedules__theater__id=theater_id)

    if show_date:
        movies = movies.filter(schedules__start_time__date=show_date)

    if min_price:
        movies = movies.filter(ticket_price__gte=min_price)

    if max_price:
        movies = movies.filter(ticket_price__lte=max_price)

    if min_rating:
        movies = movies.annotate(avg_rating=Avg('reviews__rating')).filter(avg_rating__gte=float(min_rating))

    movies = movies.distinct()

    SORT_OPTIONS = {
        '-release_date': '-release_date',
        'release_date': 'release_date',
        'title': 'title',
        '-title': '-title',
        '-ticket_price': '-ticket_price',
        'ticket_price': 'ticket_price',
    }
    if sort_by == 'popularity':
        movies = movies.annotate(num_bookings=Count('schedules__bookings')).order_by('-num_bookings')
    elif sort_by == 'rating':
        movies = movies.annotate(avg_r=Avg('reviews__rating')).order_by('-avg_r')
    else:
        movies = movies.order_by(SORT_OPTIONS.get(sort_by, '-release_date'))

    total_count = movies.count()

    # Recommended for You
    recommended = []
    if request.user.is_authenticated:
        booked_genres = Genre.objects.filter(
            movies__schedules__bookings__user=request.user
        ).distinct()
        if booked_genres.exists():
            recommended = Movie.objects.filter(
                genres__in=booked_genres
            ).exclude(
                schedules__bookings__user=request.user
            ).annotate(num_reviews=Count('reviews')).order_by('-num_reviews').distinct()[:4]

    # Pagination
    paginator = Paginator(movies, 9)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    genres = Genre.objects.all()
    languages = Language.objects.all()
    theaters = Theater.objects.all()
    cities = Theater.objects.values_list('location', flat=True).distinct()
    price_range = Movie.objects.aggregate(min_p=Min('ticket_price'), max_p=Max('ticket_price'))

    return render(request, 'movies/search.html', {
        'page_obj': page_obj,
        'movies': page_obj,
        'total_count': total_count,
        'query': query,
        'genres': genres,
        'languages': languages,
        'theaters': theaters,
        'cities': cities,
        'selected_genre': genre_id,
        'selected_language': language_id,
        'selected_city': city,
        'selected_theater': theater_id,
        'min_rating': min_rating,
        'min_price': min_price,
        'max_price': max_price,
        'show_date': show_date,
        'sort_by': sort_by,
        'price_range': price_range,
        'recommended': recommended,
    })


# ─────────────────────────────────────────────
#  TASK 2: SEAT RESERVATION
# ─────────────────────────────────────────────

@login_required
def seat_selection(request, schedule_id):
    schedule = get_object_or_404(ShowSchedule, pk=schedule_id)
    theater = schedule.theater

    SeatReservation.objects.filter(expires_at__lte=timezone.now()).delete()

    booked_set = set()
    for b in schedule.bookings.filter(payment_status='success'):
        for seat in b.seat_numbers.split(','):
            if seat.strip():
                booked_set.add(seat.strip())

    reserved_set = set(
        sr.seat_number for sr in schedule.seat_reservations.filter(expires_at__gt=timezone.now())
    )
    my_reserved = set(
        sr.seat_number for sr in schedule.seat_reservations.filter(
            user=request.user, expires_at__gt=timezone.now()
        )
    )

    seat_map = []
    row_labels = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    for r in range(theater.rows):
        row = []
        for s in range(1, theater.seats_per_row + 1):
            seat_id = f"{row_labels[r]}{s}"
            if seat_id in booked_set:
                status = 'booked'
            elif seat_id in reserved_set and seat_id not in my_reserved:
                status = 'reserved'
            elif seat_id in my_reserved:
                status = 'mine'
            else:
                status = 'available'
            row.append({'id': seat_id, 'status': status})
        seat_map.append({'label': row_labels[r], 'seats': row})

    if request.method == 'POST':
        selected_seats = request.POST.getlist('seats')
        if not selected_seats:
            messages.error(request, "Please select at least one seat.")
            return redirect('seat_selection', schedule_id=schedule_id)

        SeatReservation.objects.filter(user=request.user, schedule=schedule).delete()

        try:
            with transaction.atomic():
                for seat_id in selected_seats:
                    if seat_id in booked_set or (seat_id in reserved_set and seat_id not in my_reserved):
                        messages.error(request, f"Seat {seat_id} is no longer available. Please try again.")
                        return redirect('seat_selection', schedule_id=schedule_id)
                    SeatReservation.objects.create(
                        schedule=schedule, user=request.user, seat_number=seat_id
                    )
        except Exception:
            messages.error(request, "Could not reserve seats. Please try again.")
            return redirect('seat_selection', schedule_id=schedule_id)

        total = schedule.movie.ticket_price * len(selected_seats)
        booking = Booking.objects.create(
            user=request.user,
            schedule=schedule,
            seats_booked=len(selected_seats),
            seat_numbers=','.join(selected_seats),
            total_price=total,
            payment_status='pending'
        )
        return redirect('payment_form', booking_id=booking.id)

    return render(request, 'movies/seat_selection.html', {
        'schedule': schedule,
        'seat_map': seat_map,
        'ticket_price': schedule.movie.ticket_price,
    })


@login_required
@require_POST
def check_seat_status(request):
    schedule_id = request.POST.get('schedule_id')
    schedule = get_object_or_404(ShowSchedule, pk=schedule_id)
    SeatReservation.objects.filter(expires_at__lte=timezone.now()).delete()

    booked_seats = set()
    for b in schedule.bookings.filter(payment_status='success'):
        for seat in b.seat_numbers.split(','):
            if seat.strip():
                booked_seats.add(seat.strip())

    reserved_seats = set(
        sr.seat_number for sr in schedule.seat_reservations.filter(expires_at__gt=timezone.now())
    )
    return JsonResponse({'booked': list(booked_seats), 'reserved': list(reserved_seats)})


# ─────────────────────────────────────────────
#  TASK 3: PAYMENT
# ─────────────────────────────────────────────

# Stripe Initialization
stripe.api_key = settings.STRIPE_SECRET_KEY

@login_required
def payment_form(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    
    # If the database expired or cancelled it, user needs to pick seats again
    if booking.payment_status in ['failed', 'cancelled']:
        messages.warning(request, "Your reserved seat lock expired or the payment failed. Please choose seats again.")
        return redirect('seat_selection', schedule_id=booking.schedule.id)
        
    if booking.payment_status == 'success':
        return redirect('booking_confirmation', booking_id=booking.id)

    # Detect if we should use Stripe or sandboxed fallback
    is_stripe_configured = settings.STRIPE_SECRET_KEY and not settings.STRIPE_SECRET_KEY.startswith('sk_test_placeholder')

    return render(request, 'movies/payment_form.html', {
        'booking': booking,
        'stripe_configured': is_stripe_configured
    })


@login_required
def create_stripe_checkout_session(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)

    if booking.payment_status == 'success':
        return redirect('booking_confirmation', booking_id=booking.id)

    is_stripe_configured = settings.STRIPE_SECRET_KEY and not settings.STRIPE_SECRET_KEY.startswith('sk_test_placeholder')

    if not is_stripe_configured:
        messages.info(request, "Redirecting to Secure Sandbox Payment simulator...")
        return redirect('payment_sandbox', booking_id=booking.id)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'inr',
                    'product_data': {
                        'name': f"Tickets to '{booking.schedule.movie.title}'",
                        'description': f"Theater: {booking.schedule.theater.name} | Seats: {booking.seat_numbers}",
                    },
                    'unit_amount': int(booking.total_price * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            metadata={'booking_id': booking.id},
            success_url=request.build_absolute_uri(
                reverse('payment_success', kwargs={'booking_id': booking.id})
            ) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.build_absolute_uri(
                reverse('payment_cancel', kwargs={'booking_id': booking.id})
            ),
        )
        return redirect(session.url, code=303)
    except Exception as e:
        messages.error(request, f"Stripe Checkout Session error: {str(e)}. Redirecting to Sandbox fallback instead.")
        return redirect('payment_sandbox', booking_id=booking.id)


@login_required
def payment_success(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    session_id = request.GET.get('session_id')

    if session_id:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            if session.payment_status == 'paid':
                with transaction.atomic():
                    booking = Booking.objects.select_for_update().get(id=booking_id)
                    if booking.payment_status != 'success':
                        booking.payment_status = 'success'
                        booking.save()
                        
                        # Create Payment record
                        txn_id = session.payment_intent or f"STN{session.id[:16]}"
                        Payment.objects.get_or_create(
                            booking=booking,
                            defaults={
                                'transaction_id': txn_id,
                                'amount': booking.total_price,
                                'status': 'success',
                                'payment_method': 'Stripe'
                            }
                        )
                        
                        # Release seat reservations
                        seats = [s.strip() for s in booking.seat_numbers.split(',') if s.strip()]
                        SeatReservation.objects.filter(schedule=booking.schedule, seat_number__in=seats).delete()
                        
                        # Send async celery ticket email
                        send_ticket_email_safe(booking.id)
                
                messages.success(request, "Payment successful! Your tickets are confirmed.")
            else:
                messages.warning(request, "Your payment remains pending.")
                return redirect('payment_form', booking_id=booking.id)
        except Exception as e:
            messages.error(request, f"Error verifying payment: {str(e)}")
            return redirect('payment_form', booking_id=booking.id)
    
    return redirect('booking_confirmation', booking_id=booking.id)


@login_required
def payment_cancel(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    
    # Mark booking as cancelled or failed
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(id=booking_id)
        if booking.payment_status == 'pending':
            booking.payment_status = 'cancelled'
            booking.save()
            
            # Release/delete seat reservations (failed/cancelled payments release reserved seats)
            seats = [s.strip() for s in booking.seat_numbers.split(',') if s.strip()]
            SeatReservation.objects.filter(schedule=booking.schedule, seat_number__in=seats).delete()
            
    return render(request, 'movies/payment_cancel.html', {'booking': booking})


@login_required
def payment_sandbox(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    if booking.payment_status == 'success':
        return redirect('booking_confirmation', booking_id=booking.id)
    
    if booking.payment_status in ['failed', 'cancelled']:
        messages.warning(request, "This booking payment session has expired or failed. Please choose seats again.")
        return redirect('seat_selection', schedule_id=booking.schedule.id)

    return render(request, 'movies/sandbox_checkout.html', {'booking': booking})


@login_required
@require_POST
def sandbox_process_payment(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    action = request.POST.get('action')

    if action == 'success':
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(id=booking_id)
            if booking.payment_status != 'success':
                booking.payment_status = 'success'
                booking.save()
                
                # Create Payment record
                txn_id = f"SANDBOX-{uuid.uuid4().hex[:12].upper()}"
                Payment.objects.get_or_create(
                    booking=booking,
                    defaults={
                        'transaction_id': txn_id,
                        'amount': booking.total_price,
                        'status': 'success',
                        'payment_method': 'Sandbox-Stripe'
                    }
                )
                
                # Release seat reservations
                seats = [s.strip() for s in booking.seat_numbers.split(',') if s.strip()]
                SeatReservation.objects.filter(schedule=booking.schedule, seat_number__in=seats).delete()
                
                # Send async celery ticket email
                send_ticket_email_safe(booking.id)
        
        messages.success(request, f"Simulated payment successful! Transaction ID: {txn_id}.")
        return redirect('booking_confirmation', booking_id=booking.id)

    elif action == 'fail':
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(id=booking_id)
            if booking.payment_status == 'pending':
                booking.payment_status = 'failed'
                booking.save()
                
                # Release seat reservations
                seats = [s.strip() for s in booking.seat_numbers.split(',') if s.strip()]
                SeatReservation.objects.filter(schedule=booking.schedule, seat_number__in=seats).delete()
        
        messages.error(request, "Simulated payment failed. Reserved seats released.")
        return redirect('payment_cancel', booking_id=booking.id)

    elif action == 'cancel':
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(id=booking_id)
            if booking.payment_status == 'pending':
                booking.payment_status = 'cancelled'
                booking.save()
                
                # Release seat reservations
                seats = [s.strip() for s in booking.seat_numbers.split(',') if s.strip()]
                SeatReservation.objects.filter(schedule=booking.schedule, seat_number__in=seats).delete()
        
        messages.info(request, "Simulated payment selection cancelled. Seats released.")
        return redirect('payment_cancel', booking_id=booking.id)

    return redirect('payment_form', booking_id=booking.id)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload = request.body
    sig_header = request.headers.get('STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400)

    # Process events completely on the server-side
    event_type = event.get('type')
    if event_type == 'checkout.session.completed':
        session = event['data']['object']
        booking_id = session.get('metadata', {}).get('booking_id')
        if booking_id:
            try:
                with transaction.atomic():
                    booking = Booking.objects.select_for_update().get(id=booking_id)
                    if booking.payment_status != 'success':
                        booking.payment_status = 'success'
                        booking.save()
                        
                        # Create Payment record
                        txn_id = session.get('payment_intent') or f"STN{session.get('id')[:16]}"
                        Payment.objects.get_or_create(
                            booking=booking,
                            defaults={
                                'transaction_id': txn_id,
                                'amount': booking.total_price,
                                'status': 'success',
                                'payment_method': 'Stripe'
                            }
                        )
                        
                        # Release seat reservations
                        seats = [s.strip() for s in booking.seat_numbers.split(',') if s.strip()]
                        SeatReservation.objects.filter(schedule=booking.schedule, seat_number__in=seats).delete()
                        
                        # Send async celery ticket email
                        send_ticket_email_safe(booking.id)
            except Booking.DoesNotExist:
                pass
    elif event_type in ['checkout.session.expired', 'payment_intent.payment_failed']:
        session = event['data']['object']
        booking_id = session.get('metadata', {}).get('booking_id')
        if booking_id:
            try:
                with transaction.atomic():
                    booking = Booking.objects.select_for_update().get(id=booking_id)
                    if booking.payment_status == 'pending':
                        booking.payment_status = 'failed'
                        booking.save()
                        
                        # Release seat reservations
                        seats = [s.strip() for s in booking.seat_numbers.split(',') if s.strip()]
                        SeatReservation.objects.filter(schedule=booking.schedule, seat_number__in=seats).delete()
            except Booking.DoesNotExist:
                pass

    return HttpResponse(status=200)


@login_required
def booking_confirmation(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    return render(request, 'movies/booking_confirmation.html', {'booking': booking})


@login_required
def my_bookings(request):
    bookings = request.user.bookings.select_related(
        'schedule__movie', 'schedule__theater'
    ).order_by('-booking_time')
    return render(request, 'movies/my_bookings.html', {'bookings': bookings})


# ─────────────────────────────────────────────
#  TASK 6: DOWNLOAD TICKET PDF
# ─────────────────────────────────────────────

@login_required
def download_ticket(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related('user', 'schedule__movie', 'schedule__theater', 'payment'),
        pk=booking_id,
        user=request.user,
        payment_status='success'
    )
    pdf_buffer = generate_ticket_pdf(booking)
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="MovieApp_Ticket_Booking_{booking.id}.pdf"'
    return response


# ─────────────────────────────────────────────
#  TASK 4: ADMIN ANALYTICS DASHBOARD
# ─────────────────────────────────────────────

def is_admin(user):
    return user.is_staff


@user_passes_test(is_admin, login_url='/admin/login/')
def admin_dashboard(request):
    from django.db.models.functions import TruncDay, TruncMonth

    total_revenue = Payment.objects.filter(status='success').aggregate(total=Sum('amount'))['total'] or 0
    total_bookings = Booking.objects.filter(payment_status='success').count()
    total_movies = Movie.objects.count()
    total_users = Booking.objects.values('user').distinct().count()

    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_revenue = Payment.objects.filter(
        status='success', created_at__gte=thirty_days_ago
    ).annotate(day=TruncDay('created_at')).values('day').annotate(total=Sum('amount')).order_by('day')

    daily_labels = [entry['day'].strftime('%b %d') for entry in daily_revenue]
    daily_data = [float(entry['total']) for entry in daily_revenue]

    top_movies = Movie.objects.annotate(
        booking_count=Count('schedules__bookings', filter=Q(schedules__bookings__payment_status='success'))
    ).order_by('-booking_count')[:5]

    theater_stats = Theater.objects.annotate(
        booking_count=Count('schedules__bookings', filter=Q(schedules__bookings__payment_status='success')),
        revenue=Sum('schedules__bookings__total_price', filter=Q(schedules__bookings__payment_status='success'))
    ).order_by('-booking_count')

    recent_bookings = Booking.objects.filter(payment_status='success').select_related(
        'user', 'schedule__movie', 'schedule__theater'
    ).order_by('-booking_time')[:10]

    monthly_revenue = Payment.objects.filter(status='success').annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(total=Sum('amount')).order_by('month')

    month_labels = [entry['month'].strftime('%b %Y') for entry in monthly_revenue]
    month_data = [float(entry['total']) for entry in monthly_revenue]

    return render(request, 'movies/admin_dashboard.html', {
        'total_revenue': total_revenue,
        'total_bookings': total_bookings,
        'total_movies': total_movies,
        'total_users': total_users,
        'daily_labels': json.dumps(daily_labels),
        'daily_data': json.dumps(daily_data),
        'month_labels': json.dumps(month_labels),
        'month_data': json.dumps(month_data),
        'top_movies': top_movies,
        'theater_stats': theater_stats,
        'recent_bookings': recent_bookings,
    })


def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}! You can now book tickets.')
            auth_login(request, user)
            return redirect('home')
    else:
        form = UserRegisterForm()
    return render(request, 'movies/register.html', {'form': form})


def logout_view(request):
    auth_logout(request)
    messages.info(request, "You have been successfully logged out.")
    return redirect('home')


@user_passes_test(is_admin, login_url='/login/')
def upload_movie(request):
    if request.method == 'POST':
        form = MovieUploadForm(request.POST, request.FILES)
        if form.is_valid():
            movie = form.save()
            poster_image_file = request.FILES.get('poster_image')
            if poster_image_file:
                MoviePoster.objects.create(
                    movie=movie,
                    image=poster_image_file,
                    is_primary=True
                )
            messages.success(request, f'Movie "{movie.title}" and its poster have been uploaded successfully!')
            return redirect('admin_dashboard')
    else:
        form = MovieUploadForm()
    return render(request, 'movies/upload_movie.html', {'form': form})
