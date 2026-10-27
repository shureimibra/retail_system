"""What a POS (or any other system) can do with an API key: read items and the To order list, send stock and sales."""
from django.db import IntegrityError, transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.selectors import get_to_order
from intents.services import record_bought_visit
from products import services as stock
from products.models import Product, ProductVariation
from .auth import ApiKeyAuthentication, KeyPermission, KeyThrottle
from .models import ConnectionRequest

MAX_LINES = 500


class ConnectView(APIView):
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [KeyPermission]
    throttle_classes = [KeyThrottle]

    def reference(self, request):
        text = str(request.data.get('reference', '') or '')
        return f'{request.auth.name}: {text}'[:100] if text else request.auth.name[:100]

    def once(self, request, apply):
        """Apply a change once per Idempotency-Key. Sending the same key again returns the first answer."""
        idempotency_key = request.headers.get('Idempotency-Key', '').strip()[:100]
        if idempotency_key:
            earlier = ConnectionRequest.objects.filter(key=request.auth, idempotency_key=idempotency_key).first()
            if earlier:
                return Response(earlier.response, status=earlier.status_code, headers={'Idempotent-Replay': 'true'})
        body, status = apply()
        if idempotency_key:
            try:
                with transaction.atomic():
                    ConnectionRequest.objects.create(key=request.auth, idempotency_key=idempotency_key,
                                                     path=request.path[:100], status_code=status, response=body)
            except IntegrityError:
                pass
        return Response(body, status=status)

    def lines(self, request, field):
        rows = request.data.get(field) if isinstance(request.data, dict) else None
        if not isinstance(rows, list) or not rows:
            return None, f'Send "{field}" as a list.'
        if len(rows) > MAX_LINES:
            return None, f'Send at most {MAX_LINES} {field} at a time.'
        return rows, ''

    def variation(self, request, sku):
        return ProductVariation.objects.filter(product__shop=request.shop, sku__iexact=str(sku or '').strip()).first()


class ProductsView(ConnectView):
    def get(self, request):
        rows = []
        products = (Product.objects.filter(shop=request.shop).select_related('product_type')
                    .prefetch_related('variations__holds'))
        for product in products.order_by('name'):
            for v in product.variations.all():
                rows.append({'sku': v.sku, 'item': product.name,
                             'type': product.product_type.name if product.product_type else '',
                             'size': v.option1 or '', 'colour': v.option2 or '', 'price': str(v.effective_price),
                             'in_stock': v.stock_quantity, 'held_for_customers': v.held_quantity,
                             'available': v.available_quantity})
        return Response({'products': rows})


class ToOrderView(ConnectView):
    def get(self, request):
        return Response({'to_order': get_to_order(request.shop)})


def _whole(value, minimum):
    """A whole number of at least `minimum`, or None. Accepts 3 and "3", not 3.5, "three" or true."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number >= minimum else None


class StockView(ConnectView):
    """
    {"changes": [{"sku": "AU-42-GRE", "set": 5}, {"sku": "…", "add": 3}, {"sku": "…", "remove": 1}], "reference": "…"}
    set is a count, add is a delivery (waiting customers are told), remove is stock taken out (damaged, returned…).
    """
    def post(self, request):
        return self.once(request, lambda: self.apply(request))

    def apply(self, request):
        rows, error = self.lines(request, 'changes')
        if error:
            return {'error': error}, 400
        reference, results = self.reference(request), []
        for row in rows:
            row = row if isinstance(row, dict) else {}
            sku = row.get('sku', '')
            actions = [name for name in ('set', 'add', 'remove') if name in row]
            variation = self.variation(request, sku)
            if variation is None:
                results.append({'sku': sku, 'ok': False, 'error': 'No item with this SKU in this shop.'})
                continue
            if len(actions) != 1:
                results.append({'sku': sku, 'ok': False, 'error': 'Give exactly one of "set", "add" or "remove".'})
                continue
            action = actions[0]
            amount = _whole(row[action], 0 if action == 'set' else 1)
            if amount is None:
                least = '0' if action == 'set' else '1'
                results.append({'sku': sku, 'ok': False, 'error': f'"{action}" must be a whole number of {least} or more.'})
                continue
            new = {'set': amount, 'add': variation.stock_quantity + amount,
                   'remove': variation.stock_quantity - amount}[action]
            if new < variation.held_quantity:
                results.append({'sku': sku, 'ok': False, 'error': f"{variation.held_quantity} put aside for customers: "
                                                                  "stock can't go below that."})
                continue
            if action == 'add':
                variation = stock.receive_stock(variation.pk, amount, reference=reference)
            else:
                variation = stock.set_stock(variation.pk, new, reference=reference)
            results.append({'sku': variation.sku, 'ok': True, 'in_stock': variation.stock_quantity})
        return {'results': results}, 200


class SalesView(ConnectView):
    """{"items": [{"sku": "AU-42-GRE", "quantity": 1}], "reference": "Receipt 1043"}: one sale at the till."""
    def post(self, request):
        return self.once(request, lambda: self.apply(request))

    def apply(self, request):
        rows, error = self.lines(request, 'items')
        if error:
            return {'error': error}, 400
        reference, results, sold_any = self.reference(request), [], False
        for row in rows:
            row = row if isinstance(row, dict) else {}
            sku = row.get('sku', '')
            quantity = _whole(row.get('quantity', 1), 1)
            variation = self.variation(request, sku)
            if variation is None:
                results.append({'sku': sku, 'ok': False, 'error': 'No item with this SKU in this shop.'})
                continue
            if quantity is None:
                results.append({'sku': sku, 'ok': False, 'error': '"quantity" must be a whole number of 1 or more.'})
                continue
            variation, taken = stock.record_till_sale(variation.pk, quantity, reference=reference)
            sold_any = sold_any or taken > 0
            result = {'sku': variation.sku, 'ok': True, 'sold': taken, 'in_stock': variation.stock_quantity}
            if taken < quantity:
                result['warning'] = (f'Only {taken} {"was" if taken == 1 else "were"} free; the rest are put aside for '
                                     'customers or the count was already wrong. Count this item again.')
            results.append(result)
        if sold_any:
            record_bought_visit(request.shop)
        return {'results': results}, 200
