from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import timedelta
from django.utils import timezone

class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name

class Language(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name

class CastMember(models.Model):
    ROLE_CHOICES = [('Actor', 'Actor'), ('Director', 'Director'), ('Producer', 'Producer')]
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='Actor')
    profile_image = models.ImageField(upload_to='cast/', null=True, blank=True)
    def __str__(self): return f"{self.name} ({self.role})"

class Theater(models.Model):
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=300)
    capacity = models.PositiveIntegerField()
    def __str__(self): return f"{self.name} - {self.location}"

class Movie(models.Model):
    CERTIFICATION_CHOICES = [('U', 'U'), ('UA', 'UA'), ('A', 'A'), ('S', 'S')]
    title = models.CharField(max_length=300)
    description = models.TextField()
    release_date = models.DateField()
    duration_minutes = models.PositiveIntegerField(help_text="Duration in minutes")
    age_certification = models.CharField(max_length=10, choices=CERTIFICATION_CHOICES)
    trailer_url = models.URLField(help_text="YouTube Trailer URL (or embed link)")
    genres = models.ManyToManyField(Genre, related_name='movies')
    languages = models.ManyToManyField(Language, related_name='movies')
    cast = models.ManyToManyField(CastMember, related_name='movies', blank=True)
    
    @property
    def average_rating(self):
        reviews = self.reviews.all()
        if reviews:
            return round(sum(r.rating for r in reviews) / len(reviews), 1)
        return 0.0

    def __str__(self): return self.title

class MoviePoster(models.Model):
    movie = models.ForeignKey(Movie, related_name='posters', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='movie_posters/')
    is_primary = models.BooleanField(default=False)
    
    def __str__(self): return f"Poster for {self.movie.title}"

class ShowSchedule(models.Model):
    movie = models.ForeignKey(Movie, related_name='schedules', on_delete=models.CASCADE)
    theater = models.ForeignKey(Theater, related_name='schedules', on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    
    @property
    def end_time(self):
        return self.start_time + timedelta(minutes=self.movie.duration_minutes)
        
    def __str__(self): return f"{self.movie.title} at {self.theater.name} ({self.start_time.strftime('%Y-%m-%d %H:%M')})"

class Booking(models.Model):
    user = models.ForeignKey(User, related_name='bookings', on_delete=models.CASCADE)
    schedule = models.ForeignKey(ShowSchedule, related_name='bookings', on_delete=models.CASCADE)
    seats_booked = models.PositiveIntegerField(default=1)
    booking_time = models.DateTimeField(auto_now_add=True)
    
    @property
    def is_watched(self):
        return timezone.now() >= self.schedule.start_time
        
    def __str__(self): return f"Booking {self.id} for {self.user.username} - {self.schedule.movie.title}"

class Review(models.Model):
    movie = models.ForeignKey(Movie, related_name='reviews', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='reviews', on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_edited = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('movie', 'user')

    @property
    def verified_viewer(self):
        return Booking.objects.filter(user=self.user, schedule__movie=self.movie, schedule__start_time__lte=timezone.now()).exists()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            orig = Review.objects.get(pk=self.pk)
            if orig.text != self.text:
                self.is_edited = True
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.rating} star review by {self.user.username} on {self.movie.title}"

class ReviewReport(models.Model):
    STATUS_CHOICES = [('Pending', 'Pending'), ('Reviewed', 'Reviewed'), ('Dismissed', 'Dismissed')]
    review = models.ForeignKey(Review, related_name='reports', on_delete=models.CASCADE)
    reporter = models.ForeignKey(User, related_name='reports_filed', on_delete=models.CASCADE)
    reason = models.TextField(help_text="Why is this review inappropriate?")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    reported_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Report by {self.reporter.username} on review ID {self.review.id}"
