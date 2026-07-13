"""Felix policy for authenticated schedules and durable Web Push dispatch.

The service accepts only predefined product notification kinds for the current
account. Callers cannot supply visible copy, payload JSON, endpoints, or routes.
Reusable provider storage and worker mechanics remain app-neutral.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from itertools import islice
import re
from typing import Callable, Iterable

from api.settings import settings
from apps.felix.services.web_push_service import (
    FelixWebPushMessage,
    FelixWebPushService,
    load_web_push_delivery_config,
)
from backend.shared_services.web_push_dispatch import (
    WebPushDispatchBackgroundService,
    WebPushDispatchDraft,
    WebPushDispatchPolicy,
    WebPushDispatchWorker,
    WebPushScheduleReplaceResult,
)
from backend.shared_services.web_push_dispatch_store import (
    WebPushDispatchStorageNames,
    WebPushDispatchStore,
)
from backend.shared_services.web_push_delivery import WebPushDeliveryReport

FELIX_WEB_PUSH_DISPATCH_STORAGE = WebPushDispatchStorageNames(
    sql_table="felix_web_push_dispatch_jobs",
    mongo_collection="felix_web_push_dispatch_jobs",
    neo4j_label="FelixWebPushDispatchJob",
    neo4j_constraint="felix_web_push_dispatch_owner_key",
)

_MINIMUM_SCHEDULE_LEAD = timedelta(seconds=30)
_MAXIMUM_SCHEDULE_HORIZON = timedelta(days=8)
_DISPATCH_EXPIRY_GRACE = timedelta(days=1)
_MAXIMUM_SCHEDULE_OCCURRENCES = 60
_SAFE_SCHEDULE_KEY = re.compile(r"^[A-Za-z0-9._:%-]+$")


@dataclass(frozen=True)
class FelixWebPushScheduledOccurrence:
    """Represent one authorized predefined Felix occurrence.

    Attributes:
        schedule_key (str): Stable owner-scoped occurrence identity.
        kind (str): Backend-owned notification template key.
        due_at (datetime): Timezone-aware delivery time.
        locale (str): Supported product-copy locale.
    """

    schedule_key: str
    kind: str
    due_at: datetime
    locale: str = "de"


class FelixWebPushDispatchUnavailable(RuntimeError):
    """Signal that scheduled dispatch is deliberately disabled."""


class FelixWebPushDispatchService:
    """Validate account schedules and render fixed Felix dispatch commands."""

    def __init__(
        self,
        store: WebPushDispatchStore | None = None,
        *,
        web_push_service: FelixWebPushService | None = None,
        enabled_loader: Callable[[], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create a lazy provider-aware Felix dispatch service.

        Args:
            store (WebPushDispatchStore | None): Optional durable-store test
                override. Defaults to active-provider Felix storage.
            web_push_service (FelixWebPushService | None): Optional encrypted
                delivery override.
            enabled_loader (Callable[[], bool] | None): Deferred deployment
                enablement predicate.
            clock (Callable[[], datetime] | None): Optional UTC clock for tests.

        Returns:
            None.

        Side Effects:
            None. Provider and private-key resolution remain lazy.
        """
        self._store = store
        self._web_push_service = web_push_service or FelixWebPushService()
        self._enabled_loader = enabled_loader or _dispatch_enabled
        self._clock = clock or _utc_now

    @property
    def dispatch_enabled(self) -> bool:
        """Return whether this deployment accepts scheduled dispatch.

        Returns:
            bool: True only when explicit dispatch enablement is active.

        Side Effects:
            Reads deferred runtime configuration.
        """
        return bool(self._enabled_loader())

    async def replace_schedule(
        self,
        user_id: str,
        occurrences: Iterable[FelixWebPushScheduledOccurrence],
    ) -> WebPushScheduleReplaceResult:
        """Replace one authenticated account's rolling occurrence horizon.

        Args:
            user_id (str): Authenticated Felix account identifier.
            occurrences (Iterable[FelixWebPushScheduledOccurrence]): Complete
                desired predefined future horizon.

        Returns:
            WebPushScheduleReplaceResult: Stored and removed counts.

        Raises:
            FelixWebPushDispatchUnavailable: When deployment opt-in is absent.
            ValueError: When ownership, keys, kinds, locales, or times are
                invalid, duplicated, too soon, or beyond eight days.

        Side Effects:
            Replaces durable unleased jobs for the authenticated account.
        """
        if not self.dispatch_enabled:
            raise FelixWebPushDispatchUnavailable(
                "Scheduled Web Push dispatch is not enabled."
            )
        if not user_id.strip():
            raise ValueError("Felix Web Push schedule requires an account owner.")
        now = _aware_utc(self._clock(), field_name="dispatch clock")
        candidates = list(islice(occurrences, _MAXIMUM_SCHEDULE_OCCURRENCES + 1))
        if len(candidates) > _MAXIMUM_SCHEDULE_OCCURRENCES:
            raise ValueError("Felix Web Push schedule exceeds 60 occurrences.")
        normalized = [self._normalize_occurrence(item, now) for item in candidates]
        keys = [item.schedule_key for item in normalized]
        if len(keys) != len(set(keys)):
            raise ValueError("Felix Web Push schedule keys must be unique.")
        drafts = [self._draft(item) for item in normalized]
        return await self._dispatch_store().replace_user_schedule(
            user_id,
            drafts,
            now=now,
        )

    async def dispatch_command(
        self,
        user_id: str,
        command_payload: str,
    ) -> WebPushDeliveryReport:
        """Render and deliver one trusted persisted Felix command.

        Args:
            user_id (str): Internally authorized recipient account.
            command_payload (str): Stored fixed-kind/locale command JSON.

        Returns:
            WebPushDeliveryReport: Aggregate encrypted delivery result.

        Raises:
            ValueError: When persisted command structure is malformed.

        Side Effects:
            Performs encrypted account-scoped delivery and stale cleanup.
        """
        command = _parse_command(command_payload)
        message = _message_for(command["kind"], command["locale"])
        return await self._web_push_service.deliver(user_id, message)

    def _normalize_occurrence(
        self,
        occurrence: FelixWebPushScheduledOccurrence,
        now: datetime,
    ) -> FelixWebPushScheduledOccurrence:
        """Validate and UTC-normalize one desired occurrence.

        Args:
            occurrence (FelixWebPushScheduledOccurrence): Candidate occurrence.
            now (datetime): Current UTC time.

        Returns:
            FelixWebPushScheduledOccurrence: Validated UTC occurrence.

        Raises:
            ValueError: When identity, template, locale, or horizon is invalid.
        """
        due_at = _aware_utc(occurrence.due_at, field_name="dueAt")
        _message_for(occurrence.kind, occurrence.locale)
        if (
            not occurrence.schedule_key
            or len(occurrence.schedule_key) > 200
            or not _SAFE_SCHEDULE_KEY.fullmatch(occurrence.schedule_key)
        ):
            raise ValueError("Felix Web Push schedule key is invalid.")
        if due_at < now + _MINIMUM_SCHEDULE_LEAD:
            raise ValueError("Felix Web Push occurrence is too soon or in the past.")
        if due_at > now + _MAXIMUM_SCHEDULE_HORIZON:
            raise ValueError("Felix Web Push occurrence exceeds the rolling horizon.")
        return FelixWebPushScheduledOccurrence(
            schedule_key=occurrence.schedule_key,
            kind=occurrence.kind,
            due_at=due_at,
            locale=occurrence.locale,
        )

    def _draft(
        self,
        occurrence: FelixWebPushScheduledOccurrence,
    ) -> WebPushDispatchDraft:
        """Convert one validated occurrence to an opaque reusable draft.

        Args:
            occurrence (FelixWebPushScheduledOccurrence): Validated occurrence.

        Returns:
            WebPushDispatchDraft: Durable app-neutral job payload.
        """
        return WebPushDispatchDraft(
            schedule_key=occurrence.schedule_key,
            payload=json.dumps(
                {"kind": occurrence.kind, "locale": occurrence.locale},
                separators=(",", ":"),
            ),
            due_at=occurrence.due_at,
            expires_at=occurrence.due_at + _DISPATCH_EXPIRY_GRACE,
        )

    def _dispatch_store(self) -> WebPushDispatchStore:
        """Return the injected or lazily resolved durable store.

        Returns:
            WebPushDispatchStore: Active-provider dispatch storage.

        Side Effects:
            Resolves and caches the global database handler on first use.
        """
        if self._store is None:
            self._store = WebPushDispatchStore(FELIX_WEB_PUSH_DISPATCH_STORAGE)
        return self._store


