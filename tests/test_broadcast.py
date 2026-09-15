import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.api import admin as api
from app.clients import psql
from app.core.config import LINE_PUSH_URL
from app.schemas.broadcast import BroadcastCreate
from app.schemas.system_config import SystemConfig
from app.schemas.turn import Turn
from app.services import broadcast as service


NO_SESSION = (None, [])


def talking(session_id):
    return (session_id, [Turn(role="user", content_type="text", content="น้ำท่วม")])


class BroadcastValidationTests(IsolatedAsyncioTestCase):
    def test_line_utf16_limit_counts_non_bmp_characters_as_two(self):
        BroadcastCreate(text="😀" * 2500, audience="all")
        with self.assertRaises(ValidationError):
            BroadcastCreate(text="😀" * 2501, audience="all")

    def test_selected_requires_users_and_all_rejects_users(self):
        with self.assertRaises(ValidationError):
            BroadcastCreate(text="hello", audience="selected")
        with self.assertRaises(ValidationError):
            BroadcastCreate(text="hello", audience="all", user_ids=[uuid4()])


class BroadcastDispatchTests(IsolatedAsyncioTestCase):
    async def test_dispatch_claims_each_recipient_and_records_results(self):
        broadcast_id = uuid4()
        first = {"id": uuid4(), "user_id": uuid4(), "line_user_id": "U1", "retry_key": uuid4()}
        second = {"id": uuid4(), "user_id": uuid4(), "line_user_id": "U2", "retry_key": uuid4()}
        with (
            patch.object(service.psql, "get_broadcast", new=AsyncMock(return_value={
                "id": broadcast_id, "status": "sending", "text": "notice"
            })),
            patch.object(
                service.psql, "claim_broadcast_recipient",
                new=AsyncMock(side_effect=[first, second, None]),
            ),
            patch.object(
                service.chatbot, "load_session_from_redis", new=AsyncMock(return_value=NO_SESSION)
            ),
            patch.object(service.line, "push", new=AsyncMock(side_effect=[200, 400])) as push,
            patch.object(service.psql, "finish_broadcast_recipient", new=AsyncMock()) as finish,
            patch.object(service.psql, "complete_broadcast", new=AsyncMock()) as complete,
        ):
            await service.dispatch(broadcast_id)
        self.assertEqual(push.await_args_list[0].args, ("U1", ["notice"], first["retry_key"]))
        self.assertEqual(finish.await_args_list[0].args, (first["id"], "sent"))
        self.assertEqual(finish.await_args_list[0].kwargs, {"response_status": 200})
        self.assertEqual(finish.await_args_list[1].args, (second["id"], "failed"))
        complete.assert_awaited_once_with(broadcast_id)

    async def test_transport_timeout_is_unknown_and_not_retried(self):
        broadcast_id = uuid4()
        delivery = {"id": uuid4(), "user_id": uuid4(), "line_user_id": "U1", "retry_key": uuid4()}
        request = httpx.Request("POST", LINE_PUSH_URL)
        with (
            patch.object(service.psql, "get_broadcast", new=AsyncMock(return_value={
                "id": broadcast_id, "status": "sending", "text": "notice"
            })),
            patch.object(
                service.psql, "claim_broadcast_recipient",
                new=AsyncMock(side_effect=[delivery, None]),
            ) as claim,
            patch.object(
                service.chatbot, "load_session_from_redis", new=AsyncMock(return_value=NO_SESSION)
            ),
            patch.object(
                service.line, "push",
                new=AsyncMock(side_effect=httpx.ReadTimeout("late", request=request)),
            ),
            patch.object(service.psql, "finish_broadcast_recipient", new=AsyncMock()) as finish,
            patch.object(service.psql, "complete_broadcast", new=AsyncMock()),
        ):
            await service.dispatch(broadcast_id)
        self.assertEqual(claim.await_count, 2)
        finish.assert_awaited_once_with(delivery["id"], "unknown", error="ReadTimeout")

    def two_recipients(self):
        return (
            {"id": uuid4(), "user_id": uuid4(), "line_user_id": "U1", "retry_key": uuid4()},
            {"id": uuid4(), "user_id": uuid4(), "line_user_id": "U2", "retry_key": uuid4()},
        )

    def dispatching(self, broadcast_id, recipients, sessions):
        return (
            patch.object(service.psql, "get_broadcast", new=AsyncMock(return_value={
                "id": broadcast_id, "status": "sending", "text": "notice"
            })),
            patch.object(
                service.psql, "claim_broadcast_recipient",
                new=AsyncMock(side_effect=[*recipients, None]),
            ),
            patch.object(
                service.chatbot, "load_session_from_redis", new=AsyncMock(side_effect=sessions)
            ),
        )

    async def test_recipient_who_already_spoke_is_skipped_not_pushed(self):
        broadcast_id = uuid4()
        busy, quiet = self.two_recipients()
        get_broadcast, claim, load = self.dispatching(
            broadcast_id, [busy, quiet], [talking(uuid4()), NO_SESSION]
        )
        with (
            get_broadcast, claim, load as session_lookup,
            patch.object(service.line, "push", new=AsyncMock(return_value=200)) as push,
            patch.object(service.psql, "finish_broadcast_recipient", new=AsyncMock()) as finish,
            patch.object(service.psql, "complete_broadcast", new=AsyncMock()) as complete,
        ):
            await service.dispatch(broadcast_id)

        self.assertEqual(session_lookup.await_args_list[0].args, (f"session:{busy['user_id']}",))
        push.assert_awaited_once()
        self.assertEqual(push.await_args.args[0], "U2")
        self.assertEqual(finish.await_args_list[0].args, (busy["id"], "skipped"))
        self.assertEqual(finish.await_args_list[1].args, (quiet["id"], "sent"))
        complete.assert_awaited_once_with(broadcast_id)

    async def test_open_session_without_a_user_turn_is_not_treated_as_talking(self):
        broadcast_id = uuid4()
        sticker_only = {"id": uuid4(), "user_id": uuid4(), "line_user_id": "U1", "retry_key": uuid4()}
        session_id = uuid4()
        get_broadcast, claim, load = self.dispatching(
            broadcast_id, [sticker_only], [(session_id, [])]
        )
        with (
            get_broadcast, claim, load,
            patch.object(service.line, "push", new=AsyncMock(return_value=200)) as push,
            patch.object(service.chatbot, "save_session_to_redis", new=AsyncMock()),
            patch.object(service.psql, "finish_broadcast_recipient", new=AsyncMock()) as finish,
            patch.object(service.psql, "complete_broadcast", new=AsyncMock()),
        ):
            await service.dispatch(broadcast_id)

        push.assert_awaited_once()
        self.assertEqual(finish.await_args.args, (sticker_only["id"], "sent"))

    async def test_force_send_pushes_over_a_live_chat_and_appends_the_text_to_it(self):
        broadcast_id = uuid4()
        busy, _ = self.two_recipients()
        session_id = uuid4()
        get_broadcast, claim, load = self.dispatching(
            broadcast_id, [busy], [talking(session_id)]
        )
        with (
            get_broadcast, claim, load,
            patch.object(service.line, "push", new=AsyncMock(return_value=200)) as push,
            patch.object(service.chatbot, "save_session_to_redis", new=AsyncMock()) as save,
            patch.object(service.psql, "finish_broadcast_recipient", new=AsyncMock()) as finish,
            patch.object(service.psql, "complete_broadcast", new=AsyncMock()),
        ):
            await service.dispatch(broadcast_id, force_send=True)

        push.assert_awaited_once()
        self.assertEqual(finish.await_args.args, (busy["id"], "sent"))
        key, saved_session_id, turns = save.await_args.args
        self.assertEqual((key, saved_session_id), (f"session:{busy['user_id']}", session_id))
        self.assertEqual([turn.role for turn in turns], ["user", "assistant"])
        self.assertEqual(turns[-1].content, "notice")

    async def test_failed_force_push_does_not_touch_the_live_chat(self):
        broadcast_id = uuid4()
        busy, _ = self.two_recipients()
        get_broadcast, claim, load = self.dispatching(
            broadcast_id, [busy], [talking(uuid4())]
        )
        with (
            get_broadcast, claim, load,
            patch.object(service.line, "push", new=AsyncMock(return_value=400)),
            patch.object(service.chatbot, "save_session_to_redis", new=AsyncMock()) as save,
            patch.object(service.psql, "finish_broadcast_recipient", new=AsyncMock()) as finish,
            patch.object(service.psql, "complete_broadcast", new=AsyncMock()),
        ):
            await service.dispatch(broadcast_id, force_send=True)

        self.assertEqual(finish.await_args.args, (busy["id"], "failed"))
        save.assert_not_awaited()

    async def test_dispatch_does_nothing_for_an_already_completed_broadcast(self):
        broadcast_id = uuid4()
        with (
            patch.object(service.psql, "get_broadcast", new=AsyncMock(return_value={
                "id": broadcast_id, "status": "completed", "text": "notice"
            })),
            patch.object(service.psql, "claim_broadcast_recipient", new=AsyncMock()) as claim,
            patch.object(service.line, "push", new=AsyncMock()) as push,
        ):
            await service.dispatch(broadcast_id)
        claim.assert_not_awaited()
        push.assert_not_awaited()


