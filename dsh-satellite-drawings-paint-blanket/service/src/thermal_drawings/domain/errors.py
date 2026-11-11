class ServiceError(Exception):
    def __init__(self, status, code, message, stage='request'):
        super().__init__(message)
        self.status = status
        self.error = dict(code=code, message=message, stage=stage,
                          retryable=status in (409, 503), evidence_refs=[])


def require(condition, status=422, code='invalid_input', message='Invalid input'):
    if not condition:
        raise ServiceError(status, code, message)
