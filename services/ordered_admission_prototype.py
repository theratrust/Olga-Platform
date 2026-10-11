"""Offline model of ordered polling ingress. Not imported by bot.py.

A single polling owner calls offer() synchronously, in received-update order,
before it starts ordinary handler tasks. Only short admission operations are
ordered per user; acknowledgement and downstream work run separately.
"""
import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal


Kind = Literal["normal_text", "voice", "new"]
Status = Literal["admitted", "rejected", "reset"]


@dataclass(frozen=True)
class IngressMessage:
    polling_sequence: int  # local receive ordinal, not Telegram update_id
    user_id: int
    chat_id: int
    message_id: int
    kind: Kind
    text: str | None = None  # never used to decide ordering


@dataclass(frozen=True)
class AdmissionResult:
    polling_sequence: int
    user_id: int
    kind: Kind
    marker: tuple[int, int]
    status: Status
    conversation_id: str | None
    reason: str | None = None


class OrderedAdmissionPrototype:
    """Per-user FIFO admission reserved before downstream task fan-out.

    The injected ports represent atomic DB admission/rotation, acknowledgement,
    and long handler work. The voice port is a *prototype reservation*; the
    current runtime DB cannot persist a transcript before transcription.
    """

    def __init__(
        self,
        admit: Callable[[IngressMessage], Awaitable[tuple[str | None, str | None]]],
        rotate: Callable[[IngressMessage], Awaitable[str | None]],
        acknowledge: Callable[[AdmissionResult], Awaitable[None]],
        downstream: Callable[[AdmissionResult], Awaitable[None]],
    ):
        self._admit = admit
        self._rotate = rotate
        self._acknowledge = acknowledge
        self._downstream = downstream
        self._last_sequence: int | None = None
        self._tails: dict[int, asyncio.Task[AdmissionResult]] = {}
        self._work: list[asyncio.Task[None]] = []

    def offer(self, update: IngressMessage) -> asyncio.Task[AdmissionResult]:
        """Called without an await by one ordered polling ingress producer.

        Reject a reordered producer call. Never sort already-running handlers
        or infer missing Telegram message IDs from numeric gaps.
        """
        if type(update.polling_sequence) is not int or (
            self._last_sequence is not None
            and update.polling_sequence <= self._last_sequence
        ):
            raise ValueError("polling ingress order must be strictly increasing")
        self._last_sequence = update.polling_sequence
        predecessor = self._tails.get(update.user_id)
        task = asyncio.create_task(self._admit_after(predecessor, update))
        self._tails[update.user_id] = task
        return task

    async def _admit_after(
        self,
        predecessor: asyncio.Task[AdmissionResult] | None,
        update: IngressMessage,
    ) -> AdmissionResult:
        if predecessor is not None:
            await predecessor

        marker = (update.chat_id, update.message_id)
        if (
            type(update.user_id) is not int
            or type(update.chat_id) is not int
            or update.chat_id != update.user_id
            or type(update.message_id) is not int
            or update.message_id <= 0
            or update.kind not in ("normal_text", "voice", "new")
        ):
            return AdmissionResult(
                update.polling_sequence, update.user_id, update.kind,
                marker, "rejected", None, "incomparable",
            )

        try:
            if update.kind == "new":
                conversation_id = await self._rotate(update)
                status: Status = "reset" if conversation_id else "rejected"
                reason = None if conversation_id else "stale"
            else:
                conversation_id, reason = await self._admit(update)
                status = "admitted" if conversation_id else "rejected"
        except Exception:
            conversation_id, reason, status = None, "db_failure", "rejected"

        result = AdmissionResult(
            update.polling_sequence, update.user_id, update.kind,
            marker, status, conversation_id, reason,
        )
        if status != "rejected":
            self._work.append(asyncio.create_task(self._after_commit(result)))
        return result

    async def _after_commit(self, result: AdmissionResult) -> None:
        await self._acknowledge(result)
        await self._downstream(result)

    async def wait_for_downstream(self) -> None:
        """Test-only drain; admission never waits for this work."""
        await asyncio.gather(*self._work)
