from functools import partial

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.handlers.asgi import ASGIHandler
from django.urls import path

from thermostat import consumers


def single_to_double_callable(application):
    def new_application(scope):
        return partial(application, scope)
    return new_application


application = ProtocolTypeRouter({
    # Use the stock Django ASGI handler, not the channels-provided handler, for
    # http requests. In real production, we'd want to serve web requests from
    # a separate dedicated WSGI server anyways, but at least this way we can
    # take advantage of more of Django's async capabilities when running http
    # over asgi.
    'http': single_to_double_callable(ASGIHandler()),

    'websocket': URLRouter([
        path("ws/thermostat", consumers.ThermostatControl),
    ])
})
