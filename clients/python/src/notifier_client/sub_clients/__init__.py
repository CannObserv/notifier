"""Sub-clients for the notifier API.

Each sub-client is a thin facade over ``NotifierClient._typed_request``.
They never own state; they hold a reference to the parent client.
"""