def create_felix_web_push_background_service() -> WebPushDispatchBackgroundService:
    """Create the Felix-selected durable dispatch lifecycle service.

    Returns:
        WebPushDispatchBackgroundService: Explicitly enabled/disabled service.

    Side Effects:
        Reads non-secret worker configuration. Provider and VAPID configuration
        remain deferred until enabled startup.
    """
    return WebPushDispatchBackgroundService(
        "felix_web_push_dispatch",
        enabled=settings.WEB_PUSH_DISPATCH_ENABLED,
        poll_seconds=settings.WEB_PUSH_DISPATCH_POLL_SECONDS,
        worker_factory=_create_dispatch_worker,
    )


def _create_dispatch_worker() -> WebPushDispatchWorker:
    """Build an enabled provider/secret-aware Felix worker.

    Returns:
        WebPushDispatchWorker: Fully validated durable worker.

    Raises:
        ValueError: When VAPID or worker configuration is invalid.

    Side Effects:
        Resolves active provider storage and validates mounted-secret paths.
    """
    delivery_config = load_web_push_delivery_config()
    web_push_service = FelixWebPushService(
        delivery_config_loader=lambda: delivery_config,
    )
    dispatch_service = FelixWebPushDispatchService(
        web_push_service=web_push_service,
        enabled_loader=lambda: True,
    )
    policy = WebPushDispatchPolicy(
        batch_size=settings.WEB_PUSH_DISPATCH_BATCH_SIZE,
        lease_seconds=settings.WEB_PUSH_DISPATCH_LEASE_SECONDS,
        max_attempts=settings.WEB_PUSH_DISPATCH_MAX_ATTEMPTS,
        retry_base_seconds=settings.WEB_PUSH_DISPATCH_RETRY_BASE_SECONDS,
        retry_max_seconds=settings.WEB_PUSH_DISPATCH_RETRY_MAX_SECONDS,
    )
    return WebPushDispatchWorker(
        dispatch_service._dispatch_store(),
        dispatch_service.dispatch_command,
        policy,
    )


