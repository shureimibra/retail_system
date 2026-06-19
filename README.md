# Retail Purchase Constraint Management System

A retail decision-support and sales recovery platform that helps retailers capture failed purchase opportunities, monitor unresolved purchase constraints, and automatically re-engage customers once constraints are resolved.

## Technology Stack

* **Backend**: Django 5.2, Python
* **Database**: SQLite (local) / PostgreSQL (production via dj-database-url)
* **Frontend**: HTML5, Tailwind CSS, Chart.js
* **Deployment**: Render-ready (Procfile, build.sh, whitenoise configured)

## Modules

1. **Accounts**: Custom user model and authentication.
2. **Products**: Catalog management with product variations.
3. **Customers**: Customer records.
4. **Intents**: The core module capturing "Blocked Purchase Intents" (e.g. Size Unavailable, Price Too High).
5. **Dashboard**: Analytics and KPI tracking using Chart.js.
6. **Notifications**: Signal-based inventory engine simulating SMS sending when constraints are resolved.

## Setup Instructions

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Run migrations:
   ```bash
   python manage.py migrate
   ```

3. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

4. Run the development server:
   ```bash
   python manage.py runserver
   ```

## Architecture

This project follows a Modular Monolith architecture, separating business logic into decoupled apps, using Django Signals to trigger automated workflows (Inventory Engine -> Notifications), and providing a clean, responsive UI with Tailwind CSS.
