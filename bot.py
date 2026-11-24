"""
Black Fox Booking — Telegram-бот запису в барбершоп (демо-проєкт).

Клієнт обирає: послугу -> майстра -> день -> час -> підтвердження.
Записи зберігаються у bookings.json, адміну приходить повідомлення.
"""
import asyncio
import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ---------- Налаштування (змінюй під свій барбершоп) ----------
SERVICES = [
    ("Чоловіча стрижка", 750),
    ("Борода", 500),
    ("Стрижка + борода", 850),
    ("Дитяча стрижка", 550),
]
MASTERS = ["Андрій", "Максим", "Денис"]
WORK_HOURS = range(10, 21)  # слоти з 10:00 до 20:00 (по одному на годину)
DAYS_AHEAD = 7
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]

BASE_DIR = Path(__file__).parent
BOOKINGS_FILE = BASE_DIR / "bookings.json"

dp = Dispatcher()
# Тимчасовий вибір кожного клієнта: {user_id: {"svc": 0, "master": 1, ...}}
choices: dict[int, dict] = {}


# ---------- Службові функції ----------
def load_env() -> None:
    """Читає токен та інші налаштування з файлу .env"""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def load_bookings() -> list[dict]:
    if BOOKINGS_FILE.exists():
        return json.loads(BOOKINGS_FILE.read_text(encoding="utf-8"))
    return []


