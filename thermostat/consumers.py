import asyncio
from typing import List, Optional
from logging import getLogger

from channels.generic.websocket import AsyncJsonWebsocketConsumer

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

    async def connect(self):
        logger.info("New Websocket connected")
        await self.accept()

        self.thermostat = await get_thermostat()

        for field, key in [
            # System parameters (editable)
            # Cooling setpoint
            (self.thermostat.tstat, "t_cool"),
            # Heating setpoint
            (self.thermostat.tstat, "t_heat"),
            # Current fan mode
            (self.thermostat.tstat, "fmode"),

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
        logger.info(f"Websocket disconnected with code {code}")
        for w in self.tasks:
            w.cancel()

    async def receive_json(self, content, **kwargs):
        logger.info(f"Received message {content}")
        action = content['action']
        key = content['key']

        if action == "increment":
            await self.thermostat.tstat.increment(key)
        elif action == "decrement":
            await self.thermostat.tstat.decrement(key)

    async def watch_value(self, field, name):
        iterator = field.watch(name)
        async for value in iterator:
            logger.debug(f"New value for {name}: {value}")
            try:
                await self.send_json({'key': name, 'value': value})
            except Exception:
                logger.exception("Error sending JSON")
                await self.close()
                raise
