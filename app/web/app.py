from typing import Optional

from aiohttp.web import (
    Application as AiohttpApplication,
    Request as AiohttpRequest,
    View as AiohttpView,
)
from app.store.database.database import Database
from app.store import Store, setup_store
from app.web.config import Config, setup_config
from app.web.routes import setup_routes


class Application(AiohttpApplication):
    config: Optional[Config] = None
    database: Optional[Database] = None
    store: Optional[Store] = None


class Request(AiohttpRequest):

    @property
    def app(self) -> Application:
        return super().app()


class View(AiohttpView):
    @property
    def request(self) -> Request:
        return super().request

    @property
    def database(self):
        return self.request.app.database

    @property
    def store(self) -> Store:
        return self.request.app.store

    @property
    def data(self) -> dict:
        return self.request.get("data", {})


app = Application()


def setup_app(config_path: str) -> Application:
    setup_config(app, config_path)
    setup_routes(app)
    setup_store(app)
    return app
