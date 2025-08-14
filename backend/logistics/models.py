from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import json

class Driver(models.Model):
    name = models.CharField(max_length=100)
    shift_hours = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    past_week_hours = models.TextField(help_text="JSON array of past 7 days work hours")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_past_week_hours(self):
        """Return past week hours as a list"""
        try:
            return json.loads(self.past_week_hours) if self.past_week_hours else []
        except json.JSONDecodeError:
            return []

    def set_past_week_hours(self, hours_list):
        """Set past week hours from a list"""
        self.past_week_hours = json.dumps(hours_list)

    @property
    def average_weekly_hours(self):
        hours = self.get_past_week_hours()
        return sum(hours) / len(hours) if hours else 0

    @property
    def is_overworked(self):
        """Check if driver worked more than 8 hours yesterday"""
        hours = self.get_past_week_hours()
        return hours[-1] > 8 if hours else False

class Route(models.Model):
    TRAFFIC_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]

    route_id = models.IntegerField(unique=True)
    distance_km = models.IntegerField(validators=[MinValueValidator(1)])
    traffic_level = models.CharField(max_length=10, choices=TRAFFIC_CHOICES)
    base_time_min = models.IntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Route {self.route_id} - {self.distance_km}km ({self.traffic_level})"

    @property
    def fuel_cost_per_km(self):
        """Calculate fuel cost per km based on traffic level"""
        base_cost = 5  # ₹5/km base cost
        if self.traffic_level == 'High':
            return base_cost + 2  # +₹2/km surcharge for high traffic
        return base_cost

    @property
    def total_fuel_cost(self):
        """Calculate total fuel cost for this route"""
        return self.distance_km * self.fuel_cost_per_km

class Order(models.Model):
    order_id = models.IntegerField(unique=True)
    value_rs = models.IntegerField(validators=[MinValueValidator(1)])
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='orders')
    delivery_time = models.CharField(max_length=5, help_text="Format: HH:MM")
    assigned_driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.order_id} - ₹{self.value_rs}"

    @property
    def delivery_time_minutes(self):
        """Convert delivery time to minutes"""
        try:
            hours, minutes = map(int, self.delivery_time.split(':'))
            return hours * 60 + minutes
        except (ValueError, AttributeError):
            return 0

    @property
    def is_late(self):
        """Check if delivery is late based on route base time + 10 minutes buffer"""
        if not self.route:
            return False
        allowed_time = self.route.base_time_min + 10
        return self.delivery_time_minutes > allowed_time

    @property
    def is_high_value(self):
        """Check if order value is greater than ₹1000"""
        return self.value_rs > 1000

    @property
    def penalty_amount(self):
        """Calculate penalty for late delivery"""
        return 50 if self.is_late else 0

    @property
    def bonus_amount(self):
        """Calculate bonus for high-value on-time delivery"""
        if self.is_high_value and not self.is_late:
            return self.value_rs * 0.1  # 10% bonus
        return 0

    @property
    def net_profit(self):
        """Calculate net profit for this order"""
        fuel_cost = self.route.total_fuel_cost if self.route else 0
        return self.value_rs + self.bonus_amount - self.penalty_amount - fuel_cost

class SimulationResult(models.Model):
    simulation_id = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Simulation inputs
    available_drivers = models.IntegerField(validators=[MinValueValidator(1)])
    route_start_time = models.CharField(max_length=5, help_text="Format: HH:MM")
    max_hours_per_day = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(24)])
    
    # Simulation results
    total_profit = models.DecimalField(max_digits=10, decimal_places=2)
    efficiency_score = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    on_time_deliveries = models.IntegerField(default=0)
    late_deliveries = models.IntegerField(default=0)
    fuel_cost_breakdown = models.TextField(help_text="JSON object with fuel costs by traffic level")
    driver_assignments = models.TextField(help_text="JSON array of driver assignments")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Simulation {self.simulation_id} - Profit: ₹{self.total_profit}"

    def get_fuel_cost_breakdown(self):
        """Return fuel cost breakdown as a dictionary"""
        try:
            return json.loads(self.fuel_cost_breakdown) if self.fuel_cost_breakdown else {}
        except json.JSONDecodeError:
            return {}

    def set_fuel_cost_breakdown(self, breakdown_dict):
        """Set fuel cost breakdown from a dictionary"""
        self.fuel_cost_breakdown = json.dumps(breakdown_dict)

    def get_driver_assignments(self):
        """Return driver assignments as a list"""
        try:
            return json.loads(self.driver_assignments) if self.driver_assignments else []
        except json.JSONDecodeError:
            return []

    def set_driver_assignments(self, assignments_list):
        """Set driver assignments from a list"""
        self.driver_assignments = json.dumps(assignments_list)

    @property
    def total_deliveries(self):
        """Calculate total deliveries"""
        return self.on_time_deliveries + self.late_deliveries

    class Meta:
        ordering = ['-created_at']

class UserProfile(models.Model):
    """Extended user profile for additional user information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=[('manager', 'Manager'), ('driver', 'Driver')])
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.role}"