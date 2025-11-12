from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('centers/', views.centers, name='centers'),
    path('education/', views.education, name='education'),
    path('credits/', views.credits, name='credits'),
    path('centers/nearby/', views.centers_nearby_api, name='centers_nearby_api'),
    path('eco-tips/', views.eco_tips, name='eco_tips'),
    path('quiz/', views.quiz, name='quiz'),
    path('decision/', views.decision, name='decision'),
    path('reuse/', views.reuse_marketplace, name='reuse_marketplace'),
    path('value/', views.value_estimator, name='value_estimator'),
    path('hazard/', views.hazard_visualiser, name='hazard_visualiser'),
    path('pickup/', views.pickup_scheduling, name='pickup_scheduling'),
    path('challenges/', views.green_challenges, name='green_challenges'),
    
    # Authentication URLs
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
]


