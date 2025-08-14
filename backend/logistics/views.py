from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.db.models import Count, Avg, Sum, Q
from django.db import transaction
from .models import Driver, Route, Order, SimulationResult
from .serializers import (
    UserSerializer, LoginSerializer, DriverSerializer, RouteSerializer,
    OrderSerializer, SimulationInputSerializer, SimulationResultSerializer,
    DashboardStatsSerializer, ChartDataSerializer
)
from .utils import SimulationEngine, load_initial_data
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Authentication Views
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    """Login endpoint that returns JWT tokens"""
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    """Logout endpoint that blacklists the refresh token"""
    try:
        refresh_token = request.data["refresh_token"]
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({"message": "Successfully logged out"})
    except Exception as e:
        return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

# Driver CRUD Views
class DriverListCreateView(generics.ListCreateAPIView):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Driver.objects.all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('name')

class DriverRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer
    permission_classes = [permissions.IsAuthenticated]

# Route CRUD Views
class RouteListCreateView(generics.ListCreateAPIView):
    queryset = Route.objects.all()
    serializer_class = RouteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Route.objects.all()
        traffic_level = self.request.query_params.get('traffic_level', None)
        if traffic_level:
            queryset = queryset.filter(traffic_level=traffic_level)
        return queryset.order_by('route_id')

class RouteRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Route.objects.all()
    serializer_class = RouteSerializer
    permission_classes = [permissions.IsAuthenticated]

