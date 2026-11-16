def format_rupees(amount: int | float) -> str:
    """Whole rupees as ₹ with Indian digit grouping, e.g. 1234567 -> ₹12,34,567.

    The one place the server turns a price into text (notifications and anything else that needs
    words). The SPA does the same with `formatPrice` in src/utils/labels.js; keep them in step.
    """
    whole = int(round(amount))
    sign = "-" if whole < 0 else ""
    digits = str(abs(whole))

    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])

    return f"{sign}₹{digits}"


def format_price(amount: int | float, unit: str | None = None) -> str:
    """'Free' for zero, otherwise ₹ amount with an optional ' / unit' (the SPA's `formatPrice`)."""
    if not amount or amount <= 0:
        return "Free"
    return f"{format_rupees(amount)}{f' / {unit}' if unit else ''}"
