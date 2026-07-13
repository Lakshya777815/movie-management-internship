from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Review, Movie, Genre, Language, CastMember

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'text']
        widgets = {
            'rating': forms.NumberInput(attrs={'min': 1, 'max': 5}),
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write your review here...'}),
        }

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text='Required. Input a valid email address.')

    class Meta:
        model = User
        fields = ['username', 'email']

class MovieUploadForm(forms.ModelForm):
    poster_image = forms.ImageField(required=True, label="Movie Poster Image")
    
    class Meta:
        model = Movie
        fields = [
            'title', 'description', 'release_date', 'duration_minutes',
            'age_certification', 'trailer_url', 'ticket_price',
            'genres', 'languages', 'cast'
        ]
        widgets = {
            'release_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }
