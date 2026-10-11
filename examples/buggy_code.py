"""Small intentionally defective example; review it as text."""


def average(values):
    """Accept a possibly empty numeric list; empty input should return zero."""
    return sum(values) / len(values)


def collect(value, items=[]):
    """Each call without items should get its own fresh list."""
    items.append(value)
    return items


def lookup(connection, username):
    """username is supplied by an untrusted HTTP client."""
    return connection.execute(f"SELECT * FROM users WHERE name = '{username}'").fetchall()
