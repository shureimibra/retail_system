# Project Workflow, Logic, and Architecture Documentation

## Retail Purchase Constraint Management System (RPCMS)

Welcome to the technical documentation of the **Retail Purchase Constraint Management System (RPCMS)**. This document serves as a comprehensive reference guide for system reviews, explaining the design patterns, codebase structure, data models, business logic workflows, event handling, and configuration specifications.

---

## 1. System Overview

RPCMS is a retail decision-support and sales recovery platform. When customers visit a retail store (or digital storefront) and are unable to complete a purchase due to a specific bottleneck (e.g., product out-of-stock, size/color unavailable, price mismatch, or authenticity concern), this system captures the event as a **Blocked Purchase Intent**. 

Once the constraint is resolved (for example, the product variation is restocked), the system automatically triggers recovery workflows:
1. It updates the status of matching intents to **Resolved**.
2. It generates and sends a notification (SMS or WhatsApp) informing the customer.
3. It updates the intent's status to **Customer Notified**.
4. It aggregates these events to calculate lost vs. recovered revenue and provides automatic restock recommendations based on accumulated demand.

---

## 2. Architectural Design Patterns

The project is built on Django 5.2 (Python) and follows a **decoupled Modular Monolith** architecture with clean separation of concerns:

```
┌────────────────────────────────────────────────────────┐
│                      Presentation                      │
│        (Django HTML Templates / DRF REST APIs)          │
└───────────────────────────┬────────────────────────────┘
                            │ (Calls queries & mutations)
                            ▼
┌────────────────────────────────────────────────────────┐
│                     Business Logic                     │
│      (Service Layer: Mutations/State-Changing)         │
│      (Selector Layer: Reads/Aggregations/Queries)      │
└───────────────────────────┬────────────────────────────┘
                            │ (Reads/Writes database)
                            ▼
┌────────────────────────────────────────────────────────┐
│                        Data Layer                      │
│       (Django Models / SQLite or PostgreSQL DB)        │
└────────────────────────────────────────────────────────┘
```

### 2.1 The Service Layer Pattern
Mutations, API integration calls, SMS dispatching, and state-changing actions are isolated from views and models. They live in `services/` (or app-specific `services.py` modules), containing clean Python functions. This makes the system easily unit-testable and decouples logic from the request-response cycle.

### 2.2 The Selector Pattern
Data retrieval, complex SQL/ORM queries, filtering, and metric aggregations are isolated into selector functions (e.g., `selectors.py` modules). Views and APIs delegate data fetching to these selectors instead of performing raw ORM filtering.

### 2.3 Event-Driven Programming via Django Signals
The coupling between stock updates (inventory) and customer communications (notifications) is achieved asynchronously through Django Signals. When a product variation's stock is saved, signals are fired, decoupling the inventory module from the notification engine.

---

## 3. Directory Layout & Code Map

The project is divided into distinct Django applications (local apps) alongside central utility modules. Here is the structure of the workspace:

