class StorageError(ValueError):
    """Safe domain error, independent of transport."""


class Conflict(StorageError):
    pass


class NotFound(StorageError):
    pass


class AccessDenied(StorageError):
    pass
