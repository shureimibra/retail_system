# Project Workflow, Logic, and Architecture Documentation

## Retail Purchase Constraint Management System (RPCMS)

> [!IMPORTANT]
> **Claude AI Handover Note**: A complete, comprehensive system audit, technical debt resolution plan, enterprise UI redesign specification, and upgrade roadmap to a next-generation Retail OS is available in [CLAUDE_AI_SYSTEM_HANDOVER.md](file:///c:/Users/Administrator/.gemini/antigravity-ide/scratch/retail_system/docs/CLAUDE_AI_SYSTEM_HANDOVER.md).


---

## 1. System Overview

RPCMS is a retail decision-support and sales recovery platform. When customers visit a retail store (or digital storefront) and are unable to complete a purchase due to a specific bottleneck (e.g., product out-of-stock, size/color unavailable, price mismatch, or budget mismatch), this system captures the event as a **Blocked Purchase Intent**.

To prevent application lockups and "signal storm" race conditions under production loads, RPCMS leverages an asynchronous message broker model. Once a constraint is resolved (for example, when a product variation is restocked), the system automatically schedules recovery workflows using **Celery and Redis**:
1. It updates the status of matching, non-expired intents to **Resolved**.
2. It offloads customer alerts to Celery background workers.
3. The background worker checks privacy compliance, formats the notification template (including opt-out instructions), and sends the alert.
4. It updates the intent's status to **Customer Notified** once the broker confirms dispatch.
5. It aggregates these events to calculate lost vs. recovered revenue and provides automatic restock recommendations.

---

## 2. Architectural Design Patterns

The project is built on Django 5.2 (Python) and follows a **decoupled Modular Monolith** architecture with clean separation of concerns, utilizing an asynchronous task broker:

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
└─────────────┬─────────────────────────────┬────────────┘
              │ (Reads/Writes database)     │ (Dispatches tasks)
              ▼                             ▼
┌───────────────────────────┐ ┌──────────────────────────┐
│        Data Layer         │ │    Message Broker (Redis)│
│  (Django Models / DB)     │ └─────────────┬────────────┘
└───────────────────────────┘               │ (Pulls tasks)
                                            ▼
                              ┌──────────────────────────┐
                              │  Celery Background Worker│
                              │  (Asynchronous Actions)  │
                              └──────────────────────────┘
```

### 2.1 The Service Layer Pattern
Mutations, API integration calls, SMS dispatching, and state-changing actions are isolated from views and models. They live in `services/` (or app-specific `services.py` modules), containing clean Python functions. This makes the system easily unit-testable and decouples logic from the request-response cycle.

### 2.2 The Selector Pattern
Data retrieval, complex SQL/ORM queries, filtering, and metric aggregations are isolated into selector functions (e.g., `selectors.py` modules). Views and APIs delegate data fetching to these selectors instead of performing raw ORM filtering.

### 2.3 Asynchronous Task Queue (Celery + Redis)
To avoid blocking the HTTP request-response cycle and eliminate synchronous database locks during bulk inventory updates, the system utilizes Celery with a Redis message broker. Any process that triggers notifications or external API communications dispatches a background task to the queue, ensuring the main application remains responsive.

---

## 3. Directory Layout & Code Map

The project is divided into distinct Django applications (local apps) alongside central utility modules. Note that Flask utilities have been collapsed, and the Twilio incoming SMS webhook is integrated natively within Django:

```
retail_system/
│
├── core/                         # Project settings, routing, Celery configuration
│   ├── settings.py               # Core configurations (Apps, Middleware, DB, Celery, Twilio)
│   ├── urls.py                   # Central routing map (HTML views and DRF REST routes)
│   ├── api_views.py              # Health checks
│   ├── celery.py                 # [NEW] Celery app definition and broker setup
│   └── __init__.py               # Imports celery_app on startup
│
├── accounts/                     # User management & Authentication
│   ├── models.py                 # Custom AbstractUser model (phone number, staff members)
│   └── urls.py & views.py        # Sign-in, sign-up, sign-out views
│
├── products/                     # Product catalog and variation management
│   ├── models.py                 # Category, Product, ProductVariation models
│   ├── services.py               # Mutations: Category, Product, and explicit Stock updates
│   └── selectors.py              # Query utilities for products
│
├── customers/                    # Customer directory and customer profiles
│   ├── models.py                 # Customer (First Name, Last Name, Phone, Email, Opt-in status)
│   └── services.py               # Mutations: Create and retrieve customers
│
├── intents/                      # Core business model: Blocked Purchase Intents
│   ├── models.py                 # BlockedPurchaseIntent model (choices, expiry date)
│   ├── services.py               # Mutations: Intent creation and status updates
│   └── selectors.py              # Query utilities for intents (excludes expired entries)
│
├── notifications/                # Webhook integration, notification tasks & auditing logs
│   ├── models.py                 # NotificationLog and InboundSMSLog models
│   ├── services.py               # SMSService (Twilio WhatsApp API wrapper)
│   ├── tasks.py                  # [NEW] Celery asynchronous tasks (send_restock_alerts)
│   └── api_views.py              # Webhook view for handling inbound Twilio webhooks
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
│   └── templates/                # HTML layout, Chart.js scripts, & Cashier Quick Widget
│
├── services/                     # Central Business Logic Services Directory
│   ├── customer_service.py       # Customer creation, verification, and opt-in logic
│   ├── intent_service.py         # Handles Blocked Intents, creations, and background resolutions
│   ├── inventory_service.py      # Stock updates, validation, and Celery task dispatches
│   └── notification_service.py   # Africa's Talking API simulation and logging
│
├── templates/                    # Global base HTML layouts & styling configurations
├── static/                       # Custom JS scripts and CSS stylesheets (Tailwind)
├── manage.py                     # Django management CLI wrapper
├── populate_data.py              # Seed script populated with categories, products, and intents
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
Customer directory record containing compliance flags.
* `first_name` (`CharField(max_length=100)`)
* `last_name` (`CharField(max_length=100)`)
* `phone_number` (`CharField(max_length=20)`, unique): Required for notification dispatching (must follow E.164 format: `+CountryCode...`).
* `email` (`EmailField`, nullable)
* `marketing_opt_in` (`BooleanField`, default `True`): Tracks whether the customer consents to receiving marketing and transactional messages.

### 4.6 `intents.BlockedPurchaseIntent`
Stores details about the blocked sales transaction, incorporating a lifecycle expiry field.
* `customer` (`ForeignKey` to `Customer`, on delete CASCADE)
* `product` (`ForeignKey` to `Product`, on delete CASCADE)
* `variation` (`ForeignKey` to `ProductVariation`, on delete SET_NULL, nullable): Specific variant desired (blank if a general product issue).
* `constraint_type` (`CharField`):
  - Actionable constraint choices:
    - `Size unavailable`
    - `Color unavailable`
    - `Out of stock`
    - `Price too high` (highly actionable for markdown/promotion targeting)
    - `Budget mismatch` (highly actionable for discount/financing conversions)
  - *Note: Unactionable constraints (e.g. "Authenticity concern") are excluded from the choice list.*
* `status` (`CharField`, default `Pending`): Choices are:
  - `Pending`: Capturing initial constraint.
  - `Monitoring`: Logged and watching inventory levels.
  - `Resolved`: Constraint solved, notification scheduled.
  - `Customer Notified`: Alert successfully sent to customer.
  - `Recovered`: Customer completed purchase.
  - `Closed`: Customer lost or intent archived.
* `requested_quantity` (`PositiveIntegerField`, default `1`)
* `estimated_value` (`DecimalField`, nullable): Revenue value of transaction. If blank, auto-calculated as `base_price * requested_quantity`.
* `notes` (`TextField`, blank): Qualitative details captured by staff.
* `recorded_by` (`ForeignKey` to `User`, on delete SET_NULL, nullable): Agent who logged the intent.
* `created_at` / `updated_at` (`DateTimeField`): Auditing timestamps.
* `expires_at` (`DateTimeField`): Automatic intent expiry timestamp (defaults to `created_at + 30 days`). Expired intents are excluded from restock check loops.

### 4.7 `notifications.NotificationLog`
Maintains auditing records of outbound alert dispatches.
* `intent` (`ForeignKey` to `BlockedPurchaseIntent`, on delete CASCADE)
* `message` (`TextField`): Message text.
* `sent_at` (`DateTimeField`, auto_now_add)
* `status` (`CharField`, default `Sent`): `Sent` or `Failed`.

### 4.8 `notifications.InboundSMSLog`
Maintains records of customer webhook responses.
* `from_number` / `to_number` (`CharField(max_length=30)`)
* `body` (`TextField`)
* `received_at` (`DateTimeField`, auto_now_add)
* `customer` (`ForeignKey` to `Customer`, on delete SET_NULL, nullable)

---

## 5. Core Workflows & Business Logic

### Workflow 1: Capturing Blocked Purchase Intent (Floor Cashier "3-Tap" Process)
Designed for high cashier compliance on the retail floor. When an item is identified as out-of-stock, the cashier uses a "Quick Intent Widget" to capture the demand instantly.

```mermaid
sequenceDiagram
    autonumber
    actor Staff as Store Cashier
    participant Widget as Quick Intent Widget (UI)
    participant API as Django Intent API
    participant DB as Database

    Note over Staff, Widget: Tap 1: Click "Log Missed Sale" from out-of-stock product details page
    Widget->>Widget: Auto-populate product_id, variation_id, and estimated base price
    Note over Staff, Widget: Tap 2: Enter customer phone number (auto-resolves customer details)
    Note over Staff, Widget: Tap 3: Tap "Log Sale" button
    Widget->>API: POST /api/intents/ (payload contains phone number and auto-populated product details)
    API->>DB: Query customer by phone; create profile if new. Create BlockedPurchaseIntent (expires_at = now + 30d)
    DB-->>Widget: Success response
    Widget-->>Staff: Display success badge & close widget
```

### Workflow 2: Asynchronous Inventory Restocking & Auto-Resolution (Celery + Redis)
To resolve the "Signal Storm" race condition, restocking database updates are processed in the service layer, and bulk notifications are executed asynchronously by Celery workers instead of synchronous Django model signals.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Inventory Manager
    participant Svc as services.inventory_service
    participant DB as Database
    participant Queue as Redis Queue
    participant Worker as Celery Background Worker

    Admin->>Svc: Update stock quantity of variation (stock > 0)
    Svc->>DB: Query active, non-expired (expires_at > now) intents matching variation
    DB-->>Svc: Return list of matching intent IDs
    loop For each matching intent ID
        Svc->>DB: Set status = 'Resolved' & Save
        Svc->>Queue: Push Celery task: send_restock_notification_task(intent_id)
    end
    Svc-->>Admin: Return HTTP response immediately (no lockups, no lag)
    
    Note over Queue, Worker: Celery Worker processes task in background
    Worker->>Worker: Pulls send_restock_notification_task(intent_id)
    Worker->>DB: Query intent details (Workflow 3)
```

### Workflow 3: Asynchronous Communication & Alert Dispatch (Celery Worker)
Background processing of outbound customer notifications, featuring marketing compliance check and opt-out formatting.

```mermaid
sequenceDiagram
    autonumber
    participant Worker as Celery Background Worker
    participant DB as Database
    participant Twilio as Twilio / SMS API
    
    Worker->>DB: Query Customer & Intent (Status: 'Resolved')
    alt Customer.marketing_opt_in is False
        Worker->>DB: Log failure (Reason: Opted Out)
        Note over Worker: Terminate task execution
    else Customer.marketing_opt_in is True
        Worker->>Worker: Check if notification already sent (prevent duplicates)
        Worker->>Worker: Format message template: "...Requested product is now in stock. Reply STOP to opt out."
        Worker->>Twilio: Post Message API request
        alt API Success
            Twilio-->>Worker: Return message SID
            Worker->>DB: Write NotificationLog (Status: 'Sent')
            Worker->>DB: Update BlockedPurchaseIntent (Status: 'Customer Notified')
        else API Failure
            Twilio-->>Worker: Return error
            Worker->>DB: Write NotificationLog (Status: 'Failed')
        end
    end
```

### Workflow 4: Callback Webhooks (Inbound Messages)
To handle incoming communication (e.g., a customer replying "STOP" or "HOLD IT"), the Flask application has been completely replaced with a native Django endpoint.

```
Incoming SMS/WhatsApp reply from Customer
                  │
                  ▼ (Triggers POST Webhook)
      /api/notifications/webhook/ (Django URL)
                  │
                  ▼ (Processed by Webhook View)
     notifications.api_views.WebhookView
                  │
                  ├───► 1. Read 'From', 'To', and 'Body' variables
                  ├───► 2. Save InboundSMSLog entry linked to customer profile
                  ├───► 3. If Body contains "STOP", set Customer.marketing_opt_in = False
                  │
                  ▼ (Returns native Django HttpResponse)
       HTTP/1.1 200 OK (Content-Type: application/xml)
       Body: <Response><Message>Thank you. Your response has been logged.</Message></Response>
```

### Workflow 5: Analytics, KPIs, and Restocking Recommendations
The dashboard aggregates operational data to guide stock replenishment:
* **KPI Metrics**:
  - *Total Blocked Purchases*: Total count of logged intents.
  - *Active Intents*: Count of intents in `Pending` or `Monitoring` state.
  - *Recovered Sales*: Count of intents in `Resolved`, `Customer Notified`, or `Recovered` state.
  - *Estimated Lost Revenue*: Sum of `estimated_value` of all unrecovered/unresolved intents (excludes `Resolved`, `Customer Notified`, and `Recovered`).
  - *Recovered Revenue*: Sum of `estimated_value` of all resolved/recovered intents.
* **Filter Rule**: Expired intents (`expires_at < current_time`) are completely excluded from KPI calculations and restock recommendation aggregates.
* **Restock Recommendation Engine**: Groups active (`Pending`/`Monitoring`) intents by `variation_id` and filters variations where the count is $\ge 4$ (configurable threshold). For each matching variant, it lists the demand count, current stock, and recommends restocks.

### Workflow 6: Document Export Reporting
Allows store admins to download data for review:
* **CSV Export (`ExportCSVReportView`)**: Fetches filtered intent records, creates a CSV stream, writes column headers, and stream-downloads row data containing customer info, product variations, values, and status.
* **PDF Export (`ExportPDFReportView`)**: Utilizes `ReportLab` to construct clean tabular documents. Applies page templates, sets up document margins, creates a structured grid showing intent statistics, and applies custom color tags (e.g., `#1E3A8A` for table styling).

---

## 6. Asynchronous Architecture & Task Queue (Replacing Signal Storms)

### 6.1 The "Signal Storm" Bottleneck (Removed)
In previous iterations, updates to inventory triggered chains of signals:
`ProductVariation.save()` $\rightarrow$ `on_variation_update` $\rightarrow$ `handle_stock_update()` $\rightarrow$ `resolve_blocked_intents()` $\rightarrow$ `send_resolution_notification()` $\rightarrow$ synchronous Twilio HTTP connection $\rightarrow$ `NotificationLog.save()` $\rightarrow$ `update_intent_status_on_notification()`.

Under bulk stock uploads, this synchronous design resulted in:
1. **Thread Starvation**: The request thread remained blocked while waiting for external Twilio API responses.
2. **Database Deadlocks**: Multiple concurrent signal chains updated the same tables, locking the databases.
3. **Cascading Failures**: A timeout in Twilio rolled back the database transaction, reverting the stock updates.

### 6.2 The production-grade Asynchronous Worker Model (Implemented)
By introducing Celery and Redis:
1. **Explicit Restocking**: `services/inventory_service.py` performs database status transitions for matching non-expired intents immediately.
2. **Background Handoff**: For each resolved intent, a worker task `send_restock_notification_task.delay(intent.id)` is dispatched to Redis.
3. **Decoupled Commits**: The web request commits immediately and returns a response, freeing database connections and threads.
4. **Resilient Retries**: Worker tasks run independently. If Twilio fails or times out, Celery retries the task later without affecting inventory updates.

---

## 7. Web UI & REST API Specifications

The system is managed through both a web-based dashboard interface and REST API endpoints.

### 7.1 Web Interface Views & Dashboard Status Badges
To improve visibility, the generic tabular list log on the dashboard utilizes highly visible, color-coded status badges:

| Status Code | Color / Badge Class | Styling Description | Meaning / Action |
| :--- | :--- | :--- | :--- |
| **Pending / Monitoring** | Flashing Orange (`bg-amber-500` / `#F59E0B` pulse) | Soft orange background with pulsing animation | High loss risk, awaiting restocking resolution |
| **Resolved** | Soft Blue (`bg-blue-500` / `#3B82F6`) | Standard blue background | Constraint resolved, notification scheduled in queue |
| **Customer Notified** | Bright Green (`bg-emerald-500` / `#10B981`) | Solid green background | Restock notification successfully sent |
| **Recovered** | Deep Emerald (`bg-green-700` / `#047857` text-white) | Solid dark-green background with tick icon | Sale recovered, customer completed checkout |
| **Closed** | Slate Gray (`bg-slate-400` / `#94A3B8`) | Neutral gray background | Locked/archived (expired or manually cancelled) |

### 7.2 The Floor Cashier "Quick Intent Widget"
A lightweight panel displayed on floor registers:
- **Product Context**: Dynamically pre-populates category, product name, variation SKU, and estimated lost value.
- **Minimal Input**: Only asks for the customer's phone number.
- **Opt-in Toggle**: Quick checkmark representing compliance verbal consent.
- **Tap count**: 3 taps (1. Tap "Log Missed Sale", 2. Tap phone input, 3. Tap "Submit").

### 7.3 API Router Maps
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
* `/api/notifications/webhook/` **[NEW]**: Replaces Flask. Native Django View class mapping POST requests from Twilio. Validates webhook signature, logs incoming payloads to `InboundSMSLog`, parses "STOP" replies, and updates opt-in compliance state.

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
* `celery` **[NEW]**: Distributed task queue wrapper.
* `redis` **[NEW]**: Broker library for Celery/Redis connection.

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

# Celery and Redis Configuration
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

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
5. **Start Redis Server**:
   ```bash
   # Run Redis container (or local service)
   docker run -d -p 6379:6379 redis:alpine
   ```
6. **Start Celery Worker**:
   ```bash
   celery -A core worker --loglevel=info
   ```
