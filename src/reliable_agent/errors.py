"""Agent-specific exceptions."""


class ReliableAgentError(Exception):
    pass


class ModelRequestError(ReliableAgentError):
    pass


class ProtocolError(ReliableAgentError):
    pass


class BudgetExceededError(ReliableAgentError):
    pass
