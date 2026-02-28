from django.urls import path
from django.contrib.auth import views as auth_views

from .views import auth, users, lokals, agreements, meters, transactions, rules, reports

urlpatterns = [
    # Authentication URLs
    path('login/', auth.user_login, name='login'),
    path('logout/', auth.user_logout, name='logout'),
    path('password_change/', auth.password_change, name='password_change'),
    path('password_change/done/', auth.password_change_done, name='password_change_done'),

    # Password reset URLs (dla zapomnianych haseł)
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # Main list views
    path('', auth.home, name='home'),
    path('users/', users.user_list, name='user_list'),
    path('lokale/', lokals.lokal_list, name='lokal_list'),
    path('agreements/', agreements.agreement_list, name='agreement_list'),

    path('meter_readings/', meters.meter_readings_view, name='meter_readings'),
    path('meter-consumption-report/', meters.meter_consumption_report, name='meter-consumption-report'),
    path('upload_csv/', transactions.upload_csv, name='upload_csv'),
    path('reprocess_transactions/', transactions.reprocess_transactions, name='reprocess_transactions'),
    path('categorize_transactions/', transactions.categorize_transactions, name='categorize_transactions'),
    path('save_categorization/', transactions.save_categorization, name='save_categorization'),
    path('clear_transactions/', transactions.clear_all_transactions, name='clear_all_transactions'),
    path('fixed-costs/', reports.fixed_costs_view, name='fixed_costs_list'),
    path('water-cost-summary/', reports.water_cost_summary_view, name='water_cost_summary'),
    path('water-cost-table/', reports.water_cost_table, name='water_cost_table'),

    # Rule Management
    path('rules/', rules.rule_list, name='rule_list'),
    path('rules/<int:pk>/edit/', rules.edit_rule, name='rule_edit'),
    path('rules/<int:pk>/delete/', rules.delete_rule, name='rule_delete'),

    # User URLs
    path('user/add/', users.create_user, name='user-add'),
    path('user/<int:pk>/edit/', users.edit_user, name='user-edit'),
    path('user/<int:pk>/delete/', users.delete_user, name='user-delete'),

    # Lokal URLs
    path('lokal/add/', lokals.create_lokal, name='lokal-add'),
    path('lokal/<int:pk>/', lokals.lokal_detail, name='lokal-detail'),
    path('lokal/<int:pk>/bimonthly-report/', reports.bimonthly_report_view, name='lokal-bimonthly-report'),
    path('lokal/<int:pk>/edit/', lokals.edit_lokal, name='lokal-edit'),
    path('lokal/<int:pk>/delete/', lokals.delete_lokal, name='lokal-delete'),

    # Agreement URLs
    path('agreement/add/', agreements.create_agreement, name='agreement-add'),
    path('agreement/<int:pk>/edit/', agreements.edit_agreement, name='agreement-edit'),
    path('agreement/<int:pk>/delete/', agreements.delete_agreement, name='agreement-delete'),
    path('agreement/<int:pk>/terminate/', agreements.terminate_agreement, name='terminate_agreement'),
    path('agreement/<int:pk>/settlement/', agreements.settlement, name='settlement'),
    path('agreement/<int:pk>/annual_report/', agreements.annual_agreement_report, name='annual_agreement_report'),
    path('agreement/<int:pk>/annual_report/pdf/', reports.annual_report_pdf, name='annual_report_pdf'),

    # Meter Reading URLs
    path('meter/<int:meter_id>/add_reading/', meters.add_meter_reading, name='add_meter_reading'),

    # Transaction URLs
    path('transaction/<int:pk>/edit/', transactions.edit_transaction, name='transaction-edit'),
    path('transaction/<int:pk>/delete/', transactions.delete_transaction, name='transaction-delete'),
]