```
retail_system/
│
├── core/                         # Project settings, routing, and WSGI/ASGI servers
│   ├── settings.py               # Core configurations (Apps, Middleware, DB, Twilio)
│   ├── urls.py                   # Central routing map (HTML views and DRF REST routes)
│   └── api_views.py              # Health checks
│
├── accounts/                     # User management & Authentication
│   ├── models.py                 # Custom AbstractUser model (phone number, staff members)
│   └── urls.py & views.py        # Sign-in, sign-up, sign-out views
│
├── products/                     # Product catalog and variation management
│   ├── models.py                 # Category, Product, ProductVariation models
│   ├── signals.py                # Hook listeners on stock and variation changes
│   ├── services.py               # Mutations: Category, Product, and Stock updates
│   └── selectors.py              # Query utilities for products
│
├── customers/                    # Customer directory and customer profiles
│   ├── models.py                 # Customer (First Name, Last Name, Phone, Email)
│   └── services.py               # Mutations: Create and retrieve customers
│
├── intents/                      # Core business model: Blocked Purchase Intents
│   ├── models.py                 # BlockedPurchaseIntent model & choices
│   ├── signals.py                # Automates stock monitoring and notification triggers
│   ├── services.py               # Mutations: Intent creation and status updates
│   └── selectors.py              # Query utilities for intents
│
├── notifications/                # Outbound SMS/WhatsApp dispatch logs & webhook replies
│   ├── models.py                 # NotificationLog and InboundSMSLog models
│   ├── services.py               # SMSService (Twilio Integration / Simulation fallbacks)
│   └── signals.py                # Updates intent state to 'Customer Notified' on SMS dispatch
│
├── analytics/                    # Data aggregation engine and KPI tracking
│   ├── selectors.py              # KPI calculation, constraint distribution, monthly trends
│   └── api_views.py              # REST endpoints for dashboard charts and metrics
│
├── reports/                      # Reporting module
│   ├── views.py                  # Trigger views for CSV and PDF downloads
│   └── services.py               # Document builder (ReportLab PDF / csv.writer)
│
├── dashboard/                    # Core Web UI dashboard views and landing page
│   ├── views.py                  # Home view (loads selectors and packages data for templates)
│   └── templates/                # HTML layout & Chart.js scripts
│
├── services/                     # Central Business Logic Central Services Directory
│   ├── customer_service.py       # Customer creation and verification logic
│   ├── intent_service.py         # Handles Blocked Intents, creations, and stock resolutions
│   ├── inventory_service.py      # Stock quantity updates and validation triggers
│   └── notification_service.py   # Africa's Talking API simulation and logging
│
├── templates/                    # Global base HTML layouts & styling configurations
├── static/                       # Custom JS scripts and CSS stylesheets (Tailwind)
├── manage.py                     # Django management CLI wrapper
├── populate_data.py              # Seed script populated with categories, products, and intents
├── reply_sms.py                  # Inbound Webhook: TwiML response listener using Flask
├── send_sms.py                   # Ad-hoc command-line SMS sending tool via Twilio
└── requirements.txt              # Project dependencies
```

---

## 4. Database Schema & Data Models

### 4.1 `accounts.User`
Extends Django's `AbstractUser` to authenticate store personnel and record who logged a constraint.
* `phone_number` (`CharField(max_length=15)`, nullable): Personal phone number.
* `is_staff_member` (`BooleanField`, default `False`): Identifies sales agents.

### 4.2 `products.Category`
Groups related items in the catalog.
* `name` (`CharField(max_length=100)`): E.g., Footwear, Apparel.
* `description` (`TextField`, blank): Details about the category.

### 4.3 `products.Product`
The base item within the inventory catalog.
* `category` (`ForeignKey` to `Category`, on delete CASCADE): Category classification.
* `name` (`CharField(max_length=200)`): Product name.
* `description` (`TextField`): Product details.
* `base_price` (`DecimalField(max_digits=10, decimal_places=2)`): Base price used to calculate estimated lost value.
* `created_at` / `updated_at` (`DateTimeField`): Automatic auditing timestamps.

### 4.4 `products.ProductVariation`
Specifies exact physical SKUs based on physical attributes.
* `product` (`ForeignKey` to `Product`, on delete CASCADE): Parent product details.
* `size` (`CharField(max_length=50)`, nullable): E.g., "42", "M".
* `color` (`CharField(max_length=50)`, nullable): E.g., "Black", "Red".
* `stock_quantity` (`PositiveIntegerField`, default `0`): Current inventory.
* `sku` (`CharField(max_length=100)`, unique): Stock Keeping Unit string.

### 4.5 `customers.Customer`
Customer directory record.
* `first_name` (`CharField(max_length=100)`)
* `last_name` (`CharField(max_length=100)`)
* `phone_number` (`CharField(max_length=20)`, unique): Required for notification dispatching (must follow E.164 format: `+CountryCode...`).
* `email` (`EmailField`, nullable)

### 4.6 `intents.BlockedPurchaseIntent`
Stores details about the blocked sales transaction.
* `customer` (`ForeignKey` to `Customer`, on delete CASCADE)
* `product` (`ForeignKey` to `Product`, on delete CASCADE)
* `variation` (`ForeignKey` to `ProductVariation`, on delete SET_NULL, nullable): Specific variant desired (blank if a general product issue).
* `constraint_type` (`CharField`): Choices are:
  - `Size unavailable`
  - `Color unavailable`
  - `Out of stock`
  - `Price too high`
  - `Authenticity concern`
  - `Budget mismatch`
