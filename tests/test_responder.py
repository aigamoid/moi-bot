import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord.http import Ratelimit

from bot.main import create_client
from bot.responder import Admission, Limits, MoiResponder


def message(user=1, channel=1, content="もい", bot=False):
    return SimpleNamespace(
        id=user,
        author=SimpleNamespace(id=user, bot=bot),
        channel=SimpleNamespace(id=channel),
        content=content,
        reply=AsyncMock(),
        add_reaction=AsyncMock(),
    )


def http_error(cls, status, code):
    return cls(SimpleNamespace(status=status, reason="test error"),
               {"code": code, "message": "offline failure"})


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.gate = Admission(Limits(max_in_flight=2, max_tracked_ids=2),
                              clock=lambda: self.now)

    def test_user_and_channel_cooldowns_apply_independently(self):
        self.assertTrue(self.gate.try_acquire(1, 1))
        self.gate.release()
        self.assertFalse(self.gate.try_acquire(1, 2))
        self.assertFalse(self.gate.try_acquire(2, 1))
        self.now = 2.0
        self.assertTrue(self.gate.try_acquire(2, 1))
        self.gate.release()
        self.assertFalse(self.gate.try_acquire(1, 2))
        self.now = 10.0
        self.assertTrue(self.gate.try_acquire(1, 2))

    def test_full_capacity_rejects_without_recording_new_ids(self):
        self.assertTrue(self.gate.try_acquire(1, 1))
        self.assertTrue(self.gate.try_acquire(2, 2))
        for number in range(3, 1003):
            self.assertFalse(self.gate.try_acquire(number, number))
        self.assertEqual(self.gate.in_flight, 2)
        self.assertEqual(len(self.gate.users), 2)
        self.assertEqual(len(self.gate.channels), 2)

    def test_cooldown_storage_is_bounded_and_recovers_at_expiry(self):
        for number in (1, 2):
            self.assertTrue(self.gate.try_acquire(number, number))
            self.gate.release()
        for number in range(3, 1003):
            self.assertFalse(self.gate.try_acquire(number, number))
        self.assertEqual(len(self.gate.users), 2)
        self.assertEqual(len(self.gate.channels), 2)
        self.now = 10.0
        self.assertTrue(self.gate.try_acquire(3, 3))
        self.assertEqual(list(self.gate.users), [3])
        self.assertEqual(list(self.gate.channels), [3])

    def test_limits_reject_unbounded_or_disabled_values(self):
        for setting in ({"max_in_flight": 0}, {"max_tracked_ids": -1},
                        {"action_timeout": float("inf")},
                        {"user_cooldown": float("nan")},
                        {"channel_cooldown": 0}):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                Limits(**setting)


class ResponderTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_substring_replies_and_reacts(self):
        target = message(content="今日もいい天気")
        responder = MoiResponder()
        await responder.on_message(target)
        target.reply.assert_awaited_once_with("もい")
        target.add_reaction.assert_awaited_once_with("🦆")
        self.assertEqual(responder.admission.in_flight, 0)

    async def test_bot_and_non_matching_messages_do_not_consume_admission(self):
        responder = MoiResponder()
        for target in (message(bot=True), message(content="こんにちは"), message(content="")):
            await responder.on_message(target)
            target.reply.assert_not_awaited()
            target.add_reaction.assert_not_awaited()
        self.assertFalse(responder.admission.users)
        await responder.on_message(message())
        self.assertEqual(len(responder.admission.users), 1)

    async def test_reply_failure_still_reacts_and_next_message_succeeds(self):
        errors = [http_error(discord.Forbidden, 403, 50013),
                  http_error(discord.HTTPException, 500, 0),
                  discord.RateLimited(60)]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                responder = MoiResponder()
                target = message()
                target.reply.side_effect = error
                with self.assertLogs("bot.responder", level="WARNING"):
                    await responder.on_message(target)
                target.add_reaction.assert_awaited_once_with("🦆")
                self.assertEqual(responder.admission.in_flight, 0)
                next_target = message(2, 2)
                await responder.on_message(next_target)
                next_target.reply.assert_awaited_once()
                next_target.add_reaction.assert_awaited_once()

    async def test_reaction_failure_and_both_failures_release_slot(self):
        for reply_fails in (False, True):
            for error in (http_error(discord.Forbidden, 403, 50013),
                          http_error(discord.NotFound, 404, 10008),
                          http_error(discord.HTTPException, 500, 0)):
                with self.subTest(reply_fails=reply_fails, error=type(error).__name__):
                    responder = MoiResponder()
                    target = message()
                    if reply_fails:
                        target.reply.side_effect = http_error(discord.Forbidden, 403, 50013)
                    target.add_reaction.side_effect = error
                    with self.assertLogs("bot.responder", level="INFO"):
                        await responder.on_message(target)
                    target.reply.assert_awaited_once()
                    target.add_reaction.assert_awaited_once()
                    self.assertEqual(responder.admission.in_flight, 0)
                    next_target = message(2, 2)
                    await responder.on_message(next_target)
                    next_target.add_reaction.assert_awaited_once()

    async def test_deleted_target_skips_reaction_and_releases_slot(self):
        responder = MoiResponder()
        target = message()
        target.reply.side_effect = http_error(discord.NotFound, 404, 10008)
        with self.assertLogs("bot.responder", level="INFO"):
            await responder.on_message(target)
        target.add_reaction.assert_not_awaited()
        self.assertEqual(responder.admission.in_flight, 0)
        next_target = message(2, 2)
        await responder.on_message(next_target)
        next_target.reply.assert_awaited_once()

    async def test_stalled_reply_times_out_then_reacts(self):
        responder = MoiResponder(Limits(action_timeout=0.01))
        target = message()

        async def stall(*args):
            await asyncio.Event().wait()

        target.reply.side_effect = stall
        with self.assertLogs("bot.responder", level="WARNING"):
            await asyncio.wait_for(responder.on_message(target), 1.0)
        target.add_reaction.assert_awaited_once()
        self.assertEqual(responder.admission.in_flight, 0)

    async def test_both_stalled_actions_release_capacity_after_deadlines(self):
        responder = MoiResponder(Limits(max_in_flight=1, action_timeout=0.01))
        target = message()

        async def stall(*args):
            await asyncio.Event().wait()

        target.reply.side_effect = stall
        target.add_reaction.side_effect = stall
        with self.assertLogs("bot.responder", level="WARNING"):
            await asyncio.wait_for(responder.on_message(target), 1.0)
        self.assertEqual(responder.admission.in_flight, 0)
        next_target = message(2, 2)
        await responder.on_message(next_target)
        next_target.reply.assert_awaited_once()

    async def test_cancellation_releases_capacity_without_reacting(self):
        responder = MoiResponder(Limits(max_in_flight=1))
        target = message()
        started = asyncio.Event()

        async def stall(*args):
            started.set()
            await asyncio.Event().wait()

        target.reply.side_effect = stall
        task = asyncio.create_task(responder.on_message(target))
        await started.wait()
        self.assertEqual(responder.admission.in_flight, 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        target.add_reaction.assert_not_awaited()
        self.assertEqual(responder.admission.in_flight, 0)
        next_target = message(2, 2)
        await responder.on_message(next_target)
        next_target.reply.assert_awaited_once()

    async def test_unexpected_exception_also_releases_capacity(self):
        responder = MoiResponder(Limits(max_in_flight=1))
        target = message()
        target.reply.side_effect = RuntimeError("unexpected test failure")
        with self.assertRaises(RuntimeError):
            await responder.on_message(target)
        self.assertEqual(responder.admission.in_flight, 0)
        next_target = message(2, 2)
        await responder.on_message(next_target)
        next_target.reply.assert_awaited_once()

    async def test_real_sdk_dispatch_and_rate_limit_wait_are_bounded(self):
        responder = MoiResponder(Limits(max_in_flight=3))
        client = create_client(responder)
        # No login or HTTP session: exercise the pinned SDK's event scheduler.
        await client._async_setup_hook()
        rate = Ratelimit(30)
        rate.remaining = 0
        rate.expires = asyncio.get_running_loop().time() + 5
        rate.reset_after = 5
        targets = [message(number, number) for number in range(200)]

        async def wait_for_rate_limit(*args):
            await rate.acquire()

        for target in targets:
            target.reply.side_effect = wait_for_rate_limit
            client.dispatch("message", target)
        await asyncio.sleep(0)
        handlers = [task for task in asyncio.all_tasks()
                    if task.get_name() == "discord.py: on_message" and not task.done()]
        try:
            self.assertEqual(len(handlers), 3)
            self.assertEqual(responder.admission.in_flight, 3)
            self.assertEqual(sum(target.reply.await_count for target in targets), 3)
            self.assertEqual(len(rate._pending_requests), 3)
            self.assertEqual(len(responder.admission.users), 3)
        finally:
            for task in handlers:
                task.cancel()
            await asyncio.gather(*handlers, return_exceptions=True)
            await client.close()
        self.assertEqual(responder.admission.in_flight, 0)

    async def test_same_channel_burst_is_dropped_without_waiters(self):
        responder = MoiResponder()
        targets = [message(number, 1) for number in range(200)]
        await asyncio.gather(*(responder.on_message(target) for target in targets))
        self.assertEqual(sum(target.reply.await_count for target in targets), 1)
        self.assertEqual(sum(target.add_reaction.await_count for target in targets), 1)
        self.assertEqual(responder.admission.in_flight, 0)


if __name__ == "__main__":
    unittest.main()
