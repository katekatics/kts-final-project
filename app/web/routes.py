from aiohttp.web_app import Application
from app.admin.routes import setup_routes as admin_setup_routes


def setup_routes(app: Application):
    admin_setup_routes(app)