def _message_for(kind: str, locale: str) -> FelixWebPushMessage:
    """Render one fixed Felix notification template and route.

    Args:
        kind (str): Predefined product notification kind.
        locale (str): Supported ``de`` or ``en`` copy locale.

    Returns:
        FelixWebPushMessage: Validated visible notification.

    Raises:
        ValueError: When kind or locale is not explicitly supported.
    """
    templates = _MESSAGE_TEMPLATES.get(locale)
    if templates is None or kind not in templates:
        raise ValueError("Unsupported Felix Web Push kind or locale.")
    title, body, route = templates[kind]
    return FelixWebPushMessage(
        title=title,
        body=body,
        tag=f"felix-{kind}",
        route=route,
    )


def _parse_command(payload: str) -> dict[str, str]:
    """Parse one exact fixed-kind/locale persisted command.

    Args:
        payload (str): Opaque durable command JSON.

    Returns:
        dict[str, str]: Exact ``kind`` and ``locale`` values.

    Raises:
        ValueError: When JSON, keys, or values violate app policy.
    """
    try:
        value = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("Malformed Felix Web Push dispatch command.") from exc
    if not isinstance(value, dict) or set(value) != {"kind", "locale"}:
        raise ValueError("Malformed Felix Web Push dispatch command.")
    kind = value.get("kind")
    locale = value.get("locale")
    if not isinstance(kind, str) or not isinstance(locale, str):
        raise ValueError("Malformed Felix Web Push dispatch command.")
    _message_for(kind, locale)
    return {"kind": kind, "locale": locale}


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    """Normalize one timezone-aware datetime to UTC.

    Args:
        value (datetime): Candidate timestamp.
        field_name (str): Safe validation label.

    Returns:
        datetime: UTC-normalized timestamp.

    Raises:
        ValueError: When timezone information is absent.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _dispatch_enabled() -> bool:
    """Return explicit scheduled-dispatch deployment enablement.

    Returns:
        bool: Current runtime setting.
    """
    return settings.WEB_PUSH_DISPATCH_ENABLED


def _utc_now() -> datetime:
    """Return current timezone-aware UTC time.

    Returns:
        datetime: Current UTC timestamp.
    """
    return datetime.now(timezone.utc)


#
# Backend-owned notification templates.
# Callers schedule only a kind/locale pair so visible content and navigation
# cannot be converted into an arbitrary authenticated message-send surface.
#
_MESSAGE_TEMPLATES: dict[str, dict[str, tuple[str, str, str]]] = {
    "de": {
        "checkin": (
            "Zeit für deinen Check-in",
            "Wie geht es dir gerade? Nimm dir einen kurzen Moment.",
            "/wellness/check-in",
        ),
        "activity": (
            "Zeit für eine Aktivität",
            "Eine kleine hilfreiche Aktivität kann jetzt gut tun.",
            "/activities",
        ),
        "breathing": (
            "Kurze Atempause",
            "Nimm dir einen ruhigen Moment für deine Atmung.",
            "/wellness/breathing",
        ),
        "mindfulness": (
            "Achtsamkeitsimpuls",
            "Komm für einen Moment bewusst im Hier und Jetzt an.",
            "/wellness/mindfulness",
        ),
        "selfcare": (
            "Selbstfürsorge-Impuls",
            "Was würde dir gerade freundlich und wirklich helfen?",
            "/wellness/self-care",
        ),
        "motivation": (
            "Motivationsimpuls",
            "Ein kleiner nächster Schritt reicht für heute.",
            "/wellness/motivation",
        ),
        "gratitude": (
            "Dankbarkeitsimpuls",
            "Was war heute ein kleiner guter Moment?",
            "/wellness/gratitude",
        ),
    },
    "en": {
        "checkin": (
            "Time for your check-in",
            "How are you feeling right now? Take a brief moment.",
            "/wellness/check-in",
        ),
        "activity": (
            "Time for an activity",
            "A small supportive activity may help right now.",
            "/activities",
        ),
        "breathing": (
            "A brief breathing pause",
            "Take a calm moment to focus on your breathing.",
            "/wellness/breathing",
        ),
        "mindfulness": (
            "Mindfulness prompt",
            "Take a moment to arrive consciously in the present.",
            "/wellness/mindfulness",
        ),
        "selfcare": (
            "Self-care prompt",
            "What would feel kind and genuinely helpful right now?",
            "/wellness/self-care",
        ),
        "motivation": (
            "Motivation prompt",
            "One small next step is enough for today.",
            "/wellness/motivation",
        ),
        "gratitude": (
            "Gratitude prompt",
            "What was one small good moment today?",
            "/wellness/gratitude",
        ),
    },
}
