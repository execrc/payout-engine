#!/bin/bash

# Apply database environment migrations automatically
python manage.py migrate --noinput

# Seed database securely
python seed.py

# Start the Huey background processor globally
python manage.py run_huey &

# Bind and launch exactly the Gunicorn API service
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000
