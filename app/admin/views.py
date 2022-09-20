from aiohttp.web_exceptions import HTTPConflict
from aiohttp.web_response import json_response

from app.admin.schemas import WordSchema, WordsListSchema
from app.web.app import View


class WordAddView(View):
    async def post(self):
        data = await self.request.json()
        word = await self.store.admins.get_word_by_key(data["key"])
        if word:
            raise HTTPConflict(reason="The given word is already exist")
        else:
            word = await self.store.admins.create_word(key=data["key"], desc=data["desc"])
            return json_response(data=WordSchema().dump(word))


class WordListView(View):
    async def get(self):
        words = await self.store.admins.list_words()
        return json_response(data=WordsListSchema().dump({"words": words}))
