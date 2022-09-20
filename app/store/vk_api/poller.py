import asyncio

from asyncio import Task
from typing import Optional

from app.store import Store


class Poller:
    def __init__(self, store: Store):
        self.store = store
        self.is_running = False
        self.poll_task: Optional[Task] = None

    async def start(self):
        self.poll_task = asyncio.create_task(self.poll())

    async def stop(self):
        if self.poll_task:
            try:
                await asyncio.wait_for(self.poll_task, timeout=None)
            except asyncio.TimeoutError:
                print('timeout!')

    async def poll(self):
        updates = await self.store.vk_api.poll()
        if updates:
            await self.store.bots_manager.handle_updates(updates=updates)
        # Заново ждем сообщений
        await self.start()
