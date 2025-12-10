from django.urls import path
from . import views

urlpatterns = [
    path('', views.user_list, name='user_list'),
    path('add/', views.create_user, name='add_user'),
    path('agreement/add/', views.create_agreement, name='add_agreement'),
]
