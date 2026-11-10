"""Agent-specific exceptions."""


class ReliableAgentError(Exception):
    pass


class ModelRequestError(ReliableAgentError):
    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


class ProtocolError(ReliableAgentError):
    pass


class BudgetExceededError(ReliableAgentError):
    pass
