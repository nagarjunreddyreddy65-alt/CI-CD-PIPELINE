"""Unit tests for sample_app.billing.payment_processor (Sensitive Payment Module)."""

import pytest
from sample_app.billing.payment_processor import PaymentProcessor


def test_invoice_calculation_standard():
    items = [
        {"item_name": "Cloud Compute Hours", "unit_price": 50.0, "quantity": 2},
        {"item_name": "Storage Add-on", "unit_price": 20.0, "quantity": 1},
    ]
    invoice = PaymentProcessor.calculate_invoice_total(items, discount_pct=10.0)
    # subtotal = 100 + 20 = 120
    # discount = 12 (10%) -> discounted = 108
    # tax = 108 * 0.0825 = 8.91
    # grand_total = 108 + 8.91 = 116.91
    assert invoice["subtotal"] == 120.0
    assert invoice["discount_amount"] == 12.0
    assert invoice["tax_amount"] == 8.91
    assert invoice["grand_total"] == 116.91


def test_invalid_discount_rejected():
    with pytest.raises(ValueError, match="between 0 and 100"):
        PaymentProcessor.calculate_invoice_total([], discount_pct=150.0)


def test_validate_payment_details():
    assert PaymentProcessor.validate_payment_details(100.0, "USD", "credit_card") is True
    assert PaymentProcessor.validate_payment_details(50.0, "EUR", "ach") is True
    assert PaymentProcessor.validate_payment_details(-10.0, "USD", "credit_card") is False
    assert PaymentProcessor.validate_payment_details(100.0, "INVALID_CURR", "credit_card") is False
