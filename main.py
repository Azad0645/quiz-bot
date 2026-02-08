import os
import json
import logging
import random
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext


logger = logging.getLogger(__file__)


def load_questions(path: str = "questions.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    update.message.reply_text(
        f"Привет, {user.first_name}!\n"
        "Это бот-викторина.\n"
        "Напиши /quiz, чтобы получить вопрос."
    )


def help_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Команды:\n"
        "/quiz — задать случайный вопрос\n"
        "/help — показать эту справку"
    )


def quiz(update: Update, context: CallbackContext) -> None:
    questions = context.bot_data["questions"]
    question = random.choice(questions)

    context.user_data["current_answer"] = question["answer"]

    update.message.reply_text(question["question"])


def handle_answer(update: Update, context: CallbackContext) -> None:
    correct_answer = context.user_data.get("current_answer")

    if correct_answer is None:
        update.message.reply_text("Сначала напиши /quiz, чтобы получить вопрос.")
        return

    user_answer = update.message.text.strip()

    if user_answer.lower() == correct_answer.strip().lower():
        update.message.reply_text("Верно! Напиши /quiz, чтобы получить следующий вопрос.")
    else:
        update.message.reply_text(
            f"Неверно.\nПравильный ответ: {correct_answer}\n\n"
            "Напиши /quiz, чтобы попробовать ещё."
        )

    context.user_data["current_answer"] = None


def main() -> None:
    load_dotenv()

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logger.setLevel(logging.INFO)

    tg_token = os.environ["TG_TOKEN"]

    questions = load_questions("questions.json")

    updater = Updater(tg_token, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.bot_data["questions"] = questions

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("quiz", quiz))

    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_answer))

    logger.info("Quiz bot started")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