def save_bookings(bookings: list[dict]) -> None:
    BOOKINGS_FILE.write_text(
        json.dumps(bookings, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_taken(master: str, date: str, time: str) -> bool:
    return any(
        b["master"] == master and b["date"] == date and b["time"] == time
        for b in load_bookings()
    )


def free_slots(master: str, date: str) -> list[str]:
    now = datetime.now()
    slots = []
    for hour in WORK_HOURS:
        time = f"{hour:02d}:00"
        slot_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        if slot_dt <= now:  # минулі слоти не показуємо
            continue
        if not is_taken(master, date, time):
            slots.append(time)
    return slots


def pretty_date(date: str) -> str:
    d = datetime.strptime(date, "%Y-%m-%d")
    return f"{WEEKDAYS[d.weekday()]} {d.strftime('%d.%m')}"


def build_report(days: int = 7) -> str:
    """Зведення для власника: нові записи, виручка, популярні послуги/майстри."""
    now = datetime.now()
    since = now - timedelta(days=days)
    all_bookings = load_bookings()

    recent = [
        b for b in all_bookings if datetime.fromisoformat(b["created"]) >= since
    ]
    today = now.strftime("%Y-%m-%d")
    week_end = (now + timedelta(days=days)).strftime("%Y-%m-%d")
    upcoming = [b for b in all_bookings if today <= b["date"] <= week_end]

    lines = [f"📊 Звіт за {days} днів", ""]
    lines.append(f"Нових записів: {len(recent)}")
    lines.append(f"Орієнтовна виручка: {sum(b['price'] for b in recent)} ₴")

    if recent:
        lines += ["", "Популярні послуги:"]
        for service, count in Counter(b["service"] for b in recent).most_common(3):
            lines.append(f"• {service} — {count}")
        lines += ["", "Записи по майстрах:"]
        for master, count in Counter(b["master"] for b in recent).most_common():
            lines.append(f"• {master} — {count}")

    lines += ["", f"Записів на найближчі {days} днів: {len(upcoming)}"]
    return "\n".join(lines)


# ---------- Клавіатури ----------
def services_kb():
    kb = InlineKeyboardBuilder()
    for i, (name, price) in enumerate(SERVICES):
        kb.button(text=f"{name} — {price} ₴", callback_data=f"svc:{i}")
    kb.adjust(1)
    return kb.as_markup()


def masters_kb():
    kb = InlineKeyboardBuilder()
    for i, name in enumerate(MASTERS):
        kb.button(text=name, callback_data=f"mst:{i}")
    kb.button(text="⬅ Назад", callback_data="back:svc")
    kb.adjust(1)
    return kb.as_markup()


def days_kb():
    kb = InlineKeyboardBuilder()
    today = datetime.now().date()
    for n in range(DAYS_AHEAD):
        d = (today + timedelta(days=n)).strftime("%Y-%m-%d")
        kb.button(text=pretty_date(d), callback_data=f"day:{d}")
    kb.button(text="⬅ Назад", callback_data="back:mst")
    kb.adjust(2)
    return kb.as_markup()


def times_kb(slots: list[str]):
    kb = InlineKeyboardBuilder()
    for t in slots:
        kb.button(text=t, callback_data=f"time:{t}")
    kb.button(text="⬅ Назад", callback_data="back:day")
    kb.adjust(3)
    return kb.as_markup()


def confirm_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Підтвердити", callback_data="ok")
    kb.button(text="✖ Скасувати", callback_data="cancel")
    kb.adjust(2)
    return kb.as_markup()


# ---------- Обробники ----------
@dp.message(CommandStart())
async def cmd_start(message: Message):
    choices.pop(message.from_user.id, None)
    await message.answer(
        "Вітаємо в Black Fox! 🦊\nОберіть послугу:", reply_markup=services_kb()
    )


@dp.callback_query(F.data.startswith("svc:"))
async def pick_service(call: CallbackQuery):
    choices[call.from_user.id] = {"svc": int(call.data.split(":", 1)[1])}
    await call.message.edit_text("Оберіть майстра:", reply_markup=masters_kb())
    await call.answer()


@dp.callback_query(F.data.startswith("mst:"))
async def pick_master(call: CallbackQuery):
    data = choices.get(call.from_user.id)
    if data is None:
        await call.answer("Сесія застаріла, натисніть /start", show_alert=True)
        return
    data["master"] = int(call.data.split(":", 1)[1])
    await call.message.edit_text("Оберіть день:", reply_markup=days_kb())
    await call.answer()


@dp.callback_query(F.data.startswith("day:"))
async def pick_day(call: CallbackQuery):
    data = choices.get(call.from_user.id)
    if data is None:
        await call.answer("Сесія застаріла, натисніть /start", show_alert=True)
        return
    data["date"] = call.data.split(":", 1)[1]
    slots = free_slots(MASTERS[data["master"]], data["date"])
    if not slots:
        await call.message.edit_text(
            "На цей день вільних годин немає. Оберіть інший день:",
            reply_markup=days_kb(),
        )
    else:
        await call.message.edit_text(
            f"Вільний час на {pretty_date(data['date'])}:",
            reply_markup=times_kb(slots),
        )
    await call.answer()


@dp.callback_query(F.data.startswith("time:"))
async def pick_time(call: CallbackQuery):
    data = choices.get(call.from_user.id)
    if data is None:
        await call.answer("Сесія застаріла, натисніть /start", show_alert=True)
        return
    data["time"] = call.data.split(":", 1)[1]
    name, price = SERVICES[data["svc"]]
    await call.message.edit_text(
        "Перевірте запис:\n\n"
        f"Послуга: {name} ({price} ₴)\n"
        f"Майстер: {MASTERS[data['master']]}\n"
        f"Дата: {pretty_date(data['date'])}\n"
        f"Час: {data['time']}",
        reply_markup=confirm_kb(),
    )
    await call.answer()


@dp.callback_query(F.data == "ok")
async def confirm(call: CallbackQuery):
    data = choices.get(call.from_user.id)
    if data is None or "time" not in data:
        await call.answer("Сесія застаріла, натисніть /start", show_alert=True)
        return

    master = MASTERS[data["master"]]
    # Перевіряємо ще раз: хтось міг встигнути зайняти цей час
    if is_taken(master, data["date"], data["time"]):
        await call.message.edit_text(
            "Цей час щойно зайняли. Оберіть інший:", reply_markup=times_kb(
                free_slots(master, data["date"])
            ),
        )
        await call.answer()
        return

    name, price = SERVICES[data["svc"]]
    user = call.from_user
    booking = {
        "service": name,
        "price": price,
        "master": master,
        "date": data["date"],
        "time": data["time"],
        "client": user.full_name,
        "username": user.username,
        "user_id": user.id,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    bookings = load_bookings()
    bookings.append(booking)
    save_bookings(bookings)
    choices.pop(user.id, None)

    await call.message.edit_text(
        "✅ Ви записані!\n\n"
        f"{name} — {price} ₴\n"
        f"Майстер: {master}\n"
        f"{pretty_date(data['date'])} о {data['time']}\n\n"
        "Чекаємо на вас! Щоб записатись ще раз — /start"
    )
    await call.answer()

    admin_id = os.environ.get("ADMIN_ID")
    if admin_id:
        handle = f"@{user.username}" if user.username else "без юзернейма"
        await call.bot.send_message(
            int(admin_id),
            "🆕 Новий запис\n"
            f"{name} — {price} ₴\n"
            f"Майстер: {master}\n"
            f"{pretty_date(data['date'])} о {data['time']}\n"
            f"Клієнт: {user.full_name} ({handle})",
        )


@dp.callback_query(F.data == "cancel")
async def cancel(call: CallbackQuery):
    choices.pop(call.from_user.id, None)
    await call.message.edit_text("Запис скасовано. Щоб почати знову — /start")
    await call.answer()


@dp.callback_query(F.data.startswith("back:"))
async def go_back(call: CallbackQuery):
    where = call.data.split(":", 1)[1]
    if where == "svc":
        await call.message.edit_text("Оберіть послугу:", reply_markup=services_kb())
    elif where == "mst":
        await call.message.edit_text("Оберіть майстра:", reply_markup=masters_kb())
    elif where == "day":
        await call.message.edit_text("Оберіть день:", reply_markup=days_kb())
    await call.answer()


@dp.message(Command("bookings"))
async def list_bookings(message: Message):
    """Список майбутніх записів — тільки для адміна."""
    if str(message.from_user.id) != os.environ.get("ADMIN_ID"):
        return
    today = datetime.now().strftime("%Y-%m-%d")
    upcoming = sorted(
        (b for b in load_bookings() if b["date"] >= today),
        key=lambda b: (b["date"], b["time"]),
    )
    if not upcoming:
        await message.answer("Майбутніх записів немає.")
        return
    lines = [
        f"{pretty_date(b['date'])} {b['time']} — {b['master']}: "
        f"{b['service']} ({b['client']})"
        for b in upcoming
    ]
    await message.answer("\n".join(lines))


@dp.message(Command("report"))
async def cmd_report(message: Message):
    """Звіт за тиждень на вимогу — тільки для адміна."""
    if str(message.from_user.id) != os.environ.get("ADMIN_ID"):
        return
    await message.answer(build_report())


async def weekly_report_loop(bot: Bot) -> None:
    """Щопонеділка о 9:00 надсилає адміну тижневий звіт."""
    last_sent = None
    while True:
        try:
            now = datetime.now()
            admin_id = os.environ.get("ADMIN_ID")
            if (
                admin_id
                and now.weekday() == 0
                and now.hour == 9
                and last_sent != now.date()
            ):
                await bot.send_message(int(admin_id), build_report())
                last_sent = now.date()
        except Exception as error:  # звіт не повинен ламати бота
            print("Помилка тижневого звіту:", error)
        await asyncio.sleep(60)


async def main() -> None:
    load_env()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Не знайдено BOT_TOKEN. Додай його у файл .env")
    bot = Bot(token)
    asyncio.create_task(weekly_report_loop(bot))
    print("Бот запущено. Зупинити: Ctrl+C")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
