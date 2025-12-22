from django.urls import path
from . import views

urlpatterns = [
    # Main list views
    path('', views.user_list, name='user_list'),
    path('lokale/', views.lokal_list, name='lokal_list'),
    path('agreements/', views.agreement_list, name='agreement_list'),
    path('meter_readings/', views.meter_readings_view, name='meter_readings'),
    path('upload_csv/', views.upload_csv, name='upload_csv'),
    path('categorize_transactions/', views.categorize_transactions, name='categorize_transactions'),
    path('save_categorization/', views.save_categorization, name='save_categorization'),
    path('clear_transactions/', views.clear_all_transactions, name='clear_all_transactions'),

    # Rule Management
    path('rules/', views.rule_list, name='rule_list'),
    path('rules/<int:pk>/edit/', views.edit_rule, name='rule_edit'),
    path('rules/<int:pk>/delete/', views.delete_rule, name='rule_delete'),

    # User URLs
    path('user/add/', views.create_user, name='user-add'),
    path('user/<int:pk>/edit/', views.edit_user, name='user-edit'),
    path('user/<int:pk>/delete/', views.delete_user, name='user-delete'),

    # Lokal URLs
    path('lokal/add/', views.create_lokal, name='lokal-add'),
    path('lokal/<int:pk>/', views.lokal_detail, name='lokal-detail'),
    path('lokal/<int:pk>/edit/', views.edit_lokal, name='lokal-edit'),
    path('lokal/<int:pk>/delete/', views.delete_lokal, name='lokal-delete'),

    # Agreement URLs
    path('agreement/add/', views.create_agreement, name='agreement-add'),
    path('agreement/<int:pk>/edit/', views.edit_agreement, name='agreement-edit'),
    path('agreement/<int:pk>/delete/', views.delete_agreement, name='agreement-delete'),

    # Meter Reading URLs
    path('meter/<int:meter_id>/add_reading/', views.add_meter_reading, name='add_meter_reading'),

    # Transaction URLs
    path('transaction/<int:pk>/edit/', views.edit_transaction, name='transaction_edit'),
]