class BroadcastSendTests(IsolatedAsyncioTestCase):
    async def test_send_writes_the_record_then_dispatches_in_the_background(self):
        broadcast_id = uuid4()
        record = {"id": broadcast_id, "status": "sending"}
        with (
            patch.object(
                service.psql, "save_broadcast", new=AsyncMock(return_value=broadcast_id)
            ) as save,
            patch.object(service.psql, "get_broadcast", new=AsyncMock(return_value=record)),
            patch.object(service, "dispatch", new=AsyncMock()) as dispatch,
        ):
            result = await service.send("notice", "all", [], force_send=True)
            await asyncio.gather(*service._running)

        save.assert_awaited_once_with("notice", "all", [])
        dispatch.assert_awaited_once_with(broadcast_id, True)
        self.assertEqual(result, record)

    async def test_send_validates_before_touching_the_database(self):
        with (
            patch.object(service.psql, "save_broadcast", new=AsyncMock()) as save,
            patch.object(service, "dispatch", new=AsyncMock()) as dispatch,
        ):
            with self.assertRaises(ValidationError):
                await service.send("", "invalid", [uuid4()])
        save.assert_not_awaited()
        dispatch.assert_not_awaited()


class BroadcastSelectionTests(IsolatedAsyncioTestCase):
    def pool_with(self, connection):
        transaction = MagicMock()
        transaction.__aenter__.return_value = transaction
        connection.transaction = MagicMock(return_value=transaction)
        acquire = MagicMock()
        acquire.__aenter__.return_value = connection
        pool = MagicMock()
        pool.acquire.return_value = acquire
        return pool, transaction

    async def test_selected_audience_queries_only_requested_internal_ids(self):
        user_id = uuid4()
        connection = AsyncMock()
        connection.fetch.return_value = [{"id": user_id, "line_user_id": "U1"}]
        pool, _ = self.pool_with(connection)
        with patch.object(psql, "get_pool", return_value=pool):
            await psql.save_broadcast("notice", "selected", [user_id])
        query, selected_ids = connection.fetch.await_args.args
        self.assertIn("id = ANY", query)
        self.assertEqual(selected_ids, [user_id])
        inserted = connection.executemany.await_args.args[1]
        self.assertEqual(inserted[0][2:4], (user_id, "U1"))

    async def test_unknown_selected_user_rolls_back_draft(self):
        missing_id = uuid4()
        connection = AsyncMock()
        connection.fetch.return_value = []
        pool, transaction = self.pool_with(connection)
        with (
            patch.object(psql, "get_pool", return_value=pool),
            self.assertRaises(psql.UnknownBroadcastUsersError) as raised,
        ):
            await psql.save_broadcast("notice", "selected", [missing_id])
        self.assertEqual(raised.exception.user_ids, [missing_id])
        transaction.__aexit__.assert_awaited_once()
        self.assertIs(transaction.__aexit__.await_args.args[0], psql.UnknownBroadcastUsersError)


