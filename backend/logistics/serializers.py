from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import Driver, Route, Order, SimulationResult, UserProfile
import json

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError('Invalid credentials')
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled')
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError('Must provide username and password')

class DriverSerializer(serializers.ModelSerializer):
    past_week_hours_list = serializers.SerializerMethodField()
    average_weekly_hours = serializers.ReadOnlyField()
    is_overworked = serializers.ReadOnlyField()

    class Meta:
        model = Driver
        fields = ['id', 'name', 'shift_hours', 'past_week_hours', 'past_week_hours_list', 
                 'average_weekly_hours', 'is_overworked', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_past_week_hours_list(self, obj):
        return obj.get_past_week_hours()

    def validate_past_week_hours(self, value):
        """Validate that past_week_hours is a valid JSON array"""
        if value:
            try:
                hours_list = json.loads(value)
                if not isinstance(hours_list, list):
                    raise serializers.ValidationError("past_week_hours must be a JSON array")
                if len(hours_list) > 7:
                    raise serializers.ValidationError("past_week_hours cannot have more than 7 entries")
                for hour in hours_list:
                    if not isinstance(hour, (int, float)) or hour < 0 or hour > 24:
                        raise serializers.ValidationError("Each hour must be between 0 and 24")
                return value
            except json.JSONDecodeError:
                raise serializers.ValidationError("past_week_hours must be valid JSON")
        return value

class RouteSerializer(serializers.ModelSerializer):
    fuel_cost_per_km = serializers.ReadOnlyField()
    total_fuel_cost = serializers.ReadOnlyField()
    orders_count = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = ['id', 'route_id', 'distance_km', 'traffic_level', 'base_time_min',
                 'fuel_cost_per_km', 'total_fuel_cost', 'orders_count', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_orders_count(self, obj):
        return obj.orders.count()

    def validate_route_id(self, value):
        """Validate that route_id is unique on create or update"""
        if self.instance:
            # Update case: exclude current instance
            if Route.objects.exclude(id=self.instance.id).filter(route_id=value).exists():
                raise serializers.ValidationError("Route ID already exists")
        else:
            # Create case
            if Route.objects.filter(route_id=value).exists():
                raise serializers.ValidationError("Route ID already exists")
        return value

class OrderSerializer(serializers.ModelSerializer):
    route_details = RouteSerializer(source='route', read_only=True)
    driver_name = serializers.CharField(source='assigned_driver.name', read_only=True)
    delivery_time_minutes = serializers.ReadOnlyField()
    is_late = serializers.ReadOnlyField()
    is_high_value = serializers.ReadOnlyField()
    penalty_amount = serializers.ReadOnlyField()
    bonus_amount = serializers.ReadOnlyField()
    net_profit = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = ['id', 'order_id', 'value_rs', 'route', 'route_details', 'delivery_time',
                 'assigned_driver', 'driver_name', 'delivery_time_minutes', 'is_late',
                 'is_high_value', 'penalty_amount', 'bonus_amount', 'net_profit',
                 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate_order_id(self, value):
        """Validate that order_id is unique on create or update"""
        if self.instance:
            # Update case: exclude current instance
            if Order.objects.exclude(id=self.instance.id).filter(order_id=value).exists():
                raise serializers.ValidationError("Order ID already exists")
        else:
            # Create case
            if Order.objects.filter(order_id=value).exists():
                raise serializers.ValidationError("Order ID already exists")
        return value

    def validate_delivery_time(self, value):
        """Validate delivery time format"""
        try:
            hours, minutes = map(int, value.split(':'))
            if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
                raise ValueError
            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, AttributeError):
            raise serializers.ValidationError("Delivery time must be in HH:MM format (24-hour)")

    def validate_route(self, value):
        """Validate that route exists"""
        if not value:
            raise serializers.ValidationError("Route is required")
        return value

class SimulationInputSerializer(serializers.Serializer):
    available_drivers = serializers.IntegerField(min_value=1)
    route_start_time = serializers.CharField(max_length=5)
    max_hours_per_day = serializers.IntegerField(min_value=1, max_value=24)

    def validate_route_start_time(self, value):
        """Validate start time format"""
        try:
            hours, minutes = map(int, value.split(':'))
            if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
                raise ValueError
            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, AttributeError):
            raise serializers.ValidationError("Start time must be in HH:MM format (24-hour)")

    def validate_available_drivers(self, value):
        """Validate that there are enough drivers available"""
        total_drivers = Driver.objects.count()
        if value > total_drivers:
            raise serializers.ValidationError(f"Only {total_drivers} drivers available in system")
        return value

class SimulationResultSerializer(serializers.ModelSerializer):
    fuel_cost_breakdown_dict = serializers.SerializerMethodField()
    driver_assignments_list = serializers.SerializerMethodField()
    total_deliveries = serializers.ReadOnlyField()
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = SimulationResult
        fields = ['id', 'simulation_id', 'user', 'user_name', 'available_drivers',
                 'route_start_time', 'max_hours_per_day', 'total_profit',
                 'efficiency_score', 'on_time_deliveries', 'late_deliveries',
                 'fuel_cost_breakdown', 'fuel_cost_breakdown_dict',
                 'driver_assignments', 'driver_assignments_list',
                 'total_deliveries', 'created_at']
        read_only_fields = ['created_at']

    def get_fuel_cost_breakdown_dict(self, obj):
        return obj.get_fuel_cost_breakdown()

    def get_driver_assignments_list(self, obj):
        return obj.get_driver_assignments()

class DashboardStatsSerializer(serializers.Serializer):
    """Serializer for dashboard statistics"""
    total_drivers = serializers.IntegerField()
    total_routes = serializers.IntegerField()
    total_orders = serializers.IntegerField()
    total_simulations = serializers.IntegerField()
    recent_simulations = SimulationResultSerializer(many=True)
    
    # KPI data
    average_efficiency = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    high_traffic_routes = serializers.IntegerField()
    overworked_drivers = serializers.IntegerField()

class ChartDataSerializer(serializers.Serializer):
    """Serializer for chart data"""
    on_time_vs_late = serializers.DictField()
    fuel_cost_by_traffic = serializers.DictField()
    profit_trend = serializers.ListField()
    efficiency_trend = serializers.ListField()