"""Typed CloudTxn failures."""


class CloudTxnError(Exception):
    """Base error for expected CloudTxn failures."""


class ConfigurationError(CloudTxnError):
    """The transaction cannot be safely prepared."""


class AdapterError(CloudTxnError):
    """An adapter operation or verification failed."""
