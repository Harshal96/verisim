"""Example business branches; called once inside each coverage measurement."""

from models import Customer
from schemas import CreateOrder


def create_order(payload: dict, actor: dict, environment: dict) -> int:
    request = CreateOrder.model_validate(payload)
    if request.quantity <= 0:  # branch:quantity
        return 422
    if not actor.get("admin", False):  # branch:auth
        return 403
    if not environment.get("inventory_online", False):  # branch:inventory
        return 503
    customer = Customer.objects.filter(pk=request.customer_id).first()
    if customer is None:  # branch:found
        return 404
    if not customer.is_active:  # branch:active
        return 409
    return 201
