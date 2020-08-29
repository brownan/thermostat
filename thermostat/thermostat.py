import asyncio
from collections import defaultdict
from typing import Dict, List, NamedTuple, Any
import time
from logging import getLogger

from aiohttp import ClientSession, ClientTimeout


logger = getLogger("thermostat.thermostat")

class Thermostat:
    """Thermostat state class"""

    def __init__(self, host):
        self.host = host
        self._session_lock = asyncio.Lock()
        self._session = ClientSession(
            timeout=ClientTimeout(total=5)
        )

        self.tstat = ThermostatEndpoint(
            self._construct_url("/tstat"),
            self.get_session,
        )

        self.humidity = ThermostatEndpoint(
            self._construct_url("/tstat/humidity"),
            self.get_session,
            timeout=60
        )

    async def get_session(self):
        async with self._session_lock:
            return self._session

    def _construct_url(self, path):
        return f"http://{self.host}/{path.lstrip('/')}"


class ThermostatEndpoint:

    class TimedSetter(NamedTuple):
        task: asyncio.Task
        key: str
        orig_value: Any

    def __init__(self, url, get_session, timeout=10):
        self.url = url
        self.get_session = get_session
        self.timeout = timeout

        self._get_lock = asyncio.Lock()

        # The most recently acquired values
        self.cached_values = {}
        self.last_fetched = 0

        # Maps keys to a list of Event objects that want to be notified when
        # a key is updated
        self.watchers: Dict[str, List[asyncio.Event]] = defaultdict(list)

        # Maps keys to tasks that are scheduled to set that key to a different
        # value in the future
        self.timed_setters: Dict[str, asyncio.Task] = {}

    async def watch(self, key):
        """Returns an async iterator that yields a value whenever it changes"""
        current_value = (await self.get(key))
        yield current_value

        event = asyncio.Event()
        self.watchers[key].append(event)
        try:
            while True:
                # If nothing notifies us of a new value in self.timeout seconds,
                # then we'll call self.get() ourselves to query for a new
                # value and see if it's changed.
                try:
                    await asyncio.wait_for(event.wait(), self.timeout)
                except asyncio.TimeoutError:
                    # Event timed out. Query for a new value
                    new_value = (await self.get(key))
                else:
                    # Event was triggered. Pull value from cache
                    new_value = self.cached_values.get(key)

                event.clear()
                if new_value != current_value:
                    yield new_value
                    current_value = new_value
        finally:
            self.watchers[key].remove(event)

    async def get(self, key):
        # Only one fetch allowed at a time. If two tasks try to call this, the
        # second one will wait on the lock, and then get the cached value.
        async with self._get_lock:
            if (
                self.last_fetched + self.timeout < time.monotonic()
            ):
                logger.debug(f"Fetching new values from {self.url}")
                self.cached_values = await self._fetch()
                self.last_fetched = time.monotonic()

                # Notify all watchers that values have possibly changed
                for watcher_list in self.watchers.values():
                    for watcher in watcher_list:
                        watcher.set()

            return self.cached_values.get(key)

    async def _fetch(self):
        session = await self.get_session()
        async with session.get(self.url) as response:
            response.raise_for_status()
            return await response.json()

    async def set(self, key, value):
        session = await self.get_session()
        data = {key: value}

        async with session.post(self.url, json=data) as response:
            response.raise_for_status()

        # Update the cached value so any watchers will see the new value until
        # the next general update from the thermostat
        self.cached_values[key] = value
        for watcher in self.watchers[key]:
            watcher.set()

    async def increment(self, key):
        current = self.cached_values.get(key)
        if current is None:
            current = await self.get(key)
        await self.set(key, current+1)

    async def decrement(self, key):
        current = self.cached_values.get(key)
        if current is None:
            current = await self.get(key)
        await self.set(key, current-1)

    async def set_for_time(self, key, new_value, duration):
        """Sets a value for the given duration, then sets it back

        Returns a tuple of (task, key, orig_value) so the caller can keep track of
        the status of the timed setter."""
        original_value = await self.get(key)
        await self.set(key, new_value)
        if key in self.timed_setters:
            self.timed_setters[key].cancel()

        task = self.timed_setters[key] = asyncio.create_task(
            self._set_back_at(key, original_value, new_value, time.monotonic() + duration)
        )

        return self.TimedSetter(
            task=task,
            key=key,
            orig_value=original_value,
        )

    async def _set_back_at(self, key, orig_value, new_value, timestamp):
        """Watches the given key. If the current time is >= timestamp, then
        set the key to orig_value. If the value changes from new_value at any point,
        then do nothing and exit

        """
        # Because asynchronous iterators are sort of limited right now, we can't
        # await on the next value of the iterator AND wait on something else
        # at the same time (like a timeout), so this method re-implements much
        # of the watch() logic.
        event = asyncio.Event()
        self.watchers[key].append(event)
        try:
            while True:
                try:
                    await asyncio.wait_for(event.wait(), self.timeout)
                except asyncio.TimeoutError:
                    # No events, query ourselves for a new value
                    cur_value = (await self.get(key))
                else:
                    # Something else updated the value, see what it is
                    cur_value = self.cached_values.get(key)

                event.clear()
                if cur_value != new_value:
                    return

                if time.monotonic() > timestamp:
                    await self.set(key, orig_value)
                    return

        finally:
            self.watchers[key].remove(event)