class BroadcastApiTests(IsolatedAsyncioTestCase):
    async def test_unknown_selected_user_becomes_422_with_the_offending_ids(self):
        missing_id = uuid4()
        with patch.object(
            api.service, "send",
            new=AsyncMock(side_effect=psql.UnknownBroadcastUsersError([missing_id])),
        ):
            with self.assertRaises(api.HTTPException) as raised:
                await api.create_broadcast(
                    BroadcastCreate(text="notice", audience="selected", user_ids=[missing_id])
                )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.detail["user_ids"], [str(missing_id)])

    async def test_force_send_reaches_the_service(self):
        payload = BroadcastCreate(text="notice", audience="all")
        with patch.object(api.service, "send", new=AsyncMock(return_value={})) as send:
            await api.create_broadcast(payload, force_send=True)
        send.assert_awaited_once_with("notice", "all", [], True)

    async def test_history_passes_pagination_and_preserves_total(self):
        with patch.object(api.psql, "get_broadcasts", new=AsyncMock(return_value=([], 321))) as listing:
            result = await api.get_broadcasts(limit=100, offset=200)
        listing.assert_awaited_once_with(100, 200)
        self.assertEqual(result, {"items": [], "total": 321})

    async def test_system_config_endpoint_returns_the_running_config(self):
        running = SystemConfig(note="รอบปัจจุบัน")
        with patch.object(api.system_config, "get", return_value=running):
            self.assertIs(await api.get_system_config(), running)
