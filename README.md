# Quizbots: Telegram + VK 

Проект содержит двух ботов:
- Telegram бот
- ВК бот  

Оба используют общий набор вопросов для викторины и Redis для хранения прогресса пользователя.

## Установка
Установи зависимости:
```
pip install -r requirements.txt
```
Настрой переменные окружения в .env:
```
TG_TOKEN=токен_telegram_бота
VK_TOKEN=токен_группы_вк
REDIS_URL=redis://:пароль@host:port/0
```

## Запуск ботов:
Выполнить команду в консоли:

Телеграм: 
```python tg_bot.py```

ВКонтакте: 
```python vk_bot.py```

## Демо
- Telegram-бот: https://t.me/Quizy_game_bot
- VK-бот: https://vk.me/club235875964
