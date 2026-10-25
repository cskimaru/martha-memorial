"""Reconciler: settles payments whose callback never arrived or was not yet verified.

Run as its own container: python -m app.worker
"""

import asyncio
import logging
import signal
import time
from datetime import timedelta
from pathlib import Path

from prometheus_client import Gauge, start_http_server
from sqlalchemy import and_, func, or_, select

from memorial_common.db import Database, utcnow
from memorial_common.logging import configure_logging

from .config import Settings, get_settings
from .daraja import DarajaClient
from .models import Contribution
from .verify import verify_contribution

log = logging.getLogger("reconciler")
HEARTBEAT = Path("/tmp/reconciler-heartbeat")  # noqa: S108

open_gauge = Gauge("contributions_open", "Unsettled contributions", ["status"])
stale_gauge = Gauge("contributions_stale_open", "Contributions unsettled for longer than the timeout")
confirmed_gauge = Gauge("contributions_confirmed_kes", "Total confirmed contributions in KES")
mismatch_gauge = Gauge("contributions_mismatch", "Payments whose amount differs from the request")
last_run = Gauge("contributions_reconciler_last_run_timestamp", "Unix time of the last reconciler pass")


async def run_once(db: Database, daraja: DarajaClient, settings: Settings, batch: int = 25) -> int:
    now = utcnow()
    q = (
        select(Contribution)
        .where(
            Contribution.method == "mpesa_stk",
            Contribution.created_at < now - timedelta(seconds=45),
            or_(
                Contribution.status.in_(("pending", "verifying")),
                and_(
                    Contribution.status == "expired",
                    Contribution.checkout_request_id.is_not(None),
                    Contribution.created_at > now - timedelta(days=1),
                    or_(
                        Contribution.last_checked_at.is_(None),
                        Contribution.last_checked_at < now - timedelta(minutes=10),
                    ),
                ),
            ),
        )
        .order_by(Contribution.last_checked_at.nulls_first())
        .limit(batch)
        .with_for_update(skip_locked=True)
    )
    async with db.sessionmaker() as s:
        rows = list((await s.execute(q)).scalars())
        for c in rows:
            await verify_contribution(s, daraja, settings, c, "reconciler")
        await s.commit()
    await update_gauges(db, settings)
    return len(rows)


async def update_gauges(db: Database, settings: Settings) -> None:
    now = utcnow()
    async with db.sessionmaker() as s:
        counts = dict(
            (
                await s.execute(
                    select(Contribution.status, func.count())
                    .where(Contribution.status.in_(("pending", "verifying")))
                    .group_by(Contribution.status)
                )
            ).all()
        )
        for st in ("pending", "verifying"):
            open_gauge.labels(st).set(counts.get(st, 0))
        stale = (
            await s.execute(
                select(func.count()).where(
                    Contribution.status.in_(("pending", "verifying")),
                    Contribution.created_at < now - timedelta(minutes=settings.pending_timeout_minutes + 5),
                )
            )
        ).scalar_one()
        stale_gauge.set(stale)
        total = (
            await s.execute(
                select(func.coalesce(func.sum(Contribution.amount_received), 0)).where(
                    Contribution.status == "confirmed"
                )
            )
        ).scalar_one()
        confirmed_gauge.set(int(total))
        mismatch_gauge.set(
            (await s.execute(select(func.count()).where(Contribution.status == "mismatch"))).scalar_one()
        )
    last_run.set(time.time())


async def main(interval: float = 30.0) -> None:
    settings = get_settings()
    configure_logging("contributions-reconciler", settings.log_level)
    start_http_server(9100)
    db = Database(settings.database_url)
    daraja = DarajaClient(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    log.info("Reconciler started")
    while not stop.is_set():
        try:
            if settings.mpesa_enabled:
                n = await run_once(db, daraja, settings)
                if n:
                    log.info("Checked contributions", extra={"fields": {"count": n}})
            else:
                await update_gauges(db, settings)
            await asyncio.to_thread(HEARTBEAT.write_text, str(time.time()))
        except Exception:
            log.exception("Reconciler pass failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
    await daraja.close()
    await db.dispose()
    log.info("Reconciler stopped")


if __name__ == "__main__":
    asyncio.run(main())
