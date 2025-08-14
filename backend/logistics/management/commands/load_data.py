import csv
import os
from django.conf import settings
from .models import Driver, Route, Order
import logging
import json
from decimal import Decimal

logger = logging.getLogger(__name__)

class SimulationEngine:
    """
    Custom simulation engine that implements GreenCart's proprietary company rules
    """
    
    def __init__(self):
        self.drivers = []
        self.routes = []
        self.orders = []
    
    def load_data(self):
        """Load current data from database"""
        self.drivers = list(Driver.objects.all())
        self.routes = list(Route.objects.all())
        self.orders = list(Order.objects.select_related('route').all())
        
        # Create route lookup for faster access
        self.route_map = {route.route_id: route for route in self.routes}
    
    def run_simulation(self, available_drivers, route_start_time, max_hours_per_day):
        """
        Run the simulation with company-specific rules
        
        Company Rules:
        1. Late Delivery Penalty: If delivery time > (base route time + 10 minutes), apply ₹50 penalty
        2. Driver Fatigue Rule: If driver works >8 hours in a day, delivery speed decreases by 30% next day
        3. High-Value Bonus: If order value > ₹1000 AND delivered on time → add 10% bonus
        4. Fuel Cost Calculation: Base ₹5/km + ₹2/km surcharge for high traffic
        5. Overall Profit: Sum of (order value + bonus – penalties – fuel cost)
        6. Efficiency Score: (OnTime Deliveries / Total Deliveries) × 100
        """
        
        self.load_data()
        
        # Initialize results
        results = {
            'total_profit': 0,
            'efficiency_score': 0,
            'on_time_deliveries': 0,
            'late_deliveries': 0,
            'fuel_cost_breakdown': {'Low': 0, 'Medium': 0, 'High': 0},
            'driver_assignments': []
        }
        
        # Get available drivers (first N drivers based on input)
        selected_drivers = self.drivers[:available_drivers]
        
        if not selected_drivers:
            raise ValueError("No drivers available")
        
        if not self.orders:
            raise ValueError("No orders to process")
        
        # Assign orders to drivers
        orders_per_driver = len(self.orders) // len(selected_drivers)
        extra_orders = len(self.orders) % len(selected_drivers)
        
        driver_assignments = []
        order_index = 0
        
        total_penalties = 0
        total_bonuses = 0
        total_fuel_cost = 0
        
        for i, driver in enumerate(selected_drivers):
            # Calculate orders for this driver
            orders_for_driver = orders_per_driver + (1 if i < extra_orders else 0)
            assigned_orders = self.orders[order_index:order_index + orders_for_driver]
            order_index += orders_for_driver
            
            # Calculate estimated hours (simplified: 30 minutes per order)
            estimated_hours = min(len(assigned_orders) * 0.5, max_hours_per_day)
            
            driver_assignment = {
                'driver_name': driver.name,
                'driver_id': driver.id,
                'assigned_orders': len(assigned_orders),
                'estimated_hours': round(estimated_hours, 2),
                'is_overworked': driver.is_overworked
            }
            
            # Process each order for this driver
            for order in assigned_orders:
                route = self.route_map.get(order.route_id)
                if not route:
                    continue
                
                # Apply company rules
                order_profit, penalties, bonuses, fuel_cost = self._apply_company_rules(
                    order, route, driver
                )
                
                results['total_profit'] += order_profit
                total_penalties += penalties
                total_bonuses += bonuses
                total_fuel_cost += fuel_cost
                
                # Update fuel cost breakdown
                results['fuel_cost_breakdown'][route.traffic_level] += fuel_cost
                
                # Check if delivery is on time
                if order.is_late:
                    results['late_deliveries'] += 1
                else:
                    results['on_time_deliveries'] += 1
            
            driver_assignments.append(driver_assignment)
        
        # Calculate efficiency score
        total_deliveries = results['on_time_deliveries'] + results['late_deliveries']
        if total_deliveries > 0:
            results['efficiency_score'] = round(
                (results['on_time_deliveries'] / total_deliveries) * 100, 2
            )
        
        # Round values
        results['total_profit'] = round(results['total_profit'], 2)
        results['driver_assignments'] = driver_assignments
        
        # Add summary statistics
        results['summary'] = {
            'total_orders_processed': len(self.orders),
            'drivers_used': len(selected_drivers),
            'total_penalties': round(total_penalties, 2),
            'total_bonuses': round(total_bonuses, 2),
            'total_fuel_cost': round(total_fuel_cost, 2),
            'average_orders_per_driver': round(len(self.orders) / len(selected_drivers), 2)
        }
        
        return results
    
    def _apply_company_rules(self, order, route, driver):
        """Apply company-specific rules to calculate order profit"""
        
        order_value = order.value_rs
        penalties = 0
        bonuses = 0
        
        # Rule 1: Late delivery penalty
        if order.is_late:
            penalties += 50
        
        # Rule 2: Driver fatigue (affects delivery time, but we'll apply as efficiency reduction)
        efficiency_factor = 0.7 if driver.is_overworked else 1.0
        
        # Rule 3: High-value bonus
        if order.is_high_value and not order.is_late:
            bonuses += order_value * 0.1
        
        # Rule 4: Fuel cost calculation
        base_fuel_cost = route.distance_km * 5  # ₹5/km
        fuel_surcharge = route.distance_km * 2 if route.traffic_level == 'High' else 0
        total_fuel_cost = (base_fuel_cost + fuel_surcharge) * efficiency_factor
        
        # Rule 5: Overall profit calculation
        order_profit = order_value + bonuses - penalties - total_fuel_cost
        
        return order_profit, penalties, bonuses, total_fuel_cost

