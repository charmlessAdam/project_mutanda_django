#!/bin/bash

# Django Deployment Script for Lightsail
# Run this script on your Lightsail instance after uploading the project

echo "Starting Django deployment on Lightsail..."

# Navigate to project directory
cd /opt/bitnami/apache2/htdocs/django_project

# Install dependencies
echo "Installing Python dependencies..."
sudo pip3 install -r requirements.txt

# Run database migrations
echo "Running database migrations..."
python3 manage.py migrate

# Collect static files
echo "Collecting static files..."
python3 manage.py collectstatic --noinput

# Set proper permissions
echo "Setting file permissions..."
sudo chown -R bitnami:bitnami /opt/bitnami/apache2/htdocs/django_project
sudo chmod -R 755 /opt/bitnami/apache2/htdocs/django_project

# Restart Apache
echo "Restarting Apache server..."
sudo systemctl restart apache2

# Check Apache status
echo "Checking Apache status..."
sudo systemctl status apache2

echo "Deployment completed!"
echo "Your Django app should be accessible at your Lightsail instance IP address."
echo ""
echo "Test your API endpoints:"
echo "- http://YOUR-IP/api/"
echo "- http://YOUR-IP/admin/"
echo "- http://YOUR-IP/api/medicine/medicines/"