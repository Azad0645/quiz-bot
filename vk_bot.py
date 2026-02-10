import os
import json
import logging
import random
from typing import List, Dict

from dotenv import load_dotenv
import redis
import vk_api as vk
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor


logger = logging.getLogger(__file__)

BTN_NEW_QUESTION = "Новый вопрос"
BTN_GIVE_UP = "Сдаться"
BTN_SCORE = "Мой счёт"


def load_questions(path: str = "questions.json") -> List[Dict[str, str]]:
    """Загрузить список вопросов из JSON-файла."""
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def make_redis_key(user_id: int, suffix: str) -> str:
    """Сформировать ключ Redis."""
    return f"quiz:{user_id}:{suffix}"


def normalize_answer(text: str) -> str:
    """
    Нормализовать ответ:
    - обрезать по первой точке или скобке;
    - убрать лишнюю пунктуацию;
    - привести к нижнему регистру;
    - нормализовать ё -> е.
    """
    if not text:
        return ""

    text = text.strip().lower()

    cut_pos = len(text)
    for separator in (".", "("):
        index = text.find(separator)
        if index != -1 and index < cut_pos:
            cut_pos = index

    core = text[:cut_pos].strip()
    core = core.strip(" .,!?:;—-\"'«»")
    core = core.replace("ё", "е")

    return core


def build_keyboard() -> str:
    """Создать клавиатуру ВК."""
    keyboard = VkKeyboard(one_time=False, inline=False)

    keyboard.add_button(BTN_NEW_QUESTION, color=VkKeyboardColor.POSITIVE)
    keyboard.add_button(BTN_GIVE_UP, color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button(BTN_SCORE, color=VkKeyboardColor.PRIMARY)

    return keyboard.get_keyboard()


def send_message(vk_api, user_id: int, text: str, keyboard: str | None = None) -> None:
    """Отправить сообщение пользователю."""
    params = {
        "user_id": user_id,
        "message": text,
        "random_id": random.randint(1, 1_000_000),
    }
    if keyboard is not None:
        params["keyboard"] = keyboard

    vk_api.messages.send(**params)


def handle_new_question_request(
    vk_api,
    redis_client: redis.Redis,
    questions: List[Dict[str, str]],
    user_id: int,
    keyboard: str,
) -> None:
    """Выдать пользователю новый вопрос и сохранить его в Redis."""
    question = random.choice(questions)

    redis_client.set(make_redis_key(user_id, "current_question"), question["question"])
    redis_client.set(make_redis_key(user_id, "current_answer"), question["answer"])

    send_message(vk_api, user_id, question["question"], keyboard=keyboard)


def handle_give_up(
    vk_api,
    redis_client: redis.Redis,
    user_id: int,
    keyboard: str,
) -> None:
    """Показать правильный ответ и завершить текущий вопрос."""
    current_answer = redis_client.get(make_redis_key(user_id, "current_answer"))

    if not current_answer:
        send_message(
            vk_api,
            user_id,
            "Сейчас нет активного вопроса. Нажми «Новый вопрос», чтобы начать.",
            keyboard=keyboard,
        )
        return

    current_answer = current_answer.decode("utf-8")

    total_questions = int(redis_client.get(make_redis_key(user_id, "total")) or 0)
    redis_client.set(make_redis_key(user_id, "total"), total_questions + 1)

    send_message(
        vk_api,
        user_id,
        f"Правильный ответ: {current_answer}\n\n"
        f"Нажми «{BTN_NEW_QUESTION}», чтобы получить следующий вопрос.",
        keyboard=keyboard,
    )

    redis_client.delete(make_redis_key(user_id, "current_answer"))
    redis_client.delete(make_redis_key(user_id, "current_question"))


def show_score(
    vk_api,
    redis_client: redis.Redis,
    user_id: int,
    keyboard: str,
) -> None:
    """Показать статистику пользователя."""
    correct_answers = int(redis_client.get(make_redis_key(user_id, "correct")) or 0)
    total_questions = int(redis_client.get(make_redis_key(user_id, "total")) or 0)

    if total_questions == 0:
        message_text = "Ты ещё не ответил ни на один вопрос. Нажми «Новый вопрос»!"
    else:
        message_text = (
            "Твой счёт:\n"
            f"Правильных ответов: {correct_answers}\n"
            f"Всего попыток: {total_questions}"
        )

    send_message(vk_api, user_id, message_text, keyboard=keyboard)


def handle_solution_attempt(
    vk_api,
    redis_client: redis.Redis,
    user_id: int,
    user_answer: str,
    keyboard: str,
) -> None:
    """Обработать попытку ответа на вопрос."""
    current_answer = redis_client.get(make_redis_key(user_id, "current_answer"))

    if not current_answer:
        send_message(
            vk_api,
            user_id,
            f"Сначала нажми «{BTN_NEW_QUESTION}», чтобы получить вопрос.",
            keyboard=keyboard,
        )
        return

    current_answer = current_answer.decode("utf-8")

    total_questions = int(redis_client.get(make_redis_key(user_id, "total")) or 0)
    redis_client.set(make_redis_key(user_id, "total"), total_questions + 1)

    normalized_user_answer = normalize_answer(user_answer)
    normalized_correct_answer = normalize_answer(current_answer)

    if normalized_user_answer and normalized_user_answer == normalized_correct_answer:
        correct_answers = int(redis_client.get(make_redis_key(user_id, "correct")) or 0)
        redis_client.set(make_redis_key(user_id, "correct"), correct_answers + 1)

        send_message(
            vk_api,
            user_id,
            "Верно!\n"
            f"Нажми «{BTN_NEW_QUESTION}», чтобы получить следующий вопрос.",
            keyboard=keyboard,
        )
    else:
        send_message(
            vk_api,
            user_id,
            f"Неверно.\nПравильный ответ: {current_answer}\n\n"
            f"Нажми «{BTN_NEW_QUESTION}», чтобы попробовать ещё.",
            keyboard=keyboard,
        )

    redis_client.delete(make_redis_key(user_id, "current_answer"))
    redis_client.delete(make_redis_key(user_id, "current_question"))


def main() -> None:
    """Точка входа — запуск ВК-бота."""
    load_dotenv()

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logger.setLevel(logging.INFO)

    vk_token = os.environ["VK_TOKEN"]
    redis_url = os.environ["REDIS_URL"]

    questions = load_questions("questions.json")
    redis_client = redis.Redis.from_url(redis_url)

    vk_session = vk.VkApi(token=vk_token)
    vk_api = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)

    keyboard_json = build_keyboard()

    logger.info("VK quiz bot with Redis started")

    for event in longpoll.listen():
        if event.type != VkEventType.MESSAGE_NEW:
            continue

        if not event.to_me:
            continue

        user_id = event.user_id
        text = (event.text or "").strip()

        if not text:
            continue

        if text == BTN_NEW_QUESTION:
            handle_new_question_request(
                vk_api=vk_api,
                redis_client=redis_client,
                questions=questions,
                user_id=user_id,
                keyboard=keyboard_json,
            )
        elif text == BTN_GIVE_UP:
            handle_give_up(
                vk_api=vk_api,
                redis_client=redis_client,
                user_id=user_id,
                keyboard=keyboard_json,
            )
        elif text == BTN_SCORE:
            show_score(
                vk_api=vk_api,
                redis_client=redis_client,
                user_id=user_id,
                keyboard=keyboard_json,
            )
        else:
            handle_solution_attempt(
                vk_api=vk_api,
                redis_client=redis_client,
                user_id=user_id,
                user_answer=text,
                keyboard=keyboard_json,
            )


if __name__ == "__main__":
    main()
