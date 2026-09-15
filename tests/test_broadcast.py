from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.clients import broadcast as client
from app.api import broadcast as api
from app.schemas.broadcast import BroadcastCreate
from app.services import broadcast as service


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
        first = {"id": uuid4(), "line_user_id": "U1", "retry_key": uuid4()}
        second = {"id": uuid4(), "line_user_id": "U2", "retry_key": uuid4()}
        with (
            patch.object(client, "fetch_broadcast", new=AsyncMock(return_value={
                "id": broadcast_id, "status": "sending", "text": "notice"
            })),
            patch.object(client, "claim_recipient", new=AsyncMock(side_effect=[first, second, None])),
            patch.object(client, "push_text", new=AsyncMock(side_effect=[200, 400])),
            patch.object(client, "finish_recipient", new=AsyncMock()) as finish,
            patch.object(client, "complete_broadcast", new=AsyncMock()) as complete,
        ):
            await service.dispatch(broadcast_id)
        self.assertEqual(finish.await_args_list[0].args, (first["id"], "sent"))
        self.assertEqual(finish.await_args_list[0].kwargs, {"response_status": 200})
        self.assertEqual(finish.await_args_list[1].args, (second["id"], "failed"))
        complete.assert_awaited_once_with(broadcast_id)

    async def test_transport_timeout_is_unknown_and_not_retried(self):
        broadcast_id = uuid4()
        delivery = {"id": uuid4(), "line_user_id": "U1", "retry_key": uuid4()}
        request = httpx.Request("POST", client.LINE_PUSH_URL)
        with (
            patch.object(client, "fetch_broadcast", new=AsyncMock(return_value={
                "id": broadcast_id, "status": "sending", "text": "notice"
            })),
            patch.object(client, "claim_recipient", new=AsyncMock(side_effect=[delivery, None])) as claim,
            patch.object(client, "push_text", new=AsyncMock(side_effect=httpx.ReadTimeout("late", request=request))),
            patch.object(client, "finish_recipient", new=AsyncMock()) as finish,
            patch.object(client, "complete_broadcast", new=AsyncMock()),
        ):
            await service.dispatch(broadcast_id)
        self.assertEqual(claim.await_count, 2)
        finish.assert_awaited_once_with(delivery["id"], "unknown", error="ReadTimeout")

    async def test_send_can_only_be_claimed_once(self):
        broadcast_id = uuid4()
        draft = {"id": broadcast_id, "status": "draft"}
        sending = {"id": broadcast_id, "status": "sending"}
        with (
            patch.object(client, "fetch_broadcast", new=AsyncMock(side_effect=[draft, sending])),
            patch.object(client, "begin_send", new=AsyncMock(return_value=True)),
        ):
            item, accepted = await service.request_send(broadcast_id)
        self.assertTrue(accepted)
        self.assertEqual(item["status"], "sending")

    async def test_disabled_auto_hook_does_not_validate_write_or_send(self):
        with (
            patch.object(client, "get_auto_enabled", new=AsyncMock(return_value=False)),
            patch.object(client, "create_draft", new=AsyncMock()) as create,
            patch.object(client, "push_text", new=AsyncMock()) as push,
        ):
            result = await service.dispatch_auto("", "invalid", [uuid4()])
        self.assertIsNone(result)
        create.assert_not_awaited()
        push.assert_not_awaited()

    async def test_enabled_auto_hook_uses_durable_shared_pipeline(self):
        broadcast_id = uuid4()
        completed = {"id": broadcast_id, "status": "completed"}
        with (
            patch.object(client, "get_auto_enabled", new=AsyncMock(return_value=True)),
            patch.object(client, "create_draft", new=AsyncMock(return_value=broadcast_id)) as create,
            patch.object(client, "begin_send", new=AsyncMock(return_value=True)) as begin,
            patch.object(service, "dispatch", new=AsyncMock()) as dispatch,
            patch.object(client, "fetch_broadcast", new=AsyncMock(return_value=completed)),
        ):
            result = await service.dispatch_auto("notice", "all", [])
        create.assert_awaited_once_with("notice", "all", [])
        begin.assert_awaited_once_with(broadcast_id)
        dispatch.assert_awaited_once_with(broadcast_id)
        self.assertEqual(result, completed)


class BroadcastSettingsTests(IsolatedAsyncioTestCase):
    async def test_missing_setting_fails_closed(self):
        pool = AsyncMock()
        pool.fetchval.return_value = None
        with patch.object(client.psql, "get_pool", return_value=pool):
            self.assertFalse(await client.get_auto_enabled())


class BroadcastSelectionTests(IsolatedAsyncioTestCase):
    async def test_selected_audience_queries_only_requested_internal_ids(self):
        user_id = uuid4()
        connection = AsyncMock()
        connection.fetch.return_value = [{"id": user_id, "line_user_id": "U1"}]
        transaction = MagicMock()
        transaction.__aenter__.return_value = transaction
        connection.transaction = MagicMock(return_value=transaction)
        acquire = MagicMock()
        acquire.__aenter__.return_value = connection
        pool = MagicMock()
        pool.acquire.return_value = acquire
        with patch.object(client.psql, "get_pool", return_value=pool):
            await client.create_draft("notice", "selected", [user_id])
        query, selected_ids = connection.fetch.await_args.args
        self.assertIn("id = ANY", query)
        self.assertEqual(selected_ids, [user_id])
        inserted = connection.executemany.await_args.args[1]
        self.assertEqual(inserted[0][2:4], (user_id, "U1"))

    async def test_unknown_selected_user_rolls_back_draft(self):
        missing_id = uuid4()
        connection = AsyncMock()
        connection.fetch.return_value = []
        transaction = MagicMock()
        transaction.__aenter__.return_value = transaction
        connection.transaction = MagicMock(return_value=transaction)
        acquire = MagicMock()
        acquire.__aenter__.return_value = connection
        pool = MagicMock()
        pool.acquire.return_value = acquire
        with (
            patch.object(client.psql, "get_pool", return_value=pool),
            self.assertRaises(client.UnknownBroadcastUsersError) as raised,
        ):
            await client.create_draft("notice", "selected", [missing_id])
        self.assertEqual(raised.exception.user_ids, [missing_id])
        transaction.__aexit__.assert_awaited_once()
        self.assertIs(transaction.__aexit__.await_args.args[0], client.UnknownBroadcastUsersError)


class BroadcastApiTests(IsolatedAsyncioTestCase):
    async def test_repeat_send_returns_409_and_does_not_schedule(self):
        broadcast_id = uuid4()
        tasks = MagicMock()
        with patch.object(
            service, "request_send", new=AsyncMock(return_value=({"id": broadcast_id, "status": "sending"}, False))
        ):
            with self.assertRaises(api.HTTPException) as raised:
                await api.send_broadcast(broadcast_id, tasks, MagicMock())
        self.assertEqual(raised.exception.status_code, 409)
        tasks.add_task.assert_not_called()

    async def test_history_passes_pagination_and_preserves_total(self):
        with patch.object(client, "list_broadcasts", new=AsyncMock(return_value=([], 321))) as listing:
            result = await api.get_broadcasts(limit=100, offset=200)
        listing.assert_awaited_once_with(100, 200)
        self.assertEqual(result, {"items": [], "total": 321})

    async def test_settings_reflect_database_gate(self):
        with patch.object(client, "get_auto_enabled", new=AsyncMock(return_value=True)):
            result = await api.get_broadcast_settings()
        self.assertEqual(result, {"auto_enabled": True, "configured_auto_enabled": True})
