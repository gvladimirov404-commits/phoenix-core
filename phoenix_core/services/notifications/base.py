"""NotificationService — minimal delivery-channel abstraction (TASK-023
Phase G). Deliberately tiny: one async method, boolean success/failure.
Designed so a future Discord/email/etc. adapter can implement the same
interface without touching AlertService — but no such adapter is built
in this phase.
"""
from typing import Protocol


class NotificationService(Protocol):
    """Anything that can deliver a text message to a user_id."""

    async def send(self, user_id: int, text: str) -> bool:
        """Attempt delivery. Returns True on success, False on failure —
        never raises for expected delivery failures (e.g. blocked bot,
        network error); callers rely on the boolean, not exceptions."""
        ...
