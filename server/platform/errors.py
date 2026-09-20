class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details

    def as_dict(self):
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}