# Order CRUD Views
class OrderListCreateView(generics.ListCreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Order.objects.select_related('route', 'assigned_driver').all()
        
        # Filter by route
        route_id = self.request.query_params.get('route_id', None)
        if route_id:
            queryset = queryset.filter(route__route_id=route_id)
        
        # Filter by assigned driver
        driver_id = self.request.query_params.get('driver_id', None)
        if driver_id:
            queryset = queryset.filter(assigned_driver_id=driver_id)
        
        # Filter by late status
        is_late = self.request.query_params.get('is_late', None)
        if is_late is not None:
            if is_late.lower() == 'true':
                # This requires custom filtering since is_late is a property
                late_orders = []
                for order in queryset:
                    if order.is_late:
                        late_orders.append(order.id)
                queryset = queryset.filter(id__in=late_orders)
            elif is_late.lower() == 'false':
                late_orders = []
                for order in queryset:
                    if order.is_late:
                        late_orders.append(order.id)
                queryset = queryset.exclude(id__in=late_orders)
        
        return queryset.order_by('order_id')

class OrderRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

# Simulation Views
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def run_simulation(request):
    """Run delivery simulation with custom company rules"""
    serializer = SimulationInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            # Get validated data
            inputs = serializer.validated_data
            
            # Generate unique simulation ID
            simulation_id = str(uuid.uuid4())[:8]
            
            # Initialize simulation engine
            engine = SimulationEngine()
            
            # Run simulation
            results = engine.run_simulation(
                available_drivers=inputs['available_drivers'],
                route_start_time=inputs['route_start_time'],
                max_hours_per_day=inputs['max_hours_per_day']
            )
            
            # Create simulation result record
            simulation_result = SimulationResult.objects.create(
                simulation_id=simulation_id,
                user=request.user,
                available_drivers=inputs['available_drivers'],
                route_start_time=inputs['route_start_time'],
                max_hours_per_day=inputs['max_hours_per_day'],
                total_profit=Decimal(str(results['total_profit'])),
                efficiency_score=Decimal(str(results['efficiency_score'])),
                on_time_deliveries=results['on_time_deliveries'],
                late_deliveries=results['late_deliveries']
            )
            
            # Set complex fields
            simulation_result.set_fuel_cost_breakdown(results['fuel_cost_breakdown'])
            simulation_result.set_driver_assignments(results['driver_assignments'])
            simulation_result.save()
            
            # Return results
            result_serializer = SimulationResultSerializer(simulation_result)
            return Response({
                'simulation_id': simulation_id,
                'results': result_serializer.data,
                'message': 'Simulation completed successfully'
            })
            
    except Exception as e:
        logger.error(f"Simulation error: {str(e)}")
        return Response(
            {'error': 'Simulation failed', 'details': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def simulation_history(request):
    """Get simulation history for the current user"""
    simulations = SimulationResult.objects.filter(user=request.user).order_by('-created_at')
    
    # Pagination
    page_size = int(request.query_params.get('page_size', 10))
    page = int(request.query_params.get('page', 1))
    start = (page - 1) * page_size
    end = start + page_size
    
    paginated_simulations = simulations[start:end]
    serializer = SimulationResultSerializer(paginated_simulations, many=True)
    
    return Response({
        'results': serializer.data,
        'total': simulations.count(),
        'page': page,
        'page_size': page_size,
        'total_pages': (simulations.count() + page_size - 1) // page_size
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def simulation_detail(request, simulation_id):
    """Get detailed results for a specific simulation"""
    try:
        simulation = SimulationResult.objects.get(simulation_id=simulation_id, user=request.user)
        serializer = SimulationResultSerializer(simulation)
        return Response(serializer.data)
    except SimulationResult.DoesNotExist:
        return Response(
            {'error': 'Simulation not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

# Dashboard Views
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    """Get dashboard statistics and KPIs"""
    try:
        # Basic counts
        total_drivers = Driver.objects.count()
        total_routes = Route.objects.count()
        total_orders = Order.objects.count()
        total_simulations = SimulationResult.objects.count()
        
        # Recent simulations
        recent_simulations = SimulationResult.objects.order_by('-created_at')[:5]
        
        # Calculate KPIs
        simulations = SimulationResult.objects.all()
        average_efficiency = simulations.aggregate(avg_eff=Avg('efficiency_score'))['avg_eff'] or 0
        total_revenue = simulations.aggregate(total_rev=Sum('total_profit'))['total_rev'] or 0
        
        # High traffic routes count
        high_traffic_routes = Route.objects.filter(traffic_level='High').count()
        
        # Overworked drivers (worked more than 8 hours yesterday)
        overworked_drivers = 0
        for driver in Driver.objects.all():
            if driver.is_overworked:
                overworked_drivers += 1
        
        stats_data = {
            'total_drivers': total_drivers,
            'total_routes': total_routes,
            'total_orders': total_orders,
            'total_simulations': total_simulations,
            'recent_simulations': recent_simulations,
            'average_efficiency': round(average_efficiency, 2),
            'total_revenue': round(total_revenue, 2),
            'high_traffic_routes': high_traffic_routes,
            'overworked_drivers': overworked_drivers,
        }
        
        serializer = DashboardStatsSerializer(stats_data)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        return Response(
            {'error': 'Failed to fetch dashboard stats'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def chart_data(request):
    """Get data for dashboard charts"""
    try:
        # On-time vs Late deliveries
        total_on_time = SimulationResult.objects.aggregate(
            total=Sum('on_time_deliveries')
        )['total'] or 0
        
        total_late = SimulationResult.objects.aggregate(
            total=Sum('late_deliveries')
        )['total'] or 0
        
        on_time_vs_late = {
            'on_time': total_on_time,
            'late': total_late
        }
        
        # Fuel cost by traffic level
        fuel_cost_by_traffic = {
            'Low': 0,
            'Medium': 0,
            'High': 0
        }
        
        # Calculate fuel costs from routes
        for route in Route.objects.all():
            order_count = route.orders.count()
            total_fuel_cost = route.total_fuel_cost * order_count
            fuel_cost_by_traffic[route.traffic_level] += total_fuel_cost
        
        # Profit trend (last 7 days)
        profit_trend = []
        efficiency_trend = []
        
        for i in range(7):
            date = datetime.now().date() - timedelta(days=i)
            day_simulations = SimulationResult.objects.filter(created_at__date=date)
            
            daily_profit = day_simulations.aggregate(
                total=Sum('total_profit')
            )['total'] or 0
            
            daily_efficiency = day_simulations.aggregate(
                avg=Avg('efficiency_score')
            )['avg'] or 0
            
            profit_trend.insert(0, {
                'date': date.strftime('%Y-%m-%d'),
                'profit': float(daily_profit)
            })
            
            efficiency_trend.insert(0, {
                'date': date.strftime('%Y-%m-%d'),
                'efficiency': float(daily_efficiency)
            })
        
        chart_data = {
            'on_time_vs_late': on_time_vs_late,
            'fuel_cost_by_traffic': fuel_cost_by_traffic,
            'profit_trend': profit_trend,
            'efficiency_trend': efficiency_trend
        }
        
        serializer = ChartDataSerializer(chart_data)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Chart data error: {str(e)}")
        return Response(
            {'error': 'Failed to fetch chart data'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Utility Views
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def load_initial_data_view(request):
    """Load initial data from CSV files"""
    try:
        result = load_initial_data()
        return Response(result)
    except Exception as e:
        logger.error(f"Data loading error: {str(e)}")
        return Response(
            {'error': 'Failed to load initial data', 'details': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def health_check(request):
    """Health check endpoint"""
    return Response({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': 'connected',
        'user': request.user.username
    })

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_info(request):
    """API information endpoint"""
    return Response({
        'name': 'GreenCart Logistics API',
        'version': '1.0.0',
        'description': 'Delivery simulation and KPI dashboard API',
        'endpoints': {
            'auth': {
                'login': '/api/auth/login/',
                'logout': '/api/auth/logout/',
            },
            'drivers': '/api/drivers/',
            'routes': '/api/routes/',
            'orders': '/api/orders/',
            'simulation': {
                'run': '/api/simulation/run/',
                'history': '/api/simulation/history/',
                'detail': '/api/simulation/{simulation_id}/',
            },
            'dashboard': {
                'stats': '/api/dashboard/stats/',
                'charts': '/api/dashboard/charts/',
            },
            'utility': {
                'load_data': '/api/load-initial-data/',
                'health': '/api/health/',
                'info': '/api/info/',
            }
        }
    })