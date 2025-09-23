import asyncio

class EventBroadcaster:
    def __init__(self):
        self._subscribers = set()

    async def subscribe(self, queue: asyncio.Queue):
        self._subscribers.add(queue)

    def unsubscribe(self, queue: asyncio.Queue):
        self._subscribers.remove(queue)

    async def broadcast(self, message: str):
        for queue in self._subscribers:
            await queue.put(message)

broadcaster = EventBroadcaster()