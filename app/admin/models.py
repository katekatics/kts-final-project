from dataclasses import dataclass

from sqlalchemy import (
    Column,
    Integer,
    Text,
    Boolean
)

from app.store.database.sqlalchemy_base import db


@dataclass
class Word:
    id: int
    key: str
    desc: str
    is_used: bool


class WordModel(db):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True)
    key = Column(Text, nullable=False, unique=True)
    desc = Column(Text, nullable=False)
    is_used = Column(Boolean, default=False)

    def __str__(self):
        return "{} ({})".format(self.desc, self.key)
