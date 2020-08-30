import asyncio
from collections import defaultdict
from typing import Dict, List, NamedTuple, Any, Tuple
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
        until: int

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
        # value in the future. The int value is a timestamp for when the task
        # is scheduled for
        self.timed_setters: Dict[str, "ThermostatEndpoint.TimedSetter"] = {}

    async def watch(self, key):
        """Returns an async iterator that yields a value whenever it changes"""
        current_value = (await self.get(key))
        current_timer = self.timed_setters.get(key)

        logger.debug(f"Starting new watcher for {key}. Initial value: {current_value}")

        yield current_value, current_timer


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

                new_timer = self.timed_setters.get(key)

                if new_value != current_value or new_timer != current_timer:
                    logger.debug(f"Watcher: Key {key} changed: "
                                 f"{current_value} → {new_value}")
                    yield new_value, new_timer
                    current_value = new_value
                    current_timer = new_timer

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(f"Watcher for {key} got unhandled exception")
            raise
        finally:
            logger.debug(f"Watcher for {key} is exiting")
            self.watchers[key].remove(event)

    async def get(self, key):
        """Get the value for the given key

        Returns cached data if it was last fetched less than self.timeout
        seconds ago. Otherwise, fetches and updates all keys, then returns
        the requested key.

        May raise asyncio.TimeoutError if the fetch fails.
        """
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
        TRIES = 5
        n = 0
        while True:
            try:
                async with session.get(self.url) as response:
                    response.raise_for_status()
                    return await response.json()
            except asyncio.TimeoutError:
                n += 1
                if n <= TRIES:
                    logger.warning(f"Request timed out for {self.url}. "
                                   f"Retrying")
                    await asyncio.sleep(1)
                else:
                    logger.error(f"Request failed {TRIES} times. Bailing.")
                    raise

    async def set(self, key, value):
        session = await self.get_session()
        data = {key: value}

        async with session.post(self.url, json=data) as response:
            response.raise_for_status()

        # Setting a value is one way to clear a timer, even if it's being set
        # to the current value.
        timer = self.timed_setters.get(key)
        if timer is not None:
            timer.task.cancel()
            del self.timed_setters[key]

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

        Duration is in minutes

        Returns a tuple of (task, key, orig_value) so the caller can keep track of
        the status of the timed setter."""
        existing_timer = self.timed_setters.get(key)

        # What do we set the value back to when the timer expires?
        if existing_timer is not None:
            # We're replacing an existing timer. Use the original original value
            original_value = existing_timer.orig_value
            logger.info(f"Replacing timer for {key}")
        else:
            # Setting a new timer. Use the current value as the original value
            original_value = await self.get(key)
            if original_value == new_value:
                # No point in setting a timer
                logger.debug(f"Can't set timer for {key}")
                return
            logger.info(f"Setting new timer for {key}")

        if original_value != new_value:
            await self.set(key, new_value)

        # Make sure any existing timed setter tasks are canceled before we
        # replace it
        if existing_timer is not None:
            existing_timer.task.cancel()

        until = time.time() + duration*60

        task = asyncio.create_task(
            self._set_back_at(key, original_value, new_value, until)
        )
        self.timed_setters[key] = self.TimedSetter(
            task=task,
            key=key,
            orig_value=original_value,
            until=until,
        )

        # Alert any waiters that there's a new timed setter and possibly a new
        # value (although that would have been done by set())
        for w in self.watchers[key]:
            w.set()

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
                    logger.info("Timed setter exiting because value changed out-of-band")
                    return

                if time.time() > timestamp:
                    logger.info(f"Timed setter setting {key} to {orig_value}")
                    await self.set(key, orig_value)
                    return

        except Exception:
            logger.exception("Timed setter task got an exception")
            raise

        finally:
            logger.debug(f"timed setter for {key} is closing down")
            self.watchers[key].remove(event)

            # If we're the last timer and we're done, remove ourself from
            # the timed_setters dict and alert any watchers.
            # It's possible we're not the current task in the timed_setters
            # dict though: set_for_time() may have replaced us.
            # It's also possible set() removed the item already, if an explicit
            # set() was given to cancel the timer.
            ts = self.timed_setters.get(key)
            if ts is not None and ts.task is asyncio.current_task():
                logger.debug("_set_back_at removing own task from "
                             f"timed_setters list (key {key})")
                del self.timed_setters[key]
                for w in self.watchers[key]:
                    w.set()
