from django.http import HttpResponse
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('api/recommended/', views.recommended_content_api, name='recommended_content_api'),
    path('explore/', views.explore, name='explore'),
    path('event_detail/<int:id>/', views.event_detail, name='event_detail'),
    path('feedback/', views.feedback, name='feedback'),
    path('save-feedback/', views.save_feedback, name='save_feedback'),
    path('chat-ai/', views.chat_with_ai, name='chat_with_ai'),
    path('culture_performance/', views.culture_performance, name='culture_performance'),
    path('business_performance/', views.business_performance, name='business_performance'),
    path('track/', views.track_activity, name='track_activity'),
    path('content/<int:id>/', views.event_detail, name='event_detail'),
    path('event/<int:id>/register/', views.register_event, name='register_event'),
    path('success/', views.success_page, name='success_page'),
 
    # Admin login / logout
    path('admin-login/', views.admin_login, name='admin_login'),
    path('admin-logout/', views.admin_logout_view, name='admin_logout'),
 
    # Admin pages (protected)
    path('admin-home/', views.admin_home, name='admin_home'),
    path('admin-explore/', views.explore_admin, name='admin_explore'),
    path('admin-explore/add/', views.admin_add_event, name='admin_add_event'),
    path('admin-explore/edit/<int:id>/', views.admin_edit_event, name='admin_edit_event'),
    path('admin-explore/delete/<int:id>/', views.admin_delete_event, name='admin_delete_event'),
    path('admin-feedback/', views.feedback_admin, name='admin_feedback'),
]
