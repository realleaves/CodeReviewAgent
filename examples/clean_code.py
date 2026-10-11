"""A corresponding normal example."""


def average(values):
    """Accept a possibly empty numeric list; empty input returns zero."""
    return sum(values) / len(values) if values else 0


def collect(value, items=None):
    """Each call without items gets its own fresh list."""
    if items is None:
        items = []
    items.append(value)
    return items


def lookup(connection, username):
    """Use sqlite parameter binding for untrusted input."""
    return connection.execute("SELECT * FROM users WHERE name = ?", (username,)).fetchall()
