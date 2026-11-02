"""Bound the work admitted from message events before any Discord API wait."""

import asyncio
import logging
import math
import time
from collections import OrderedDict
from dataclasses import dataclass

import discord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Limits:
    max_in_flight: int = 8
    user_cooldown: float = 10.0
    channel_cooldown: float = 2.0
    action_timeout: float = 10.0
    max_tracked_ids: int = 4096

    def __post_init__(self):
        for name in ("max_in_flight", "max_tracked_ids"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("user_cooldown", "channel_cooldown", "action_timeout"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


class Admission:
    """Synchronous admission on the client's single event loop; no waiter queue."""

    def __init__(self, limits, clock=time.monotonic):
        self.limits = limits
        self.clock = clock
        self.in_flight = 0
        self.users = OrderedDict()
        self.channels = OrderedDict()

    @staticmethod
    def _expire(entries, now):
        # Fixed cooldowns make insertion order the same as expiry order.
        while entries and next(iter(entries.values())) <= now:
            entries.popitem(last=False)

    def try_acquire(self, user_id, channel_id):
        now = self.clock()
        self._expire(self.users, now)
        self._expire(self.channels, now)
        if self.in_flight >= self.limits.max_in_flight:
            return False
        if user_id in self.users or channel_id in self.channels:
            return False
        if (len(self.users) >= self.limits.max_tracked_ids or
                len(self.channels) >= self.limits.max_tracked_ids):
            # Do not evict an active cooldown to admit more identities.
            return False
        self.users[user_id] = now + self.limits.user_cooldown
        self.channels[channel_id] = now + self.limits.channel_cooldown
        self.in_flight += 1
        return True

    def release(self):
        self.in_flight -= 1


class MoiResponder:
    def __init__(self, limits=None, clock=time.monotonic):
        self.limits = limits if limits is not None else Limits()
        self.admission = Admission(self.limits, clock)

    async def _try_action(self, action, message, operation):
        """Return False only when the target no longer exists."""
        try:
            async with asyncio.timeout(self.limits.action_timeout):
                await operation()
        except discord.NotFound:
            logger.info("%s skipped: target missing (message=%s)", action, message.id)
            return False
        except discord.Forbidden:
            logger.warning("%s forbidden (message=%s, channel=%s)",
                           action, message.id, message.channel.id)
        except discord.HTTPException as error:
            logger.warning("%s HTTP failure (message=%s, status=%s, code=%s)",
                           action, message.id, error.status, error.code)
        except discord.RateLimited:
            logger.warning("%s skipped: excessive rate-limit wait (message=%s)",
                           action, message.id)
        except TimeoutError:
            logger.warning("%s timed out (message=%s)", action, message.id)
        return True

    async def on_message(self, message):
        if message.author.bot or "もい" not in message.content:
            return
        # No await before this decision: rejected messages never wait for a slot.
        if not self.admission.try_acquire(message.author.id, message.channel.id):
            return
        try:
            exists = await self._try_action("reply", message, lambda: message.reply("もい"))
            if exists:
                await self._try_action("reaction", message,
                                       lambda: message.add_reaction("🦆"))
        finally:
            # Covers API errors, timeouts, unexpected exceptions, and shutdown.
            self.admission.release()
