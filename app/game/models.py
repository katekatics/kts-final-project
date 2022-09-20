from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    BigInteger,
    ForeignKey
)

from app.store.database.sqlalchemy_base import db


@dataclass
class Game:
    id: int
    start_time: datetime
    end_time: datetime
    status: str
    peer_id: int
    word_id: int
    word_state: str
    whos_step: int
    deadline: datetime


@dataclass
class User:
    id: int
    vk_id: int


@dataclass
class StepOrder:
    id: int
    user_id: int
    game_id: int
    step_number: int


@dataclass
class Score:
    id: int
    user_id: int
    game_id: int
    score: int


class GameModel(db):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(String, nullable=True)
    peer_id = Column(BigInteger, nullable=False)
    word_id = Column(Integer, ForeignKey("words.id", ondelete="CASCADE"), nullable=True)
    word_state = Column(String, nullable=True)
    whos_step = Column(BigInteger, nullable=True)
    deadline = Column(DateTime, nullable=True)

    def __str__(self):
        return "{}, {}, {}".format(self.id, self.peer_id, self.status)


class UserModel(db):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    vk_id = Column(BigInteger, nullable=False)


class StepOrderModel(db):
    __tablename__ = "step_orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    step_number = Column(Integer, nullable=False)


class ScoreModel(db):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, nullable=True, default=0)
