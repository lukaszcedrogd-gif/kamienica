from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Authentication URLs
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('password_change/', views.password_change, name='password_change'),
    path('password_change/done/', views.password_change_done, name='password_change_done'),

    # Password reset URLs (dla zapomnianych haseł)
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # Main list views
    path('', views.home, name='home'),
    path('users/', views.user_list, name='user_list'),
    path('lokale/', views.lokal_list, name='lokal_list'),
    path('agreements/', views.agreement_list, name='agreement_list'),

    path('meter_readings/', views.meter_readings_view, name='meter_readings'),
    path('meter-consumption-report/', views.meter_consumption_report, name='meter-consumption-report'),
    path('upload_csv/', views.upload_csv, name='upload_csv'),
    path('reprocess_transactions/', views.reprocess_transactions, name='reprocess_transactions'),
    path('categorize_transactions/', views.categorize_transactions, name='categorize_transactions'),
    path('save_categorization/', views.save_categorization, name='save_categorization'),
    path('clear_transactions/', views.clear_all_transactions, name='clear_all_transactions'),
    path('fixed-costs/', views.fixed_costs_view, name='fixed_costs_list'),
    path('water-cost-summary/', views.water_cost_summary_view, name='water_cost_summary'),
    path('water-cost-table/', views.water_cost_table, name='water_cost_table'),

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
    path('lokal/<int:pk>/bimonthly-report/', views.bimonthly_report_view, name='lokal-bimonthly-report'),
    path('lokal/<int:pk>/edit/', views.edit_lokal, name='lokal-edit'),
    path('lokal/<int:pk>/delete/', views.delete_lokal, name='lokal-delete'),

    # Agreement URLs
    path('agreement/add/', views.create_agreement, name='agreement-add'),
    path('agreement/<int:pk>/edit/', views.edit_agreement, name='agreement-edit'),
    path('agreement/<int:pk>/delete/', views.delete_agreement, name='agreement-delete'),
    path('agreement/<int:pk>/terminate/', views.terminate_agreement, name='terminate_agreement'),
    path('agreement/<int:pk>/settlement/', views.settlement, name='settlement'),
    path('agreement/<int:pk>/annual_report/', views.annual_agreement_report, name='annual_agreement_report'),
    path('agreement/<int:pk>/annual_report/pdf/', views.annual_report_pdf, name='annual_report_pdf'),

    # Meter Reading URLs
    path('meter/<int:meter_id>/add_reading/', views.add_meter_reading, name='add_meter_reading'),

    # Transaction URLs
    path('transaction/<int:pk>/edit/', views.edit_transaction, name='transaction-edit'),
    path('transaction/<int:pk>/delete/', views.delete_transaction, name='transaction-delete'),
]