def load_initial_data():
    """Load initial data from CSV files"""
    
    data_dir = os.path.join(settings.BASE_DIR, 'data')
    results = {
        'drivers_loaded': 0,
        'routes_loaded': 0,
        'orders_loaded': 0,
        'errors': []
    }
    
    try:
        # Load drivers
        drivers_file = os.path.join(data_dir, 'drivers.csv')
        if os.path.exists(drivers_file):
            Driver.objects.all().delete()  # Clear existing data
            
            with open(drivers_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                drivers_to_create = []
                
                for row in reader:
                    try:
                        # Parse past week hours
                        past_week_hours = []
                        if row.get('past_week_hours'):
                            hours_str = row['past_week_hours'].split('|')
                            past_week_hours = [int(h) for h in hours_str if h.strip()]
                        
                        driver = Driver(
                            name=row['name'].strip(),
                            shift_hours=int(row['shift_hours']),
                            past_week_hours=json.dumps(past_week_hours)
                        )
                        drivers_to_create.append(driver)
                        
                    except (ValueError, KeyError) as e:
                        results['errors'].append(f"Error processing driver row {row}: {str(e)}")
                
                Driver.objects.bulk_create(drivers_to_create)
                results['drivers_loaded'] = len(drivers_to_create)
                logger.info(f"Loaded {len(drivers_to_create)} drivers")
        
        # Load routes
        routes_file = os.path.join(data_dir, 'routes.csv')
        if os.path.exists(routes_file):
            Route.objects.all().delete()  # Clear existing data
            
            with open(routes_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                routes_to_create = []
                
                for row in reader:
                    try:
                        route = Route(
                            route_id=int(row['route_id']),
                            distance_km=int(row['distance_km']),
                            traffic_level=row['traffic_level'].strip(),
                            base_time_min=int(row['base_time_min'])
                        )
                        routes_to_create.append(route)
                        
                    except (ValueError, KeyError) as e:
                        results['errors'].append(f"Error processing route row {row}: {str(e)}")
                
                Route.objects.bulk_create(routes_to_create)
                results['routes_loaded'] = len(routes_to_create)
                logger.info(f"Loaded {len(routes_to_create)} routes")
        
        # Load orders
        orders_file = os.path.join(data_dir, 'orders.csv')
        if os.path.exists(orders_file):
            Order.objects.all().delete()  # Clear existing data
            
            # Create route lookup for foreign key assignment
            routes = {r.route_id: r for r in Route.objects.all()}
            
            with open(orders_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                orders_to_create = []
                
                for row in reader:
                    try:
                        route_id = int(row['route_id'])
                        route = routes.get(route_id)
                        
                        if route:
                            order = Order(
                                order_id=int(row['order_id']),
                                value_rs=int(row['value_rs']),
                                route=route,
                                delivery_time=row['delivery_time'].strip()
                            )
                            orders_to_create.append(order)
                        else:
                            results['errors'].append(f"Route {route_id} not found for order {row['order_id']}")
                            
                    except (ValueError, KeyError) as e:
                        results['errors'].append(f"Error processing order row {row}: {str(e)}")
                
                Order.objects.bulk_create(orders_to_create)
                results['orders_loaded'] = len(orders_to_create)
                logger.info(f"Loaded {len(orders_to_create)} orders")
        
        # Create default admin user if it doesn't exist
        from django.contrib.auth.models import User
        if not User.objects.filter(username='admin').exists():
            User.objects.create_user(
                username='admin',
                password='admin123',
                email='admin@greencart.com',
                first_name='Admin',
                last_name='User',
                is_staff=True,
                is_superuser=True
            )
            logger.info("Created default admin user")
            results['admin_created'] = True
        
        results['success'] = True
        results['message'] = "Data loaded successfully"
        
    except Exception as e:
        logger.error(f"Error loading initial data: {str(e)}")
        results['success'] = False
        results['message'] = f"Failed to load data: {str(e)}"
        results['errors'].append(str(e))
    
    return results

def validate_csv_format(file_path, expected_headers):
    """Validate CSV file format and headers"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            headers = next(reader)
            
            # Check if all expected headers are present
            missing_headers = set(expected_headers) - set(headers)
            extra_headers = set(headers) - set(expected_headers)
            
            return {
                'valid': len(missing_headers) == 0,
                'missing_headers': list(missing_headers),
                'extra_headers': list(extra_headers),
                'headers': headers
            }
    except Exception as e:
        return {
            'valid': False,
            'error': str(e),
            'headers': []
        }

def export_data_to_csv():
    """Export current data to CSV files for backup"""
    try:
        data_dir = os.path.join(settings.BASE_DIR, 'exports')
        os.makedirs(data_dir, exist_ok=True)
        
        results = {'files_created': []}
        
        # Export drivers
        drivers_file = os.path.join(data_dir, f'drivers_export_{int(time.time())}.csv')
        with open(drivers_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['name', 'shift_hours', 'past_week_hours'])
            
            for driver in Driver.objects.all():
                past_hours = '|'.join(map(str, driver.get_past_week_hours()))
                writer.writerow([driver.name, driver.shift_hours, past_hours])
        
        results['files_created'].append(drivers_file)
        
        # Export routes
        routes_file = os.path.join(data_dir, f'routes_export_{int(time.time())}.csv')
        with open(routes_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['route_id', 'distance_km', 'traffic_level', 'base_time_min'])
            
            for route in Route.objects.all():
                writer.writerow([
                    route.route_id, route.distance_km, 
                    route.traffic_level, route.base_time_min
                ])
        
        results['files_created'].append(routes_file)
        
        # Export orders
        orders_file = os.path.join(data_dir, f'orders_export_{int(time.time())}.csv')
        with open(orders_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['order_id', 'value_rs', 'route_id', 'delivery_time'])
            
            for order in Order.objects.select_related('route').all():
                writer.writerow([
                    order.order_id, order.value_rs, 
                    order.route.route_id, order.delivery_time
                ])
        
        results['files_created'].append(orders_file)
        results['success'] = True
        results['message'] = f"Exported {len(results['files_created'])} files"
        
        return results
        
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        return {'success': False, 'error': str(e)}

# Add time import
import time