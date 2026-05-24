from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config import ADMIN_ID


def main_keyboard(user_id=None):
    buttons = [
        [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="🎁 Бонус")],
        [KeyboardButton(text="👥 Пригласить"), KeyboardButton(text="💸 Вывод")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="ℹ️ Помощь")],
    ]
    if user_id and user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="🛠️ Админ панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def admin_keyboard():
    buttons = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📢 Рассылка")],
        [KeyboardButton(text="📡 Каналы"), KeyboardButton(text="🔨 Забанить")],
        [KeyboardButton(text="✅ Разбанить"), KeyboardButton(text="🏠 Главная")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def manage_channels_keyboard(channels):
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 Удалить {ch}",
            callback_data=f"del_channel:{ch}"
        )])
    buttons.append([InlineKeyboardButton(
        text="➕ Добавить канал",
        callback_data="add_channel"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_withdraw_keyboard(amount):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Подтвердить вывод {amount} ₽",
            callback_data=f"confirm_wd:{amount}"
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_wd")]
    ])


def admin_withdraw_keyboard(wid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Оплачено", callback_data=f"wd_paid:{wid}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_refused:{wid}")
        ]
    ])


def subscribe_keyboard(channels):
    buttons = []
    for ch in channels:
        name = ch.replace("@", "")
        buttons.append([InlineKeyboardButton(
            text=f"📢 Подписаться на {ch}",
            url=f"https://t.me/{name}"
        )])
    buttons.append([InlineKeyboardButton(
        text="✅ Я подписался",
        callback_data="check_subscription"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
  
