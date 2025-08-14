#!/usr/bin/env bash
# Exit on error
set -o errexit

# Modify this line as needed for your package manager (pip, poetry, etc.)
pip install -r requirements.txt

# Convert static asset files
python manage.py collectstatic --no-input

# Apply any outstanding database migrations
python manage.py migrate

# Create superuser if it doesn't exist
python manage.py shell << EOF
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@greencart.com', 'admin123')
    print('Superuser created')
else:
    print('Superuser already exists')
EOF

# Load initial data
python manage.py shell << EOF
try:
    from logistics.utils import load_initial_data
    result = load_initial_data()
    print('Data loaded:', result)
except Exception as e:
    print('Data loading error:', str(e))
EOF