* `status` (`CharField`, default `Pending`): Choices are:
  - `Pending`: Capturing initial constraint.
  - `Monitoring`: Logged and watching inventory levels.
  - `Customer Notified`: Alert sent to customer.
  - `Resolved`: Constraint solved, waiting/processing notification.
  - `Recovered`: Customer completed purchase.
  - `Closed`: Customer lost or intent archived.
* `requested_quantity` (`PositiveIntegerField`, default `1`)
* `estimated_value` (`DecimalField`, nullable): Revenue value of transaction. If blank, auto-calculated as `base_price * requested_quantity`.
* `notes` (`TextField`, blank): Qualitative details captured by staff.
* `recorded_by` (`ForeignKey` to `User`, on delete SET_NULL, nullable): Agent who logged the intent.

### 4.7 `notifications.NotificationLog`
Maintains auditing records of outbound alert dispatches.
* `intent` (`ForeignKey` to `BlockedPurchaseIntent`, on delete CASCADE)
* `message` (`TextField`): Message text.
* `sent_at` (`DateTimeField`, auto_now_add)
* `status` (`CharField`, default `Sent`): `Sent` or `Failed`.

### 4.8 `notifications.InboundSMSLog`
Maintains records of customer responses.
* `from_number` / `to_number` (`CharField(max_length=30)`)
* `body` (`TextField`)
* `received_at` (`DateTimeField`, auto_now_add)
* `customer` (`ForeignKey` to `Customer`, on delete SET_NULL, nullable)

---

## 5. Core Workflows & Business Logic

### Workflow 1: Capturing Blocked Purchase Intent
```mermaid
sequenceDiagram
    autonumber
    actor Staff as Store Agent
    participant Views as Intents View / API
    participant IS as Intent Service
    participant DB as SQLite / Postgres DB

    Staff->>Views: Fill Intent Form (Customer, Product, Variation, Constraint, Qty)
    Views->>IS: create_blocked_purchase_intent()
    alt estimated_value is blank
        IS->>IS: Calculate estimated_value = product.base_price * requested_quantity
    end
    IS->>DB: Save BlockedPurchaseIntent record (Status = 'Pending')
    DB-->>Staff: Return Success, Display on Dashboard
```

### Workflow 2: Inventory Restocking & Auto-Resolution
This workflow runs when stock becomes available. It automatically identifies matching constraints and updates their state:
```mermaid
sequenceDiagram
    autonumber
    actor Admin as Inventory/Admin
    participant Model as ProductVariation Model
    participant Sig as products.signals
    participant InvSvc as services.inventory_service
    participant IntSvc as services.intent_service
    participant DB as Database

    Admin->>Model: Update stock_quantity > 0 & Save()
    Model->>Sig: Fire on_variation_update signal
    Sig->>InvSvc: handle_stock_update(variation)
    InvSvc->>IntSvc: resolve_blocked_intents_for_variation(variation)
    IntSvc->>DB: Filter Pending/Monitoring intents matching variation
    loop For each matching intent
        IntSvc->>DB: Set status = 'Resolved' & Save()
        IntSvc->>IntSvc: Call send_resolution_notification(intent)
    end
```

### Workflow 3: Communication & Alert Dispatch (Outbound)
Once resolved, the communication block prepares and fires messages.
1. **Duplicate Check**: Query `NotificationLog` to ensure no successful (`status='Sent'`) notification exists for this intent ID. If one exists, the request is silently ignored to prevent spamming.
2. **Contact Format Validation**: Inspect customer phone number. If it is null or does not begin with `+` (E.164 verification), log a warning, write a `Failed` entry in the `NotificationLog`, and return.
3. **Payload Formatting**: Compose customized message:
   `"Hello [Customer Name], the [Product Name] ([Size]/[Color]) you requested is now available."`
