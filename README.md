# Black Fox Booking Bot (демо-проєкт)

Telegram-бот для запису в барбершоп.

Клієнт обирає послугу, майстра, день і час, підтверджує запис.
Адмін отримує сповіщення, записи зберігаються у bookings.json.
Зайняті слоти іншим клієнтам не показуються.

Демо-лендінг: https://black-fox-demo.netlify.app

## Запуск
1. Створи бота в @BotFather і отримай токен
2. Скопіюй `.env.example` у `.env` і заповни токен та свій Telegram ID
3. pip install -r requirements.txt
4. python bot.py

/report і автозвіт щопонеділка для власника.

Стек: Python, aiogram 3.
