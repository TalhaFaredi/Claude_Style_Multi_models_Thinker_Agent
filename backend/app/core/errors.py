"""Errors the API turns into plain HTTP answers (see main.py)."""


class UnknownChat(Exception):
    """The chat does not exist, or belongs to someone else. Both look the same on purpose."""
