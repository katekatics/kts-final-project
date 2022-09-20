import time
import typing
from typing import Optional

from aiohttp.client import ClientSession

from app.base.base_accessor import BaseAccessor
from app.store.vk_api.dataclasses import Message, Update, UpdateObject, UpdateMessage
from app.store.vk_api.poller import Poller

if typing.TYPE_CHECKING:
    from app.web.app import Application


class VkApiAccessor(BaseAccessor):
    def __init__(self, app: "Application", *args, **kwargs):
        super().__init__(app, *args, **kwargs)
        self.session: Optional[ClientSession] = None
        self.key: Optional[str] = None
        self.server: Optional[str] = None
        self.poller: Optional[Poller] = None
        self.ts: Optional[int] = None

    async def connect(self, app: "Application"):
        self.session = ClientSession()

        resp = await self.session.get(
            self._build_query(
                "https://api.vk.com/method/",
                "groups.getLongPollServer",
                {
                    "access_token": self.app.config.bot.token,
                    "group_id": self.app.config.bot.group_id,
                    "v": "5.131",
                    "wait": 30,
                }
            )
        )
        data = await resp.json()
        self.ts = data['response']['ts']
        self.key = data['response']['key']
        self.server = data['response']['server']
        poller = Poller(store=app.store)
        await poller.start()

    async def disconnect(self, app: "Application"):
        if self.session:
            await self.session.close()
        if self.poller:
            await self.poller.stop()

    @staticmethod
    def _build_query(host: str, method: str, params: dict) -> str:
        url = host + method + "?"
        if "v" not in params:
            params["v"] = "5.131"
        url += "&".join([f"{k}={v}" for k, v in params.items()])
        return url

    async def _get_long_poll_service(self):
        params = {
            "act": "a_check",
            "key": self.key,
            "ts": self.ts,
            "wait": 5,  # TODO: 30
        }
        return self._build_query(self.server, '', params)

    async def poll(self):
        resp = await self.session.get(
            await self._get_long_poll_service()
        )
        data = await resp.json()
        self.ts = data['ts']
        updates = [
            Update(
                type=upd['type'],
                object=UpdateObject(
                    message=UpdateMessage(
                        vk_user_id=upd['object']['message']['from_id'],
                        from_id=upd['object']['message']['peer_id'],
                        text=upd['object']['message']['text'],
                        id=upd['object']['message']['id'],
                    )
                ),
            )
            for upd in data['updates']
        ]
        return updates

    async def send_message(self, message: Message) -> None:
        params = {
            "access_token": self.app.config.bot.token,
            "group_id": self.app.config.bot.group_id,
            "random_id": int(time.time() * 100),
            "message": message.text,
            "peer_id": message.user_id,
        }
        resp = await self.session.post(
            self._build_query('https://api.vk.com/method/', 'messages.send', params)
        )

    async def get_user_info(self, _id):
        params = {
            "access_token": self.app.config.bot.token,
            "user_ids": _id,
            "name_case": "nom",
        }
        resp = await self.session.get(
            self._build_query('https://api.vk.com/method/', 'users.get', params)
        )
        return resp
