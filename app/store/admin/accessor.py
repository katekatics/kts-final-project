from typing import Optional

from sqlalchemy import select

from app.admin.models import Word, WordModel
from app.base.base_accessor import BaseAccessor


class WordAccessor(BaseAccessor):
    async def create_word(self, key: str, desc: str) -> Word:
        new_word = WordModel(key=key, desc=desc)
        async with self.app.database.session.begin() as session:
            session.add(new_word)
        return Word(id=new_word.id, key=new_word.key, desc=new_word.desc, is_used=new_word.is_used)

    async def get_word_by_key(self, key: str) -> Optional[Word]:
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(WordModel)
                .where(WordModel.key == key)
            )).scalars().first()
            if res:
                return Word(id=res.id, key=res.key, desc=res.desc, is_used=res.is_used)

    async def list_words(self) -> list[Word]:
        Q = select(WordModel)
        async with self.app.database.session.begin() as session:
            res = (await session.execute(Q)).scalars().all()
            return res
