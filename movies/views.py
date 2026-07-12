from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Avg, Count
from .models import Movie, Review, Booking
from .forms import ReviewForm
from django.utils import timezone

def home(request):
    # Trending: movies with most reviews
    trending_movies = Movie.objects.annotate(num_reviews=Count('reviews')).order_by('-num_reviews')[:6]
    # Recently released
    recent_movies = Movie.objects.order_by('-release_date')[:6]
    
    return render(request, 'movies/home.html', {
        'trending_movies': trending_movies,
        'recent_movies': recent_movies,
    })

def movie_detail(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    reviews = movie.reviews.all().order_by('-created_at')
    
    # Similar movies logic (by genre)
    similar_movies = Movie.objects.filter(genres__in=movie.genres.all()).exclude(pk=movie.pk).distinct()[:4]
    
    # Review form for logged in users
    review_form = None
    has_watched = False
    user_review = None
    
    if request.user.is_authenticated:
        # Check if user has watched it (booking start time in past)
        has_watched = Booking.objects.filter(
            user=request.user,
            schedule__movie=movie,
            schedule__start_time__lte=timezone.now()
        ).exists()
        
        # Check if user already reviewed
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
    })