4. **API Dispatching (Twilio WhatsApp vs. Africa's Talking)**:
   - **Twilio WhatsApp (Production)**: If TWILIO keys are configured in environment variables, the system converts phone numbers to Twilio's WhatsApp identifiers (e.g., `whatsapp:+254...`). It instantiates the Twilio Client and sends the WhatsApp message.
   - **Simulation Mode (Fallback)**: If Twilio credentials are not set, it writes a log entry: `[Simulation Mode] Sending SMS to +...` and marks it as `Sent`.
5. **Acknowledge Notification**: Write a row to `NotificationLog` with `status='Sent'` (or `Failed` on API error).
6. **Intent Status Transition**: Upon successful dispatch, Django signals (`notifications/signals.py`) detect the saved `NotificationLog` with status `Sent` and automatically transition the intent's status to `Customer Notified`.

### Workflow 4: Callback Webhooks (Inbound Messages)
To handle incoming communication (e.g., a customer replying "Thank you, hold it for me"), a dedicated webhook is exposed.
1. A customer sends an SMS or WhatsApp to the Twilio number.
2. Twilio parses the incoming message and triggers an HTTP POST request to the application's `/sms` webhook route (defined in `reply_sms.py`).
3. The Flask app parses form inputs: `From` (customer number), `To` (recipient number), and `Body` (message content).
4. It prints the transaction logs to the console and generates a TwiML response:
   ```xml
   <Response>
       <Message>Thank you for contacting Retail RMS. Your response has been logged.</Message>
   </Response>
   ```
5. The response is returned to the user, and details can be logged to `InboundSMSLog` in the backend.

### Workflow 5: Analytics, KPIs, and Restocking Recommendations
The dashboard aggregates operational data to guide stock replenishment:
* **KPI Metrics**:
  - *Total Blocked Purchases*: Total count of logged intents.
  - *Active Intents*: Count of intents in `Pending` or `Monitoring` state.
  - *Recovered Sales*: Count of intents in `Resolved`, `Customer Notified`, or `Recovered` state.
  - *Estimated Lost Revenue*: Sum of `estimated_value` of all unrecovered/unresolved intents (excludes `Resolved`, `Customer Notified`, and `Recovered`).
  - *Recovered Revenue*: Sum of `estimated_value` of all resolved/recovered intents.
* **Monthly Trends**: Groups intents by month using `TruncMonth`, aggregating counts and recovery rates.
* **Top Blocked Products**: Identifies the top 5 products by blocked intent count.
* **Restock Recommendation Engine**: Groups active (`Pending`/`Monitoring`) intents by `variation_id` and filters variations where the count is $\ge 4$ (configurable threshold). For each matching variant, it lists the demand count, current stock, and recommends restocks.

### Workflow 6: Document Export Reporting
Allows store admins to download data for review:
* **CSV Export (`ExportCSVReportView`)**: Fetches filtered intent records, creates a CSV stream, writes column headers, and stream-downloads row data containing customer info, product variations, values, and status.
* **PDF Export (`ExportPDFReportView`)**: Utilizes `ReportLab` to construct clean tabular documents. Applies page templates, sets up document margins, creates a structured grid showing intent statistics, and applies custom color tags (e.g., `#1E3A8A` for table styling).

---

## 6. Django Signals: Decoupling and Event Flows

Signals act as the glue between inventory modifications and notification logic. 

```
┌──────────────────────────────────────────────┐
│           ProductVariation.save()            │
└──────────────────────┬───────────────────────┘
                       │
                       ▼ (Triggers Django post_save / save override)
┌──────────────────────────────────────────────┐
│         products.signals                     │
│         (on_variation_update.send)           │
└──────────────────────┬───────────────────────┘
                       │
                       ▼ (Calls)
┌──────────────────────────────────────────────┐
│         services.inventory_service           │
│         (handle_stock_update)                │
└──────────────────────┬───────────────────────┘
                       │
                       ▼ (If stock > 0, calls)
┌──────────────────────────────────────────────┐
│         services.intent_service              │
│         (resolve_blocked_intents)            │
└──────────────────────┬───────────────────────┘
                       │
                       ▼ (Updates intent.status = 'Resolved')
┌──────────────────────────────────────────────┐
│         intents.signals                      │
│         (send_notification_on_intent_resolve) │
└──────────────────────┬───────────────────────┘
                       │
                       ▼ (Triggers)
┌──────────────────────────────────────────────┐
│         notifications.services (SMSService)  │
│         (send_restock_notification)          │
└──────────────────────┬───────────────────────┘
                       │
                       ▼ (Saves NotificationLog with status='Sent')
┌──────────────────────────────────────────────┐
│         notifications.signals                │
│         (update_intent_status_on_notification)│
└──────────────────────┬───────────────────────┘
                       │
                       ▼ (Updates status)
┌──────────────────────────────────────────────┐
│    intent.status = 'Customer Notified'       │
└──────────────────────────────────────────────┘
```

There are two parallel signaling structures:
1. **Custom Model Signals**:
   - `on_product_stock_update` and `on_variation_update` defined in `products/signals.py` and manually invoked inside the model `save()` methods.
   - Handlers call `services/inventory_service.py` -> `handle_stock_update()` to resolve intents.
2. **Standard Django Django Model Signals (`post_save`)**:
   - `check_inventory_for_intents` (listens to `post_save` of `ProductVariation` in `intents/signals.py`). When variations are updated with stock, it automatically updates matching intents' status to `'Resolved'`.
   - `send_notification_on_intent_resolve` (listens to `post_save` of `BlockedPurchaseIntent` in `intents/signals.py`). When an intent status is updated to `'Resolved'`, it triggers `SMSService.send_restock_notification()`.
   - `update_intent_status_on_notification` (listens to `post_save` of `NotificationLog` in `notifications/signals.py`). When a notification log is saved with status `Sent`, it updates the intent's status to `'Customer Notified'`.

---

## 7. Web UI & REST API Specifications

The system is managed through both a web-based dashboard interface and REST API endpoints.

### 7.1 Web Interface Views
* **Dashboard Home (`/dashboard/`)**: Features KPI summary cards, interactive Chart.js widgets (constraint distributions, trend lines, product bars), restock recommendations, and a quick-record intent modal.
* **Product Catalog (`/products/`)**: Add, edit, and view items and variations.
* **Customer Directory (`/customers/`)**: Customer profiling and records list.
* **Blocked Intents Log (`/intents/`)**: Log, update, and monitor constraint cases.
* **Reporting Hub (`/reports/`)**: Generate CSV and PDF exports.

### 7.2 API Router Maps
Registered under `/api/` using Django REST Framework's `DefaultRouter`:
* `/api/categories/`: Category list and CRUD.
* `/api/products/`: Catalog items list, including nested serializer representations of variations.
* `/api/variations/`: Product variations list, filterable by `product` ID.
* `/api/customers/`: Customer profiles list.
* `/api/intents/`: Blocked purchase intents list. Perform-create hooks invoke `create_blocked_purchase_intent()`.
* `/api/dashboard/`: Read-only KPIs and recommendations.
* `/api/analytics/`: Detailed aggregations, charts datasets, and trend outputs.
* `/api/reports/`: Filtered reports list.
* `/api/health/`: Return `{"status": "healthy"}` for deployment checks.

---

## 8. Configuration, Environment, and Setup

### 8.1 Dependencies (`requirements.txt`)
* `django`: Core framework.
* `djangorestframework`: API framework.
* `django-filter`: Query filters for API views.
* `reportlab`: PDF document engine.
* `twilio`: WhatsApp API client.
* `python-dotenv`: Environment variables reader.
* `whitenoise`: Static file server.
* `dj-database-url`: Parse production connection strings.
* `gunicorn`: WSGI HTTP Server.

### 8.2 Environment Variables (`.env`)
Create a `.env` file in the root directory to store credentials:
```bash
# Security & Debug
SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Twilio Credentials (Optional - Falls back to simulation if blank)
TWILIO_ACCOUNT_SID=ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+17656271910

# Database (Optional - Defaults to local sqlite)
DATABASE_URL=postgres://user:password@host:port/database_name
```

### 8.3 CLI Commands
1. **Initialize and Install**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Execute Migrations**:
   ```bash
   python manage.py migrate
   ```
3. **Seed Database with Sample Data**:
   ```bash
   python manage.py shell
   # Or directly execute the script
   python populate_data.py
   ```
4. **Run Development Server**:
   ```bash
   python manage.py runserver
   ```
5. **Run Incoming Webhook Listener**:
   ```bash
   python reply_sms.py
   ```
