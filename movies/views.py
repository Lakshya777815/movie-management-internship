from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Avg, Count, Sum, Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta
import uuid, json
from .models import Movie, Review, Booking, ShowSchedule, SeatReservation, Payment, Genre, Language, Theater
from .forms import ReviewForm


# ──────────────────────────────────────────────
# HOME + MOVIE DETAIL
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# TASK 5: SEARCH & DISCOVERY
# ──────────────────────────────────────────────

def search_movies(request):
    query = request.GET.get('q', '').strip()
    genre_id = request.GET.get('genre', '')
    language_id = request.GET.get('language', '')
    min_rating = request.GET.get('min_rating', '')
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

    if min_rating:
        movies = movies.annotate(avg_rating=Avg('reviews__rating')).filter(avg_rating__gte=float(min_rating))

    SORT_OPTIONS = {
        '-release_date': '-release_date',
        'release_date': 'release_date',
        'title': 'title',
        '-title': '-title',
    }
    movies = movies.order_by(SORT_OPTIONS.get(sort_by, '-release_date'))

    genres = Genre.objects.all()
    languages = Language.objects.all()

    return render(request, 'movies/search.html', {
        'movies': movies,
        'query': query,
        'genres': genres,
        'languages': languages,
        'selected_genre': genre_id,
        'selected_language': language_id,
        'min_rating': min_rating,
        'sort_by': sort_by,
    })


# ──────────────────────────────────────────────
# TASK 2: SEAT RESERVATION
# ──────────────────────────────────────────────

@login_required
def seat_selection(request, schedule_id):
    schedule = get_object_or_404(ShowSchedule, pk=schedule_id)
    theater = schedule.theater

    # Clean up expired reservations
    SeatReservation.objects.filter(expires_at__lte=timezone.now()).delete()

    # Build seat map
    rows = theater.rows
    seats_per_row = theater.seats_per_row
    booked_seats = set(
        b.seat_numbers for b in schedule.bookings.filter(payment_status='success')
        if b.seat_numbers
    )
    # Flatten seat numbers
    booked_set = set()
    for s in booked_seats:
        for seat in s.split(','):
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
    for r in range(rows):
        row = []
        for s in range(1, seats_per_row + 1):
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

        # Release my old reservations
        SeatReservation.objects.filter(user=request.user, schedule=schedule).delete()

        # Reserve new seats atomically
        try:
            with transaction.atomic():
                for seat_id in selected_seats:
                    # Check not already booked/reserved
                    if seat_id in booked_set or (seat_id in reserved_set and seat_id not in my_reserved):
                        messages.error(request, f"Seat {seat_id} is no longer available. Please try again.")
                        return redirect('seat_selection', schedule_id=schedule_id)
                    SeatReservation.objects.create(
                        schedule=schedule, user=request.user, seat_number=seat_id
                    )
        except Exception:
            messages.error(request, "Could not reserve seats. Please try again.")
            return redirect('seat_selection', schedule_id=schedule_id)

        # Create pending booking
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
    """AJAX endpoint to refresh seat availability."""
    schedule_id = request.POST.get('schedule_id')
    schedule = get_object_or_404(ShowSchedule, pk=schedule_id)
    SeatReservation.objects.filter(expires_at__lte=timezone.now()).delete()

    booked_seats = set()
    for b in schedule.bookings.filter(payment_status='success'):
        for seat in b.seat_numbers.split(','):
            booked_seats.add(seat.strip())

    reserved_seats = set(
        sr.seat_number for sr in schedule.seat_reservations.filter(expires_at__gt=timezone.now())
    )
    return JsonResponse({'booked': list(booked_seats), 'reserved': list(reserved_seats)})


# ──────────────────────────────────────────────
# TASK 3: PAYMENT
# ──────────────────────────────────────────────

@login_required
def payment_form(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    if booking.payment_status == 'success':
        return redirect('booking_confirmation', booking_id=booking.id)

    if request.method == 'POST':
        card_number = request.POST.get('card_number', '').replace(' ', '')
        card_name = request.POST.get('card_name', '')
        expiry = request.POST.get('expiry', '')
        cvv = request.POST.get('cvv', '')

        # Simulate payment processing
        # Card ending with 0000 = failed, otherwise success
        if card_number.endswith('0000'):
            payment_status = 'failed'
            booking.payment_status = 'failed'
            booking.save()
            messages.error(request, "Payment failed! Please try a different card.")
            return redirect('payment_form', booking_id=booking.id)
        else:
            # Success
            with transaction.atomic():
                transaction_id = f"TXN{uuid.uuid4().hex[:12].upper()}"
                Payment.objects.create(
                    booking=booking,
                    transaction_id=transaction_id,
                    amount=booking.total_price,
                    status='success',
                    payment_method='Card'
                )
                booking.payment_status = 'success'
                booking.save()
                # Release seat reservations (they are now fully booked)
                SeatReservation.objects.filter(user=request.user, schedule=booking.schedule).delete()

            messages.success(request, f"Payment successful! Transaction ID: {transaction_id}")
            return redirect('booking_confirmation', booking_id=booking.id)

    return render(request, 'movies/payment_form.html', {'booking': booking})


@login_required
def booking_confirmation(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    return render(request, 'movies/booking_confirmation.html', {'booking': booking})


@login_required
def my_bookings(request):
    bookings = request.user.bookings.select_related('schedule__movie', 'schedule__theater').order_by('-booking_time')
    return render(request, 'movies/my_bookings.html', {'bookings': bookings})


# ──────────────────────────────────────────────
# TASK 4: ADMIN ANALYTICS DASHBOARD
# ──────────────────────────────────────────────

def is_admin(user):
    return user.is_staff

@user_passes_test(is_admin, login_url='/admin/login/')
def admin_dashboard(request):
    from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
    import json as json_lib

    # Overview stats
    total_revenue = Payment.objects.filter(status='success').aggregate(total=Sum('amount'))['total'] or 0
    total_bookings = Booking.objects.filter(payment_status='success').count()
    total_movies = Movie.objects.count()
    total_users = Booking.objects.values('user').distinct().count()

    # Revenue by day (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_revenue = Payment.objects.filter(
        status='success', created_at__gte=thirty_days_ago
    ).annotate(day=TruncDay('created_at')).values('day').annotate(total=Sum('amount')).order_by('day')

    daily_labels = [entry['day'].strftime('%b %d') for entry in daily_revenue]
    daily_data = [float(entry['total']) for entry in daily_revenue]

    # Top 5 movies by bookings
    top_movies = Movie.objects.annotate(
        booking_count=Count('schedules__bookings', filter=Q(schedules__bookings__payment_status='success'))
    ).order_by('-booking_count')[:5]

    # Bookings per theater
    theater_stats = Theater.objects.annotate(
        booking_count=Count('schedules__bookings', filter=Q(schedules__bookings__payment_status='success')),
        revenue=Sum('schedules__bookings__total_price', filter=Q(schedules__bookings__payment_status='success'))
    ).order_by('-booking_count')

    # Recent bookings
    recent_bookings = Booking.objects.filter(payment_status='success').select_related(
        'user', 'schedule__movie', 'schedule__theater'
    ).order_by('-booking_time')[:10]

    # Monthly revenue
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
        'daily_labels': json_lib.dumps(daily_labels),
        'daily_data': json_lib.dumps(daily_data),
        'month_labels': json_lib.dumps(month_labels),
        'month_data': json_lib.dumps(month_data),
        'top_movies': top_movies,
        'theater_stats': theater_stats,
        'recent_bookings': recent_bookings,
    })
