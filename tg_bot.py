import os
import logging
import random
from dotenv import load_dotenv
from quiz_utils import load_questions, normalize_answer

import redis
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ConversationHandler,
)

logger = logging.getLogger(__file__)

QUIZ_STATE = 1

BTN_NEW_QUESTION = "Новый вопрос"
BTN_GIVE_UP = "Сдаться"
BTN_SCORE = "Мой счёт"


def get_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с основными кнопками."""
    keyboard = [
        [BTN_NEW_QUESTION, BTN_GIVE_UP],
        [BTN_SCORE],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def start(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /start."""
    user = update.effective_user
    update.message.reply_text(
        f"Привет, {user.first_name}!\n"
        "Это бот-викторина.\n"
        f"Нажми «{BTN_NEW_QUESTION}», чтобы начать.",
        reply_markup=get_keyboard(),
    )


def help_command(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /help."""
    update.message.reply_text(
        "Команды и кнопки:\n"
        f"• {BTN_NEW_QUESTION} — задать новый вопрос\n"
        f"• {BTN_GIVE_UP} — показать ответ и завершить вопрос\n"
        f"• {BTN_SCORE} — показать твой счёт\n"
        "/quiz — начать викторину",
        reply_markup=get_keyboard(),
    )


def handle_new_question_request(update: Update, context: CallbackContext) -> int:
    """Выдать пользователю новый вопрос и сохранить его в Redis."""
    questions = context.bot_data["questions"]
    redis_client: redis.Redis = context.bot_data["redis"]

    user_id = update.effective_user.id
    question = random.choice(questions)

    redis_client.set(f"quiz:tg:{user_id}:current_question", question["question"])
    redis_client.set(f"quiz:tg:{user_id}:current_answer", question["answer"])

    update.message.reply_text(question["question"], reply_markup=get_keyboard())

    return QUIZ_STATE


def handle_give_up(update: Update, context: CallbackContext) -> int:
    """Показать правильный ответ и завершить текущий вопрос."""
    redis_client: redis.Redis = context.bot_data["redis"]
    user_id = update.effective_user.id

    current_answer = redis_client.get(f"quiz:tg:{user_id}:current_answer")

    if not current_answer:
        update.message.reply_text(
            "Сейчас нет активного вопроса. Нажми «Новый вопрос», чтобы начать.",
            reply_markup=get_keyboard(),
        )
        return QUIZ_STATE

    current_answer = current_answer.decode("utf-8")

    total_questions = int(redis_client.get(f"quiz:tg:{user_id}:total") or 0)
    redis_client.set(f"quiz:tg:{user_id}:total", total_questions + 1)

    update.message.reply_text(
        f"Правильный ответ: {current_answer}\n\n"
        f"Нажми «{BTN_NEW_QUESTION}», чтобы получить следующий вопрос.",
        reply_markup=get_keyboard(),
    )

    redis_client.delete(f"quiz:tg:{user_id}:current_answer")
    redis_client.delete(f"quiz:tg:{user_id}:current_question")

    return QUIZ_STATE


def show_score(update: Update, context: CallbackContext) -> int:
    """Показать статистику пользователя."""
    redis_client: redis.Redis = context.bot_data["redis"]
    user_id = update.effective_user.id

    correct_answers = int(redis_client.get(f"quiz:tg:{user_id}:correct") or 0)
    total_questions = int(redis_client.get(f"quiz:tg:{user_id}:total") or 0)

    if total_questions == 0:
        message_text = "Ты ещё не ответил ни на один вопрос. Нажми «Новый вопрос»!"
    else:
        message_text = (
            "Твой счёт:\n"
            f"Правильных ответов: {correct_answers}\n"
            f"Всего попыток: {total_questions}"
        )

    update.message.reply_text(message_text, reply_markup=get_keyboard())
    return QUIZ_STATE


def handle_solution_attempt(update: Update, context: CallbackContext) -> int:
    """Обработать попытку ответа на вопрос."""
    redis_client: redis.Redis = context.bot_data["redis"]
    user_id = update.effective_user.id
    user_answer = update.message.text.strip()

    current_answer = redis_client.get(f"quiz:tg:{user_id}:current_answer")

    if not current_answer:
        update.message.reply_text(
            f"Сначала нажми «{BTN_NEW_QUESTION}», чтобы получить вопрос.",
            reply_markup=get_keyboard(),
        )
        return QUIZ_STATE

    current_answer = current_answer.decode("utf-8")

    total_questions = int(redis_client.get(f"quiz:tg:{user_id}:total") or 0)
    redis_client.set(f"quiz:tg:{user_id}:total", total_questions + 1)

    normalized_user_answer = normalize_answer(user_answer)
    normalized_correct_answer = normalize_answer(current_answer)

    if normalized_user_answer and normalized_user_answer == normalized_correct_answer:
        correct_answers = int(redis_client.get(f"quiz:tg:{user_id}:correct") or 0)
        redis_client.set(f"quiz:tg:{user_id}:correct", correct_answers + 1)

        update.message.reply_text(
            "Верно!\n"
            f"Нажми «{BTN_NEW_QUESTION}», чтобы получить следующий вопрос.",
            reply_markup=get_keyboard(),
        )
    else:
        update.message.reply_text(
            f"Неверно.\nПравильный ответ: {current_answer}\n\n"
            f"Нажми «{BTN_NEW_QUESTION}», чтобы попробовать ещё.",
            reply_markup=get_keyboard(),
        )

    redis_client.delete(f"quiz:tg:{user_id}:current_answer")
    redis_client.delete(f"quiz:tg:{user_id}:current_question")

    return QUIZ_STATE


def main() -> None:
    """Точка входа в приложение — запуск бота."""
    load_dotenv()

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logger.setLevel(logging.INFO)

    tg_token = os.environ["TG_TOKEN"]
    redis_url = os.environ["REDIS_URL"]

    questions = load_questions("questions.json")
    redis_client = redis.Redis.from_url(redis_url)

    updater = Updater(tg_token, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.bot_data["questions"] = questions
    dispatcher.bot_data["redis"] = redis_client

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("quiz", handle_new_question_request),
            MessageHandler(Filters.regex(f"^{BTN_NEW_QUESTION}$"), handle_new_question_request),
        ],
        states={
            QUIZ_STATE: [
                MessageHandler(Filters.regex(f"^{BTN_NEW_QUESTION}$"), handle_new_question_request),
                MessageHandler(Filters.regex(f"^{BTN_GIVE_UP}$"), handle_give_up),
                MessageHandler(Filters.regex(f"^{BTN_SCORE}$"), show_score),
                MessageHandler(Filters.text & ~Filters.command, handle_solution_attempt),
            ]
        },
        fallbacks=[
            CommandHandler("help", help_command),
        ],
    )

    dispatcher.add_handler(conv_handler)

    logger.info("Quiz bot with Redis + ConversationHandler started")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
