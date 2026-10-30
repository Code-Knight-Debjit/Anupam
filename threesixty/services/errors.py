"""One error type for rule violations raised by services. The API layer turns
it into a JSON error response (`ApiError` is a subclass), so services never
need to import anything from `threesixty.api`."""


class ServiceError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra
