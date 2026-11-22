"""
Billing and Payment Processing Service.
NOTE: This is a sensitive billing module.
Any change in this module triggers Safety Rule 3 (Payment Fallback).
"""

from typing import Any


class PaymentProcessor:
    """Processes customer invoices and computes payment balances."""

    TAX_RATE = 0.0825  # 8.25%

    @classmethod
    def calculate_invoice_total(
        cls, line_items: list[dict[str, Any]], discount_pct: float = 0.0
    ) -> dict[str, float]:
        """Calculates subtotal, discount, tax, and grand total."""
        if discount_pct < 0.0 or discount_pct > 100.0:
            raise ValueError("Discount percentage must be between 0 and 100")

        subtotal = sum(
            float(item.get("unit_price", 0.0)) * int(item.get("quantity", 0)) for item in line_items
        )
        discount_amount = round(subtotal * (discount_pct / 100.0), 2)
        discounted_subtotal = max(0.0, subtotal - discount_amount)
        tax_amount = round(discounted_subtotal * cls.TAX_RATE, 2)
        total = round(discounted_subtotal + tax_amount, 2)

        return {
            "subtotal": round(subtotal, 2),
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "grand_total": total,
        }

    @classmethod
    def validate_payment_details(cls, amount: float, currency: str, payment_method: str) -> bool:
        """Validates payment payload."""
        return (
            amount > 0.0
            and currency.upper() in ["USD", "EUR", "GBP", "INR"]
            and payment_method.lower() in ["credit_card", "ach", "wire", "crypto"]
        )
