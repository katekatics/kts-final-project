import asyncio
import typing
from asyncio import Task
from datetime import datetime, timedelta

from sqlalchemy import select, update, func

from app.admin.models import WordModel
from app.game.models import GameModel, UserModel, Game, User, StepOrderModel, ScoreModel, Score
from app.store.vk_api.dataclasses import Update, Message

if typing.TYPE_CHECKING:
    from app.web.app import Application

GAME_RULES = """
Поле чудес:\n
Для того, чтобы вступить в игру напишите /играть.\n
Для начала игры - /начать.\n
Для досрочного завершения игры - /завершить.\n
Для предложения буквы или слова - /буква а, /слово машина.
"""
BEFORE_START = """
Дождитесь остальных игроков или начинайте игру с помощью команды /начать.
После начала игры у Вас будет 1 минута на ответ.
"""

OPTIONS = {
    "enter": "/играть",
    "start": "/начать",
    "finish": "/завершить",
    "symbol": "/буква",
    "word": "/слово"
}

SCORES = {
    "symbol": 50,
    "word": 200
}
PREPARE = "preparing"
START = "started"
CANCEL = "cancelled"
FINISH = "finished"

CHECK_STEP_INTERVAL = 5


class BotManager:
    def __init__(self, app: "Application"):
        self.app = app
        self.change_step_task: typing.Optional[Task] = None

    async def handle_updates(self, updates: list[Update]):
        if updates:
            msg = updates[-1].object.message
            if msg.text.startswith("/"):
                if msg.text == OPTIONS["enter"]:
                    await self.app.store.vk_api.send_message(
                        Message(
                            user_id=msg.from_id,
                            text="Вы вступили в игру"
                        )
                    )
                    game = await self.get_game_by_peer_id(msg.from_id)
                    if not game:
                        game = await self.create_game(msg)
                    user = await self.add_user(msg)
                    await self.create_step_order(game, user)
                elif msg.text == OPTIONS["start"]:
                    if not await self.is_game_started(msg):
                        await self.start_game(msg)
                    else:
                        await self.app.store.vk_api.send_message(
                            Message(
                                user_id=msg.from_id,
                                text="Игра уже начата"
                            )
                        )
                elif msg.text == OPTIONS["finish"]:
                    await self.finish_game(msg)
                    await self.cancel_game(msg)
                    await self.stop_task()
                elif msg.text.startswith(OPTIONS["symbol"]):
                    await self.check_symbol(msg)
                elif msg.text.startswith(OPTIONS["word"]):
                    await self.check_word(msg)
                else:
                    await self.app.store.vk_api.send_message(
                        Message(
                            user_id=msg.from_id,
                            text=GAME_RULES
                        )
                    )
            else:
                pass

    # Создание игры
    async def create_game(self, data):
        new_game = GameModel(peer_id=data.from_id, status=PREPARE)
        async with self.app.database.session.begin() as session:
            session.add(new_game)
        await self.app.store.vk_api.send_message(
            Message(
                user_id=data.from_id,
                text=BEFORE_START
            )
        )
        return Game(
            id=new_game.id,
            start_time=new_game.start_time,
            end_time=new_game.end_time,
            status=new_game.status,
            peer_id=new_game.peer_id,
            word_id=new_game.word_id,
            word_state=new_game.word_state,
            whos_step=new_game.whos_step,
            deadline=new_game.deadline
        )

    # Начало игры
    async def start_game(self, data):
        word, desc, word_id = await self.get_word()
        encrypted_word = len(word) * "*"
        await self.app.store.vk_api.send_message(
            Message(
                user_id=data.from_id,
                text="{}\n Загадка: {}".format(encrypted_word, desc)
            )
        )
        await self.create_change_step_task(data.from_id)
        await self.update_game(data, word_id, encrypted_word)
        await self.update_word(word_id)

    async def create_change_step_task(self, from_id):
        await asyncio.sleep(CHECK_STEP_INTERVAL)
        self.change_step_task = asyncio.create_task(self.change_step(from_id))

    async def stop_task(self):
        await asyncio.wait_for(self.change_step_task, timeout=None)
        self.change_step_task.cancel()

    async def change_step(self, from_id):
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(GameModel)
                .where(GameModel.deadline <= datetime.now())
            )).scalars().all()
            if res:
                for i in res:
                    cur = await self.change_player(i.peer_id)
                    await self.app.store.vk_api.send_message(
                        Message(
                            user_id=i.peer_id,
                            text="Ходит {}".format(await self.get_name(cur))
                        )
                    )
        await self.create_change_step_task(from_id)

    # Проверка буквы в слове
    async def check_symbol(self, data):
        if await self.is_right_player(data):
            symbol = data.text.split(" ")
            if len(symbol) < 2:
                await self.app.store.vk_api.send_message(
                    Message(
                        user_id=data.from_id,
                        text="Вы не ввели букву"
                    )
                )
            elif len(symbol) == 2:
                state, word = await self.check_symbol_in_word(symbol[1], data)
                if state:
                    await self.add_score(data, "symbol")
                    await self.app.store.vk_api.send_message(
                        Message(
                            user_id=data.from_id,
                            text="Буква {} есть в слове: {}".format(symbol[1], word)
                        )
                    )
                    if "*" not in word:
                        await self.finish_game(data)
                        await self.stop_task()
                else:
                    await self.app.store.vk_api.send_message(
                        Message(
                            user_id=data.from_id,
                            text="Такой буквы нет: {}".format(symbol[1], word)
                        )
                    )
                    await self.change_player(data.from_id)
            else:
                await self.app.store.vk_api.send_message(
                    Message(
                        user_id=data.from_id,
                        text="Введите только одну букву"
                    )
                )
        else:
            await self.app.store.vk_api.send_message(
                Message(
                    user_id=data.from_id,
                    text="Сейчас не Ваш ход"
                )
            )

    # Проверка слова
    async def check_word(self, data):
        if await self.is_right_player(data):
            word = data.text.split(" ")
            if len(word) < 2:
                await self.app.store.vk_api.send_message(
                    Message(
                        user_id=data.from_id,
                        text="Вы не ввели слово"
                    )
                )
            elif len(word) == 2:
                state, w = await self.check_word_in_word(word[1], data)
                if state:
                    await self.add_score(data, "word")
                    await self.app.store.vk_api.send_message(
                        Message(
                            user_id=data.from_id,
                            text="Вы угадали загаданное слово: {}".format(w)
                        )
                    )
                    await self.finish_game(data)
                    await self.stop_task()
                else:
                    await self.app.store.vk_api.send_message(
                        Message(
                            user_id=data.from_id,
                            text="Неверное слово: {} \n Вы выбываете из игры".format(w)
                        )
                    )
                    await self.change_player(data.from_id)
            else:
                await self.app.store.vk_api.send_message(
                    Message(
                        user_id=data.from_id,
                        text="Введите только одно слово"
                    )
                )
        else:
            await self.app.store.vk_api.send_message(
                Message(
                    user_id=data.from_id,
                    text="Сейчас не Ваш ход"
                )
            )

    # Завершение игры
    async def finish_game(self, data):
        async with self.app.database.session() as session:
            await session.execute(
                update(GameModel).
                where(GameModel.peer_id == data.from_id).
                values(
                    end_time=datetime.now(),
                    status=FINISH
                )
            )
            await session.commit()
        await self.app.store.vk_api.send_message(
            Message(
                user_id=data.from_id,
                text="Вы завершили игру"
            )
        )
        await self.results(data)
        await self.find_winner(data)

    async def get_game_by_peer_id(self, peer_id):
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(GameModel)
                .where(GameModel.peer_id == peer_id)
            )).scalars().first()
            if res:
                return Game(
                    id=res.id,
                    start_time=res.start_time,
                    end_time=res.end_time,
                    status=res.status,
                    peer_id=res.peer_id,
                    word_id=res.word_id,
                    word_state=res.word_state,
                    whos_step=res.whos_step,
                    deadline=res.deadline
                )

    async def add_user(self, data):
        user = await self.get_user_by_vk_id(data.vk_user_id)
        if not user:
            new_user = UserModel(vk_id=data.vk_user_id)
            async with self.app.database.session.begin() as session:
                session.add(new_user)
            return User(
                id=new_user.id,
                vk_id=new_user.vk_id
            )

    async def get_user_by_vk_id(self, vk_id):
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(UserModel)
                .where(UserModel.vk_id == vk_id)
            )).scalars().first()
            if res:
                return User(
                    id=res.id,
                    vk_id=res.vk_id
                )

    async def get_user_by_id(self, _id):
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(UserModel)
                .where(UserModel.id == _id)
            )).scalars().first()
            if res:
                return User(
                    id=res.id,
                    vk_id=res.vk_id
                )

    async def is_right_player(self, data):
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(GameModel)
                .where(GameModel.peer_id == data.from_id)
                .where(GameModel.start_time != None)
                .where(GameModel.end_time == None)
            )).scalars().first()
            if res:
                if res.whos_step == data.vk_user_id:
                    return True
                else:
                    return False

    async def update_game(self, data, word_id, encrypted_word):
        async with self.app.database.session() as session:
            await session.execute(
                update(GameModel).
                where(GameModel.peer_id == data.from_id).
                values(
                    start_time=datetime.now(),
                    status=START,
                    word_id=word_id,
                    word_state=encrypted_word,
                    whos_step=data.vk_user_id,
                    deadline=datetime.now() + timedelta(seconds=30)
                )
            )
            await session.commit()

    async def update_word(self, _id):
        async with self.app.database.session() as session:
            await session.execute(
                update(WordModel).
                where(WordModel.id == _id).
                values(
                    is_used=True
                )
            )
            await session.commit()

    async def create_step_order(self, game, user):
        # TODO если игра уже закончена, обновить существующую очередность для этого же чата
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(StepOrderModel)
                .where(StepOrderModel.game_id == game.id)
                .order_by(StepOrderModel.step_number.desc())
            )).scalars().first()
            if not res:
                count = 1
                new_order = StepOrderModel(user_id=user.id, game_id=game.id, step_number=count)
            else:
                new_order = StepOrderModel(user_id=user.id, game_id=game.id, step_number=res.step_number + 1)
            async with self.app.database.session.begin() as session:
                session.add(new_order)

    async def get_word(self):
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(WordModel)
                .where(WordModel.is_used == False)
            )).scalars().first()
            if res:
                return res.key, res.desc, res.id

    async def check_symbol_in_word(self, symbol, data):
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(WordModel, GameModel)
                .join(GameModel, WordModel.id == GameModel.word_id)
                .where(GameModel.peer_id == data.from_id)
            )).all()
            if res:
                word = res[0].WordModel.key.lower()
                word_state = res[0].GameModel.word_state
                word_state_list = list(word_state)
                if symbol.lower() in word:
                    word_list = list(word)
                    symbol_idx = []
                    for i, j in enumerate(word_list):
                        if j == symbol.lower():
                            symbol_idx.append(i)

                    for i in symbol_idx:
                        word_state_list[i] = symbol
                    word_state = "".join(word_state_list)
                    await self.update_word_state(word_state, data)
                    return True, word_state
                else:
                    return False, word_state

    async def check_word_in_word(self, given_word, data):
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(WordModel, GameModel)
                .join(GameModel, WordModel.id == GameModel.word_id)
                .where(GameModel.peer_id == data.from_id)
            )).all()
            if res:
                word = res[0].WordModel.key.lower()
                word_state = res[0].GameModel.word_state
                if word.lower() == given_word:
                    await self.update_word_state(word, data)
                    return True, given_word
                else:
                    return False, word_state

    async def update_word_state(self, updated_word, data):
        async with self.app.database.session() as session:
            await session.execute(
                update(GameModel).
                where(GameModel.peer_id == data.from_id).
                values(
                    word_state=updated_word
                )
            )
            await session.commit()

    async def get_current_player(self, from_id):
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(GameModel.whos_step)
                .where(GameModel.peer_id == from_id)
            )).scalars().first()
            if res:
                return res

    async def change_player(self, from_id):
        cur = (await self.get_user_by_vk_id(await self.get_current_player(from_id))).id
        game = await self.get_game_by_peer_id(from_id)
        async with self.app.database.session() as session:
            count = (await session.execute(
                select(func.max(StepOrderModel.step_number))
                .where(StepOrderModel.game_id == game.id)
            )).scalars().first()
            await session.commit()
            if count:
                if cur < count:
                    cur += 1
                else:
                    cur = 1
            new_cur = await self.update_whos_step(from_id, cur)
            await self.app.store.vk_api.send_message(
                Message(
                    user_id=from_id,
                    text="Ходит {}".format(await self.get_name(new_cur))
                )
            )
            return new_cur

    async def update_whos_step(self, from_id, cur):
        new_cur = (await self.get_user_by_id(cur)).vk_id
        async with self.app.database.session() as session:
            await session.execute(
                update(GameModel).
                where(GameModel.peer_id == from_id).
                values(
                    whos_step=new_cur,
                    deadline=datetime.now() + timedelta(seconds=30)
                )
            )
            await session.commit()
            return new_cur

    async def add_score(self, data, state):
        user = await self.get_user_by_vk_id(data.vk_user_id)
        game = await self.get_game_by_peer_id(data.from_id)
        new_score = ScoreModel(
            user_id=user.id,
            game_id=game.id,
            score=SCORES[state]
        )
        async with self.app.database.session() as session:
            session.add(new_score)
            await session.commit()
        return Score(
            id=new_score.id,
            user_id=new_score.user_id,
            game_id=new_score.game_id,
            score=new_score.score
        )

    async def results(self, data):
        game = await self.get_game_by_peer_id(data.from_id)
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(ScoreModel.user_id, func.sum(ScoreModel.score))
                .group_by(ScoreModel.user_id, ScoreModel.game_id)
                .having(ScoreModel.game_id == game.id)
            )).all()
            await session.commit()
            result = []
            if res:
                for score in res:
                    vk_id = (await self.get_user_by_id(score[0])).vk_id
                    name = await self.get_name(vk_id)
                    result.append((name, score[1]))
            await self.app.store.vk_api.send_message(
                Message(
                    user_id=data.from_id,
                    text="Результаты: {}".format([i for i in result])
                )
            )

    async def get_name(self, player):
        res = await self.app.store.vk_api.get_user_info(
            player
        )
        if res:
            data = (await res.json())["response"][0]
            return "{} {}".format(data["first_name"], data["last_name"])

    async def cancel_game(self, data):
        async with self.app.database.session() as session:
            await session.execute(
                update(GameModel).
                where(GameModel.peer_id == data.from_id).
                values(
                    end_time=datetime.now(),
                    status=CANCEL
                )
            )
            await session.commit()

    async def end_game(self, data):
        async with self.app.database.session() as session:
            await session.execute(
                update(GameModel).
                where(GameModel.peer_id == data.from_id).
                values(
                    end_time=datetime.now(),
                    status=FINISH
                )
            )
            await session.commit()

    async def find_winner(self, data):
        game = await self.get_game_by_peer_id(data.from_id)
        async with self.app.database.session() as session:
            res = (await session.execute(
                select(ScoreModel.user_id, func.sum(ScoreModel.score))
                .group_by(ScoreModel.user_id, ScoreModel.game_id)
                .having(ScoreModel.game_id == game.id)
                .order_by(func.sum(ScoreModel.score).desc())
            )).scalars().first()
            await session.commit()
            if res:
                vk_id = (await self.get_user_by_id(res)).vk_id
                await self.app.store.vk_api.send_message(
                    Message(
                        user_id=data.from_id,
                        text="Победитель: {}".format(await self.get_name(vk_id))
                    )
                )

    async def is_game_started(self, data):
        async with self.app.database.session.begin() as session:
            res = (await session.execute(
                select(GameModel)
                .where(GameModel.peer_id == data.from_id)
            )).scalars().first()
            if res:
                if res.status == START:
                    return True
                else:
                    return False
