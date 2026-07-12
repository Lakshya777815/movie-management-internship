from django.contrib import admin
from .models import Genre, Language, CastMember, Theater, Movie, MoviePoster, ShowSchedule, Booking, Review, ReviewReport

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(CastMember)
class CastMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'role')
    list_filter = ('role',)

@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'capacity')

class MoviePosterInline(admin.TabularInline):
    model = MoviePoster
    extra = 1

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'release_date', 'duration_minutes', 'age_certification', 'average_rating')
    list_filter = ('age_certification', 'genres', 'languages')
    search_fields = ('title', 'description')
    filter_horizontal = ('genres', 'languages', 'cast')
    inlines = [MoviePosterInline]

@admin.register(ShowSchedule)
class ShowScheduleAdmin(admin.ModelAdmin):
    list_display = ('movie', 'theater', 'start_time', 'end_time')
    list_filter = ('theater', 'start_time')
    search_fields = ('movie__title',)

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('user', 'schedule', 'seats_booked', 'booking_time', 'is_watched')
    list_filter = ('booking_time',)
    search_fields = ('user__username', 'schedule__movie__title')

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('movie', 'user', 'rating', 'created_at', 'is_edited', 'verified_viewer')
    list_filter = ('rating', 'created_at', 'is_edited')
    search_fields = ('movie__title', 'user__username', 'text')

@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = ('review', 'reporter', 'status', 'reported_at')
    list_filter = ('status', 'reported_at')
    search_fields = ('reporter__username', 'review__text', 'reason')
    readonly_fields = ('review', 'reporter', 'reason', 'reported_at')
