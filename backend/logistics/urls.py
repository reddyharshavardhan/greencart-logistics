from django.urls import path
from . import views

urlpatterns = [
    # Authentication endpoints
    path('auth/login/', views.login_view, name='login'),
    path('auth/logout/', views.logout_view, name='logout'),
    
    # Driver CRUD endpoints
    path('drivers/', views.DriverListCreateView.as_view(), name='driver-list-create'),
    path('drivers/<int:pk>/', views.DriverRetrieveUpdateDestroyView.as_view(), name='driver-detail'),
    
    # Route CRUD endpoints
    path('routes/', views.RouteListCreateView.as_view(), name='route-list-create'),
    path('routes/<int:pk>/', views.RouteRetrieveUpdateDestroyView.as_view(), name='route-detail'),
    
    # Order CRUD endpoints
    path('orders/', views.OrderListCreateView.as_view(), name='order-list-create'),
    path('orders/<int:pk>/', views.OrderRetrieveUpdateDestroyView.as_view(), name='order-detail'),
    
    # Simulation endpoints
    path('simulation/run/', views.run_simulation, name='run-simulation'),
    path('simulation/history/', views.simulation_history, name='simulation-history'),
    path('simulation/<str:simulation_id>/', views.simulation_detail, name='simulation-detail'),
    
    # Dashboard endpoints
    path('dashboard/stats/', views.dashboard_stats, name='dashboard-stats'),
    path('dashboard/charts/', views.chart_data, name='chart-data'),
    
    # Utility endpoints
    path('load-initial-data/', views.load_initial_data_view, name='load-initial-data'),
    path('health/', views.health_check, name='health-check'),
    path('info/', views.api_info, name='api-info'),
]