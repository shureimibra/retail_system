import hmac
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services
from .models import MpesaRequest


@csrf_exempt
@require_POST
def mpesa_callback(request, token):
    """Safaricom calls this when a payment prompt ends. The secret token in the address proves it's ours."""
    if not settings.MPESA_CALLBACK_TOKEN or not hmac.compare_digest(token, settings.MPESA_CALLBACK_TOKEN):
        raise Http404
    try:
        payload = json.loads(request.body or b'{}')
    except ValueError:
        payload = {}
    services.handle_callback(payload)
    # Always "accepted": Safaricom only needs to know we received it.
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})


@login_required
def mpesa_status(request, pk):
    """The deal panel checks this every few seconds while a prompt is waiting."""
    mpesa = get_object_or_404(MpesaRequest, pk=pk, shop=request.shop)
    mpesa = services.refresh(mpesa)
    return JsonResponse({'status': mpesa.status, 'label': mpesa.get_status_display(), 'detail': mpesa.result_desc,
                         'receipt': mpesa.receipt})
