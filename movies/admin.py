from django.contrib import admin
from .models import Genre, Language, CastMember, Theater, Movie, MoviePoster, ShowSchedule, Booking, Review, ReviewReport, SeatReservation, Payment

class MoviePosterInline(admin.TabularInline):
    model = MoviePoster
    extra = 1

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    inlines = [MoviePosterInline]
    list_display = ('title', 'release_date', 'age_certification', 'average_rating', 'ticket_price')
    list_filter = ('age_certification', 'genres', 'languages')
    search_fields = ('title', 'description')
    filter_horizontal = ('genres', 'languages', 'cast')

@admin.register(ShowSchedule)
class ShowScheduleAdmin(admin.ModelAdmin):
    list_display = ('movie', 'theater', 'start_time', 'available_seats_count')
    list_filter = ('theater', 'movie')
    search_fields = ('movie__title',)

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'schedule', 'seats_booked', 'seat_numbers', 'total_price', 'payment_status', 'booking_time')
    list_filter = ('payment_status',)
    readonly_fields = ('booking_time',)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'booking', 'amount', 'status', 'payment_method', 'created_at')
    list_filter = ('status', 'payment_method')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'movie', 'rating', 'is_edited', 'created_at')
    list_filter = ('rating',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = ('reporter', 'review', 'status', 'reported_at')
    list_filter = ('status',)
    readonly_fields = ('reported_at',)

@admin.register(SeatReservation)
class SeatReservationAdmin(admin.ModelAdmin):
    list_display = ('user', 'schedule', 'seat_number', 'reserved_at', 'expires_at', 'is_expired')
    readonly_fields = ('reserved_at',)

admin.site.register(Genre)
admin.site.register(Language)
admin.site.register(CastMember)
admin.site.register(Theater)
