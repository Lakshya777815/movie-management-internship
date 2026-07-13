from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('movie/<int:pk>/', views.movie_detail, name='movie_detail'),
    path('search/', views.search_movies, name='search_movies'),
    path('seats/<int:schedule_id>/', views.seat_selection, name='seat_selection'),
    path('seats/check/', views.check_seat_status, name='check_seat_status'),
    path('payment/<int:booking_id>/', views.payment_form, name='payment_form'),
    path('booking/<int:booking_id>/confirmation/', views.booking_confirmation, name='booking_confirmation'),
    path('booking/<int:booking_id>/download/', views.download_ticket, name='download_ticket'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # Auth Routes
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Upload Movie Route
    path('movie/upload/', views.upload_movie, name='upload_movie'),
]
