import typing

from aiohttp.web_app import Application

if typing.TYPE_CHECKING:
    from app.web.app import Application


def setup_routes(app: Application):
    from app.admin.views import WordAddView, WordListView

    app.router.add_view("/admin.add_word", WordAddView)
    app.router.add_view("/admin.words", WordListView)
