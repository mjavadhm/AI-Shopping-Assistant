from contextvars import ContextVar

total_cost_per_session: float = 0.0

current_request_cost_var: ContextVar[float] = ContextVar("current_request_cost", default=0.0)