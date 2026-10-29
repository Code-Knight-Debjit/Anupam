"""What is PRINTED on quotation / proforma / challan documents (REQ-PRN-*).

The printed totals deliberately differ from the entry form:
  * "show discount" OFF (default): the discount is folded into the rate and the
    rate is ROUNDED to a whole rupee (JavaScript `Math.round`: half up); the
    amount is qty x that rate.
  * "show discount" ON: the rate is shown as entered and the amount is
    qty x rate x (1 - disc%).
  * Line tax is NOT part of the line amount: all line tax is added into one
    "Tax Amount" after Sub Total.
Money is `Decimal`; `ROUND_HALF_UP` everywhere the reference app used `Math.round`.
"""
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from ..rules.anupam_rules import number_to_words_indian

TWO = Decimal('0.01')
HUNDRED = Decimal('100')
ZERO = Decimal('0')


def js_round(x) -> int:
    """JavaScript `Math.round`: the nearest integer, halves go up (not banker's rounding)."""
    return int((Decimal(x) + Decimal('0.5')).to_integral_value(rounding=ROUND_FLOOR))


def money(x) -> Decimal:
    return Decimal(x).quantize(TWO, rounding=ROUND_HALF_UP)


def _charge(amount, tax_pct):
    return Decimal(amount or 0) * (1 + Decimal(tax_pct or 0) / HUNDRED)


def print_totals(document, items=None):
    """Lines and totals as printed. `items` defaults to the document's items."""
    show = bool(document.show_discount_in_pdf)
    sub = tax_total = ZERO
    lines = []
    for number, item in enumerate(items if items is not None else document.items.all(), start=1):
        qty, rate, disc, tax = Decimal(item.qty), Decimal(item.rate), Decimal(item.discount), Decimal(item.tax)
        if show:
            shown_rate, amount = rate, qty * rate * (1 - disc / HUNDRED)
        else:
            shown_rate = Decimal(js_round(rate * (1 - disc / HUNDRED)))
            amount = qty * shown_rate
        line_tax = amount * tax / HUNDRED
        sub += amount
        tax_total += line_tax
        name = f'{item.item_name or "—"} ({item.make})' if item.make else (item.item_name or '—')
        lines.append({'sr': number, 'name': name, 'qty': qty, 'unit': item.unit, 'rate': shown_rate,
                      'discount': disc, 'amount': amount, 'tax': line_tax})
    packing = _charge(document.packing_charges, document.packing_tax)
    freight = _charge(document.freight_charges, document.freight_tax)
    other = _charge(document.other_charges, document.other_charges_tax)
    round_off = Decimal(document.round_off or 0)
    total = sub + tax_total + packing + freight + other + round_off
    return {'lines': lines, 'sub_total': sub, 'tax_total': tax_total, 'packing': packing, 'freight': freight,
            'other': other, 'round_off': round_off, 'total': total}


def amount_in_words(amount) -> str:
    """Indian system: 'Rupees One Lakh Twenty Three Thousand ... and Fifty Paise Only'."""
    amount = money(amount)
    rupees = int(abs(amount))
    paise = int(((abs(amount) - rupees) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    words = 'Rupees ' + number_to_words_indian(rupees)
    if paise > 0:
        words += ' and ' + number_to_words_indian(paise) + ' Paise'
    words += ' Only'
    return ('Minus ' + words) if amount < 0 else words


def quotation_value_of(document, items=None) -> Decimal:
    """Value used in reports: the stored total, else the sum of item values, else the legacy value (REQ-PRN-04)."""
    if document.total_amount:
        return Decimal(document.total_amount)
    values = [Decimal(i.value) for i in (items if items is not None else document.items.all())]
    if values and any(values):
        return sum(values, ZERO)
    return Decimal(document.quotation_value or 0)
