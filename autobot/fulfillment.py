"""
Convert an incoming Etsy webhook order payload into a Printify order and submit it.
"""
from __future__ import annotations

import logging
from typing import Any

from .etsy_agent import get_order
from .printify_agent import submit_order

log = logging.getLogger(__name__)


def _build_printify_order(etsy_receipt: dict[str, Any]) -> dict[str, Any]:
    """Map Etsy receipt fields onto the Printify order schema."""
    buyer = etsy_receipt.get("buyer_user_id", "unknown")
    address = etsy_receipt.get("formatted_address", {})

    line_items = []
    for transaction in etsy_receipt.get("transactions", []):
        # listing_id maps to the Printify external_id set at product creation
        printify_product_id = transaction.get("product_data", {}).get(
            "printify_product_id", ""
        )
        variant_id = transaction.get("product_data", {}).get("printify_variant_id", 0)
        quantity = transaction.get("quantity", 1)
        if printify_product_id:
            line_items.append(
                {
                    "product_id": printify_product_id,
                    "variant_id": variant_id,
                    "quantity": quantity,
                }
            )

    return {
        "external_id": str(etsy_receipt.get("receipt_id", "")),
        "label": f"Etsy-{etsy_receipt.get('receipt_id', '')}",
        "line_items": line_items,
        "shipping_method": 1,  # standard
        "send_shipping_notification": True,
        "address_to": {
            "first_name": address.get("first_name", ""),
            "last_name": address.get("last_name", ""),
            "email": etsy_receipt.get("buyer_email", ""),
            "phone": "",
            "country": address.get("country_iso", "US"),
            "region": address.get("state", ""),
            "address1": address.get("first_line", ""),
            "address2": address.get("second_line", ""),
            "city": address.get("city", ""),
            "zip": address.get("zip", ""),
        },
    }


async def fulfill_etsy_order(receipt_id: str) -> str:
    """Fetch the Etsy order and submit fulfillment to Printify. Returns Printify order ID."""
    log.info("Fulfilling Etsy receipt %s", receipt_id)
    etsy_receipt = await get_order(receipt_id)
    printify_order = _build_printify_order(etsy_receipt)

    if not printify_order["line_items"]:
        log.warning("Receipt %s has no mappable line items — skipping", receipt_id)
        return ""

    printify_order_id = await submit_order(printify_order)
    return printify_order_id
