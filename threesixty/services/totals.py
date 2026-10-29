"""Exact port of the sales-document save-time item/charges math
(`contact_management.html` ~L11370-11436) — this is the formula that
decides what gets *persisted* on save, distinct from the separate
print-time `computeQuotationDocData` (~L8805-8850) used only to lay out
the PDF/print view, which deliberately rounds the discount-folded rate for
display and is ported separately in Phase 3/4's PDF export work.

Per-type flags below are copied verbatim from `SALES_DOC_CONFIG`
(~L3635-3696):
  - enquiry has no item columns at all (`itemCols: []`).
  - po has `hasDiscount` but neither `hasTax` nor `hasCharges`.
  - quotation/dc/proforma all have `hasDiscount` + `hasTax` + `hasCharges`.
"""
from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal('0.01')

TYPE_FLAGS = {
    'enquiry': {'has_items': False, 'has_charges': False},
    'quotation': {'has_items': True, 'has_discount': True, 'has_tax': True, 'has_charges': True},
    'po': {'has_items': True, 'has_discount': True, 'has_tax': False, 'has_charges': False},
    'dc': {'has_items': True, 'has_discount': True, 'has_tax': True, 'has_charges': True},
    'proforma': {'has_items': True, 'has_discount': True, 'has_tax': True, 'has_charges': True},
}


def _num(value):
    if value in (None, ''):
        return Decimal('0')
    return Decimal(str(value))


def compute_item_fields(doc_type, item_data):
    """Mirrors the save handler's per-item `amount`/`value`:
        if(cfg.hasDiscount){
          unitFinal = rate * (1 - discount/100);
          if(cfg.hasTax) unitFinal *= (1 + tax/100);
          amount = unitFinal; value = qty * unitFinal;
        } else if(cfg.itemCols.includes('rate')){
          amount = qty * rate; value = amount;   // (only po-less types; unused today)
        }
    Returns (amount, value) as Decimals."""
    flags = TYPE_FLAGS.get(doc_type, {})
    qty = _num(item_data.get('qty'))
    rate = _num(item_data.get('rate'))
    discount = _num(item_data.get('discount'))
    tax = _num(item_data.get('tax'))
    if flags.get('has_discount'):
        unit_final = rate * (Decimal('1') - discount / Decimal('100'))
        if flags.get('has_tax'):
            unit_final = unit_final * (Decimal('1') + tax / Decimal('100'))
        amount = unit_final
        value = qty * unit_final
    elif flags.get('has_items'):
        amount = qty * rate
        value = amount
    else:
        amount = Decimal('0')
        value = Decimal('0')
    return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def compute_document_totals(doc_type, items_data, packing, packing_tax, freight, freight_tax,
                             other, other_tax, round_off):
    """Mirrors:
        subTotal = items.reduce((s,it)=> s + it.value, 0);
        packingFinal = packing * (1 + packingTax/100);  // (same for freight/other)
        totalAmount = subTotal + packingFinal + freightFinal + otherFinal + roundOff;
    Only meaningful for types with `has_charges` — callers on other types
    should leave sub_total/total_amount at 0, matching the original (the
    form never shows/sets these fields for enquiry/po)."""
    flags = TYPE_FLAGS.get(doc_type, {})
    zero = Decimal('0').quantize(TWO_PLACES)
    if not flags.get('has_charges'):
        return zero, zero
    sub_total = sum((compute_item_fields(doc_type, item)[1] for item in items_data), Decimal('0'))
    packing_final = _num(packing) * (Decimal('1') + _num(packing_tax) / Decimal('100'))
    freight_final = _num(freight) * (Decimal('1') + _num(freight_tax) / Decimal('100'))
    other_final = _num(other) * (Decimal('1') + _num(other_tax) / Decimal('100'))
    total_amount = sub_total + packing_final + freight_final + other_final + _num(round_off)
    return sub_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), total_amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
