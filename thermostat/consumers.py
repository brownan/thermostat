import asyncio
from datetime import datetime
from typing import List, Optional
from logging import getLogger

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .thermostat import Thermostat

logger = getLogger("thermostat.consumers")

# Can't create the thermostat object until the event loop starts, so do this
# lazily
_thermostat = None
async def get_thermostat():
    global _thermostat
    if _thermostat is not None:
        return _thermostat

    _thermostat = Thermostat("10.0.7.36")
    return _thermostat


class ThermostatControl(AsyncJsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.thermostat: Optional[Thermostat] = None
        self.tasks: List[asyncio.Task] = []

    @property
    def hoststr(self):
        return f"[{self.scope['client'][0]}:{self.scope['client'][1]}]"

    async def connect(self):
        logger.info(f"New Websocket connected from {self.hoststr}")
        await self.accept()

        self.thermostat = await get_thermostat()

        for field, key in [
            # System parameters (editable)
            # Cooling setpoint
            (self.thermostat.tstat, "t_cool"),
            # Heating setpoint
            (self.thermostat.tstat, "t_heat"),
            # Current fan mode
            # (0 - Auto, 1 - Circulate, 2 - On)
            (self.thermostat.tstat, "fmode"),
            # Current thermostat mode
            # (0 - Off, 1 - Heat, 2 - Cool, 3 - Auto)
            (self.thermostat.tstat, "tmode"),

            # System status variables (read only)
            # Current temperature
            (self.thermostat.tstat, "temp"),
            # Current humidity
            (self.thermostat.humidity, "humidity"),
            # Current thermostat state (0 - idle, 1 - heating, 2 - cooling)
            (self.thermostat.tstat, "tstate"),
            # Current fan state (true - fan running, false - fan idle)
            (self.thermostat.tstat, "fstate"),
        ]:
            self.tasks.append(asyncio.create_task(
                self.watch_value(field, key)
            ))

    async def disconnect(self, code):
        logger.info(f"Websocket disconnected from {self.hoststr} with code"
                    f" {code}")
        for w in self.tasks:
            w.cancel()

    async def receive_json(self, content, **kwargs):
        logger.info(f"Received message from {self.hoststr} {content!r}")
        key = content['key']

        if "action" in content:
            action = content['action']
            if action == "increment":
                await self.thermostat.tstat.increment(key)
            elif action == "decrement":
                await self.thermostat.tstat.decrement(key)
        elif "value" in content:
            value = content['value']
            if 'duration' in content:
                await self.thermostat.tstat.set_for_time(
                    key,
                    value,
                    int(content['duration']),
                )
            else:
                await self.thermostat.tstat.set(key, value)

    async def watch_value(self, field, key):
        try:
            iterator = field.watch(key)
            async for value, timer in iterator:
                logger.info(f"Sending new value for {key} to {self.hoststr}:"
                             f" {value}")
                # Check to see if it has a timer set
                if timer is not None:
                    dt = datetime.fromtimestamp(
                        timer.until,
                        timezone.get_current_timezone()
                    )
                    extra_kwargs = {
                        'until': dt.strftime("%I:%M %p"),
                    }
                else:
                    extra_kwargs = {}

                await self.send_json({
                    'type': 'state-var',
                    'key': key,
                    'value': value,
                    **extra_kwargs,
                })
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(f"Error in {self.hoststr}'s watcher for {key}. "
                             f"Closing websocket.")
            await self.close()
            raise
