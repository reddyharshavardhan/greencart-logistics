import os
import django
import csv
from logistics.models import Driver, Route, Order

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greencart.settings')
django.setup()

def seed_data(file_path, model, parse_row):
    with open(file_path, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            model.objects.create(**parse_row(row))

def parse_driver(row):
    return {
        'name': row['name'],
        'shift_hours': int(row['shift_hours']),
        'past_week_hours': list(map(int, row['past_week_hours'].split('|'))),
        'is_fatigued': False
    }

def parse_route(row):
    return {
        'route_id': int(row['route_id']),
        'distance_km': int(row['distance_km']),
        'traffic_level': row['traffic_level'],
        'base_time_min': int(row['base_time_min'])
    }

def parse_order(row):
    return {
        'order_id': int(row['order_id']),
        'value_rs': int(row['value_rs']),
        'route_id': int(row['route_id']),
        'delivery_time_min': int(row['delivery_time'].split(':')[0]) * 60 + int(row['delivery_time'].split(':')[1])
    }

if __name__ == "__main__":
    seed_data('data/drivers.csv', Driver, parse_driver)
    seed_data('data/routes.csv', Route, parse_route)
    seed_data('data/orders.csv', Order, parse_order)
    print("Seeding complete!")