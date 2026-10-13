def average(values):
    """Return the arithmetic mean; return 0.0 when values is empty."""
    if not values:
        return 0.0
    return sum(values) / len(values)
