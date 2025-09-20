from contextvars import ContextVar
from typing import Optional

# A context variable to store the scenario for the current request
scenario_context: ContextVar[Optional[str]] = ContextVar("scenario_context", default=None)