from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('movie/<int:pk>/', views.movie_detail, name='movie_detail'),
    path('search/', views.search_movies, name='search_movies'),
    path('seats/<int:schedule_id>/', views.seat_selection, name='seat_selection'),
    path('seats/check/', views.check_seat_status, name='check_seat_status'),
    path('payment/<int:booking_id>/', views.payment_form, name='payment_form'),
    path('booking/<int:booking_id>/confirmation/', views.booking_confirmation, name='booking_confirmation'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
]
