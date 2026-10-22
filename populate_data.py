from accounts.models import User
from products.models import Category, Product, ProductVariation
from customers.models import Customer
from intents.models import BlockedPurchaseIntent
from django.utils import timezone
import datetime

# Clean up existing data if any
BlockedPurchaseIntent.objects.all().delete()
ProductVariation.objects.all().delete()
Product.objects.all().delete()
Category.objects.all().delete()
Customer.objects.all().delete()

# Create Categories
c1 = Category.objects.create(name="Footwear", description="Running shoes, boots, and sneakers")
c2 = Category.objects.create(name="Apparel", description="Shirts, pants, jackets")
c3 = Category.objects.create(name="Accessories", description="Watches, bags, belts")

# Create Products
p1 = Product.objects.create(category=c1, name="Nike Air Zoom", description="Premium running shoes", base_price=120.00)
p2 = Product.objects.create(category=c1, name="Adidas Ultraboost", description="Ultra comfortable running shoes", base_price=180.00)
p3 = Product.objects.create(category=c2, name="Levi's 511 Slim", description="Classic slim-fit denim jeans", base_price=70.00)
p4 = Product.objects.create(category=c3, name="Leather Messenger Bag", description="Handcrafted genuine leather messenger bag", base_price=150.00)

# Create Variations
v1 = ProductVariation.objects.create(product=p1, option1="42", option2="Black", stock_quantity=0, sku="NIKE-AZ-42-BLK")
v2 = ProductVariation.objects.create(product=p1, option1="44", option2="White", stock_quantity=5, sku="NIKE-AZ-44-WHT")
v3 = ProductVariation.objects.create(product=p2, option1="42", option2="Grey", stock_quantity=0, sku="ADI-UB-42-GRY")
v4 = ProductVariation.objects.create(product=p3, option1="32", option2="Blue", stock_quantity=0, sku="LEV-511-32-BLU")

# Create Customers
cust1 = Customer.objects.create(first_name="John", last_name="Doe", phone_number="+254712345678", email="john.doe@example.com")
cust2 = Customer.objects.create(first_name="Jane", last_name="Smith", phone_number="+254722345678", email="jane.smith@example.com")
cust3 = Customer.objects.create(first_name="Robert", last_name="Johnson", phone_number="+254733345678", email="robert.j@example.com")
cust4 = Customer.objects.create(first_name="Mary", last_name="Williams", phone_number="+254744345678", email="mary.w@example.com")

# Create Blocked Purchase Intents with different timestamps and statuses
admin_user = User.objects.get(username='admin')

# John Doe wanted Nike Air Zoom Size 42 Black (out of stock)
BlockedPurchaseIntent.objects.create(
    customer=cust1, product=p1, variation=v1,
    constraint_type="Out of stock", status="Pending",
    requested_quantity=1, estimated_value=120.00,
    notes="Customer was very interested, promised to return if notified.",
    recorded_by=admin_user
)

# Jane Smith also wanted Nike Air Zoom Size 42 Black
BlockedPurchaseIntent.objects.create(
    customer=cust2, product=p1, variation=v1,
    constraint_type="Out of stock", status="Pending",
    requested_quantity=1, estimated_value=120.00,
    notes="Wants Black size 42 specifically.",
    recorded_by=admin_user
)

# Robert Johnson also wanted Nike Air Zoom Size 42 Black
BlockedPurchaseIntent.objects.create(
    customer=cust3, product=p1, variation=v1,
    constraint_type="Out of stock", status="Pending",
    requested_quantity=2, estimated_value=240.00,
    notes="Needs 2 pairs for a marathon.",
    recorded_by=admin_user
)

# Jane Smith wanted Adidas Ultraboost Size 42 Grey
BlockedPurchaseIntent.objects.create(
    customer=cust2, product=p2, variation=v3,
    constraint_type="Size unavailable", status="Monitoring",
    requested_quantity=1, estimated_value=180.00,
    notes="Grey colour preferred, size 42 was missing.",
    recorded_by=admin_user
)

# Mary Williams wanted Messenger Bag but price was too high
BlockedPurchaseIntent.objects.create(
    customer=cust4, product=p4, variation=None,
    constraint_type="Price too high", status="Closed",
    requested_quantity=1, estimated_value=150.00,
    notes="Asked for a 20% discount which wasn't authorized.",
    recorded_by=admin_user
)

# John Doe wanted Levi's 511 Slim Blue size 32 but color/size unavailable, recovered later
intent_recovered = BlockedPurchaseIntent.objects.create(
    customer=cust1, product=p3, variation=v4,
    constraint_type="Color unavailable", status="Recovered",
    requested_quantity=1, estimated_value=70.00,
    notes="Wants blue color. Recovered after we got stock.",
    recorded_by=admin_user
)

print("Sample data populated successfully!")
