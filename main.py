"""
ЗаработокБот — бот для заработка в Telegram
Структура идентична ADONAÏ MONEY
"""
import asyncio
import logging
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery

import db
from config import BOT_TOKEN, ADMIN_ID, MIN_WITHDRAW, REFERRALS_REQUIRED, CANAL_RETRAIT
from keyboards import (
    main_keyboard, admin_keyboard, manage_channels_keyboard,
    confirm_withdraw_keyboard, admin_withdraw_keyboard, subscribe_keyboard
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(storage=MemoryStorage())

_processing_wids: set = set()
_admin_reply_target: dict = {}


# ── STATES ──
class WithdrawState(StatesGroup):
    method = State()
    number = State()
    name = State()
    confirm = State()

class BroadcastState(StatesGroup):
    message = State()

class AddChannelState(StatesGroup):
    username = State()

class BanState(StatesGroup):
    user_id = State()

class UnbanState(StatesGroup):
    user_id = State()

class ReplyState(StatesGroup):
    waiting_reply = State()


# ── HELPERS ──
def ordinal_ru(n: int) -> str:
    if n == 1: return "1-й"
    if n == 2: return "2-й"
    if n == 3: return "3-й"
    if n == 4: return "4-й"
    return f"{n}-й"

def flouter_numero(number: str) -> str:
    chiffres = re.sub(r"\D", "", number)
    if len(chiffres) < 6:
        return number
    return chiffres[:4] + " *** ** ** " + chiffres[-2:]

async def user_in_all_channels(user_id: int, channels: list) -> bool:
    for ch in channels:
        try:
            username = ch.lstrip("@")
            member = await bot.get_chat_member(f"@{username}", user_id)
            if member.status in ("left", "kicked", "banned"):
                return False
        except Exception:
            return False
    return True

async def check_subscription(user_id: int) -> bool:
    channels = await db.get_channels()
    if not channels:
        return True
    return await user_in_all_channels(user_id, channels)


# ── /START ──
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id

    if await db.is_banned(user_id):
        return await message.answer("🚫 Вы заблокированы в этом боте.")

    args = message.text.split()
    referrer_id = None
    if len(args) > 1:
        try:
            ref = int(args[1])
            if ref != user_id:
                referrer_id = ref
        except:
            pass

    await db.get_or_create_user(user_id, referrer_id, message.from_user.language_code)

    # Проверка подписки
    channels = await db.get_channels()
    if channels and not await user_in_all_channels(user_id, channels):
        return await message.answer(
            "📢 <b>Для использования бота необходимо подписаться на наши каналы!</b>\n\n"
            "После подписки нажмите кнопку ✅",
            reply_markup=subscribe_keyboard(channels)
        )

    await message.answer(
        f"👋 Добро пожаловать в <b>ЗаработокБот</b>!\n\n"
        f"💰 Зарабатывай рубли прямо в Telegram:\n\n"
        f"🎁 Ежедневный бонус: <b>10 ₽</b>\n"
        f"👥 За каждого реферала: <b>250 ₽</b>\n"
        f"💸 Минимум вывода: <b>5 000 ₽</b>\n"
        f"👤 Нужно рефералов: <b>20 человек</b>\n\n"
        f"Выбери действие в меню 👇",
        reply_markup=main_keyboard(user_id)
    )


# ── SUBSCRIPTION CHECK ──
@dp.callback_query(F.data == "check_subscription")
async def check_sub_callback(call: CallbackQuery):
    user_id = call.from_user.id
    channels = await db.get_channels()

    if not channels or await user_in_all_channels(user_id, channels):
        await call.message.delete()
        await call.message.answer(
            "✅ <b>Подписка подтверждена!</b>\n\n"
            "Добро пожаловать в ЗаработокБот 🎉",
            reply_markup=main_keyboard(user_id)
        )
    else:
        await call.answer("❌ Вы ещё не подписались на все каналы!", show_alert=True)


# ── BALANCE ──
@dp.message(F.text == "💰 Баланс")
async def show_balance(message: Message):
    user_id = message.from_user.id
    if await db.is_banned(user_id): return

    user = await db.get_user(user_id)
    bal = await db.get_balance(user_id)
    if not user:
        return await message.answer("❌ Ошибка. Введите /start")

    await message.answer(
        f"💰 <b>Ваш баланс</b>\n\n"
        f"💵 Баланс: <b>{bal} ₽</b>\n"
        f"👥 Рефералов: <b>{user['total_referrals']}</b>\n"
        f"🎁 Бонусов получено: <b>{user['total_bonus']}</b>"
    )


# ── DAILY BONUS ──
@dp.message(F.text == "🎁 Бонус")
async def daily_bonus(message: Message):
    user_id = message.from_user.id
    if await db.is_banned(user_id): return

    if not await check_subscription(user_id):
        channels = await db.get_channels()
        return await message.answer(
            "📢 Подпишитесь на все каналы для получения бонуса!",
            reply_markup=subscribe_keyboard(channels)
        )

    today = datetime.now().strftime("%Y-%m-%d")
    success = await db.claim_daily_bonus(user_id, today)

    if success:
        bal = await db.get_balance(user_id)
        await message.answer(
            f"✅ <b>Бонус получен!</b>\n\n"
            f"💰 +10 ₽ на ваш баланс\n"
            f"💵 Новый баланс: <b>{bal} ₽</b>\n\n"
            f"Возвращайтесь завтра за новым бонусом! 🎁"
        )
    else:
        await message.answer(
            "⏰ <b>Вы уже получили бонус сегодня!</b>\n\n"
            "Возвращайтесь завтра 🌅"
        )


# ── REFERRAL ──
@dp.message(F.text == "👥 Пригласить")
async def referral(message: Message):
    user_id = message.from_user.id
    if await db.is_banned(user_id): return

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={user_id}"
    user = await db.get_user(user_id)

    await message.answer(
        f"👥 <b>Приглашайте друзей и зарабатывайте!</b>\n\n"
        f"💰 За каждого друга: <b>250 ₽</b>\n"
        f"👤 Ваших рефералов: <b>{user['total_referrals']}</b>\n\n"
        f"🔗 Ваша реферальная ссылка:\n"
        f"<code>{link}</code>\n\n"
        f"📋 Скопируйте и поделитесь с друзьями!"
    )


# ── STATS ──
@dp.message(F.text == "📊 Статистика")
async def stats(message: Message):
    user_id = message.from_user.id
    if await db.is_banned(user_id): return

    user = await db.get_user(user_id)
    bal = await db.get_balance(user_id)
    wd_count = await db.get_withdrawal_count(user_id)

    await message.answer(
        f"📊 <b>Ваша статистика</b>\n\n"
        f"💵 Баланс: <b>{bal} ₽</b>\n"
        f"👥 Рефералов: <b>{user['total_referrals']}</b>\n"
        f"🎁 Бонусов: <b>{user['total_bonus']}</b>\n"
        f"💸 Выводов: <b>{wd_count}</b>"
    )


# ── HELP ──
@dp.message(F.text == "ℹ️ Помощь")
async def help_cmd(message: Message):
    await message.answer(
        f"ℹ️ <b>Помощь</b>\n\n"
        f"💰 <b>Как заработать:</b>\n"
        f"• Ежедневный бонус: 10 ₽\n"
        f"• За реферала: 250 ₽\n\n"
        f"💸 <b>Условия вывода:</b>\n"
        f"• Минимум: 5 000 ₽\n"
        f"• Нужно: 20 рефералов\n\n"
        f"💳 <b>Способы вывода:</b>\n"
        f"• Карта МИР\n"
        f"• QIWI / YooMoney\n"
        f"• СБП\n"
        f"• Криптовалюта (USDT TRC20)\n\n"
        f"📞 Поддержка: @adonaibot1"
    )


# ── WITHDRAW ──
@dp.message(F.text == "💸 Вывод")
async def withdraw_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if await db.is_banned(user_id): return

    if not await check_subscription(user_id):
        channels = await db.get_channels()
        return await message.answer(
            "📢 Подпишитесь на все каналы!",
            reply_markup=subscribe_keyboard(channels)
        )

    user = await db.get_user(user_id)
    bal = await db.get_balance(user_id)
    total_referrals = user["total_referrals"] if user else 0

    if bal < MIN_WITHDRAW:
        return await message.answer(
            f"❌ Недостаточно средств.\n"
            f"Минимум: <b>{MIN_WITHDRAW} ₽</b>\n"
            f"Ваш баланс: <b>{bal} ₽</b>"
        )

    withdrawal_count = await db.get_withdrawal_count(user_id)
    prochain = withdrawal_count + 1

    if withdrawal_count == 0:
        if total_referrals < REFERRALS_REQUIRED:
            return await message.answer(
                f"❌ <b>Вывод недоступен</b>\n\n"
                f"📋 <b>{ordinal_ru(prochain)} вывод</b>\n"
                f"👥 Рефералов: <b>{total_referrals}/{REFERRALS_REQUIRED}</b>\n"
                f"⏳ Нужно ещё: <b>{REFERRALS_REQUIRED - total_referrals} человек</b>\n\n"
                f"Пригласите <b>{REFERRALS_REQUIRED} человек</b> для первого вывода."
            )

    elif 1 <= withdrawal_count <= 3:
        referrals_at_last = await db.get_referrals_at_last_withdrawal(user_id)
        new_since_last = total_referrals - referrals_at_last
        snapshots = await db.get_all_withdrawal_snapshots(user_id)

        historique = ""
        for i, snap in enumerate(snapshots):
            if i == 0:
                historique += f"👥 Рефералов 1-й вывод: <b>{snap}</b>\n"
            else:
                prev = snapshots[i - 1]
                diff = snap - prev
                historique += f"👥 Рефералов {ordinal_ru(i + 1)} вывод: <b>{diff}</b>\n"

        if new_since_last < REFERRALS_REQUIRED:
            return await message.answer(
                f"❌ <b>Вывод недоступен</b>\n\n"
                f"📋 История рефералов:\n{historique}"
                f"👥 Рефералов {ordinal_ru(prochain)} вывод: <b>{new_since_last}/{REFERRALS_REQUIRED}</b>\n"
                f"⏳ Нужно ещё: <b>{REFERRALS_REQUIRED - new_since_last} человек</b>\n\n"
                f"Пригласите <b>{REFERRALS_REQUIRED} новых</b> с последнего вывода."
            )

    pending = await db.count_pending_withdrawals(user_id)
    if pending > 0:
        return await message.answer("⏳ У вас уже есть заявка на рассмотрении.")

    await message.answer(
        "💳 Выберите способ вывода:\n\n"
        "Напишите один из вариантов:\n"
        "<i>Карта МИР, QIWI, YooMoney, СБП, USDT TRC20</i>\n\n"
        "Отправьте /cancel для отмены."
    )
    await state.set_state(WithdrawState.method)


@dp.message(WithdrawState.method)
async def get_method(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("❌ Вывод отменён.", reply_markup=main_keyboard(message.from_user.id))
    method = message.text.strip()
    if len(method) > 50:
        return await message.answer("❌ Слишком длинный ответ (макс. 50 символов).")
    await state.update_data(method=method)
    await message.answer(
        "📱 Введите номер/адрес для вывода:\n"
        "Пример: <code>+7 999 123 45 67</code>"
    )
    await state.set_state(WithdrawState.number)


@dp.message(WithdrawState.number)
async def get_number(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("❌ Вывод отменён.", reply_markup=main_keyboard(message.from_user.id))
    number = message.text.strip()
    await state.update_data(number=number)
    await message.answer("👤 Введите имя получателя:")
    await state.set_state(WithdrawState.name)


@dp.message(WithdrawState.name)
async def get_name(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("❌ Вывод отменён.", reply_markup=main_keyboard(message.from_user.id))
    name = message.text.strip()
    data = await state.get_data()
    user_id = message.from_user.id
    bal = await db.get_balance(user_id)

    if bal < MIN_WITHDRAW:
        await state.clear()
        return await message.answer("❌ Недостаточно средств. Вывод отменён.")

    await state.update_data(name=name)
    await message.answer(
        f"📋 <b>ПОДТВЕРЖДЕНИЕ</b>\n\n"
        f"💰 Сумма: <b>{bal} ₽</b>\n"
        f"💳 Способ: <b>{data['method']}</b>\n"
        f"📱 Реквизиты: <b>{data['number']}</b>\n"
        f"👤 Имя: <b>{name}</b>\n\n"
        f"Подтвердить?",
        reply_markup=confirm_withdraw_keyboard(bal)
    )
    await state.set_state(WithdrawState.confirm)


@dp.callback_query(WithdrawState.confirm, F.data.startswith("confirm_wd:"))
async def confirm_withdraw(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    await state.clear()
    bal = await db.get_balance(user_id)

    if bal < MIN_WITHDRAW:
        return await call.message.answer("❌ Недостаточно средств.")

    user = await db.get_user(user_id)
    total_referrals = user["total_referrals"] if user else 0
    withdrawal_count = await db.get_withdrawal_count(user_id)
    numero_retrait = withdrawal_count + 1

    snapshots = await db.get_all_withdrawal_snapshots(user_id)
    historique_admin = ""
    for i, snap in enumerate(snapshots):
        if i == 0:
            historique_admin += f"👥 Рефералов 1-й вывод: <b>{snap}</b>\n"
        else:
            prev = snapshots[i - 1]
            diff = snap - prev
            historique_admin += f"👥 Рефералов {ordinal_ru(i + 1)} вывод: <b>{diff}</b>\n"

    referrals_at_last = await db.get_referrals_at_last_withdrawal(user_id)
    new_since_last = total_referrals - referrals_at_last if withdrawal_count > 0 else total_referrals

    try:
        wid = await db.create_withdrawal(
            user_id=user_id,
            amount=bal,
            method=data["method"],
            number=data["number"],
            name=data["name"]
        )
    except Exception as e:
        logger.error(f"Ошибка create_withdrawal: {e}")
        return await call.message.answer("❌ Техническая ошибка. Попробуйте позже.")

    try:
        await bot.send_message(
            ADMIN_ID,
            f"📥 <b>НОВАЯ ЗАЯВКА #{wid}</b>\n\n"
            f"👤 ID: <code>{user_id}</code>\n"
            f"💰 Сумма: <b>{bal} ₽</b>\n"
            f"💳 Способ: {data['method']}\n"
            f"📱 Реквизиты: {data['number']}\n"
            f"👤 Имя: {data['name']}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{historique_admin}"
            f"👥 Рефералов {ordinal_ru(numero_retrait)} вывод: <b>{new_since_last}</b>\n"
            f"📊 Всего рефералов: <b>{total_referrals}</b>\n"
            f"🔢 Номер вывода: <b>{ordinal_ru(numero_retrait)}</b>",
            reply_markup=admin_withdraw_keyboard(wid)
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить админа: {e}")

    await call.message.answer("⏳ Заявка отправлена! Обработка в течение 1-24 часов.")
    await call.answer()


@dp.callback_query(WithdrawState.confirm, F.data == "cancel_wd")
async def cancel_withdraw(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ Вывод отменён.", reply_markup=main_keyboard(call.from_user.id))
    await call.answer()


# ── ADMIN: PAY ──
@dp.callback_query(F.data.startswith("wd_paid:"))
async def wd_paid(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("🚫 Только для администратора.", show_alert=True)
    wid = int(call.data.split(":")[1])
    if wid in _processing_wids:
        return await call.answer("⏳ Уже обрабатывается.", show_alert=True)
    _processing_wids.add(wid)
    try:
        row = await db.get_withdrawal(wid)
        if not row or row["status"] != "pending":
            return await call.answer(f"⚠️ Статус: {row['status'] if row else 'не найдено'}", show_alert=True)

        await db.pay_withdrawal(wid)

        try:
            await bot.send_message(
                row["user_id"],
                "✅ Ваш вывод подтверждён и оплачен! 💰\n"
                "Проверьте ваши реквизиты."
            )
        except Exception:
            pass

        try:
            numero_floute = flouter_numero(row["number"])
            await bot.send_message(
                CANAL_RETRAIT,
                f"✅ <b>ВЫПЛАТА ПРОИЗВЕДЕНА</b>\n\n"
                f"💰 Сумма: <b>{row['amount']} ₽</b>\n"
                f"💳 Способ: <b>{row['method']}</b>\n"
                f"📱 Реквизиты: <b>{numero_floute}</b>\n"
                f"👤 Имя: <b>{row['name']}</b>\n\n"
                f"🤖 Через @zarabotok70_bot\n"
                f"📲 Присоединяйся и зарабатывай!"
            )
        except Exception as e:
            logger.error(f"Не удалось опубликовать в канал: {e}")

        await call.message.edit_text(
            call.message.text + "\n\n✅ <b>ОПЛАЧЕНО</b>",
            reply_markup=None
        )
        await call.answer("Оплачено ✅")
    except Exception as e:
        logger.error(f"Ошибка wd_paid: {e}")
        await call.answer("❌ Техническая ошибка.", show_alert=True)
    finally:
        _processing_wids.discard(wid)


# ── ADMIN: REFUSE ──
@dp.callback_query(F.data.startswith("wd_refused:"))
async def wd_refused(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("🚫 Только для администратора.", show_alert=True)
    wid = int(call.data.split(":")[1])
    if wid in _processing_wids:
        return await call.answer("⏳ Уже обрабатывается.", show_alert=True)
    _processing_wids.add(wid)
    try:
        success = await db.refuse_withdrawal(wid)
        if not success:
            return await call.answer("⚠️ Уже обработано.", show_alert=True)
        row = await db.get_withdrawal(wid)
        try:
            await bot.send_message(
                row["user_id"],
                "❌ Ваша заявка отклонена. Баланс восстановлен.\n"
                "Свяжитесь с поддержкой: @adonaibot1"
            )
        except Exception:
            pass
        await call.message.edit_text(
            call.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>",
            reply_markup=None
        )
        await call.answer("Отклонено ✅")
    except Exception as e:
        logger.error(f"Ошибка wd_refused: {e}")
        await call.answer("❌ Техническая ошибка.", show_alert=True)
    finally:
        _processing_wids.discard(wid)


# ── ADMIN PANEL ──
@dp.message(F.text == "🛠️ Админ панель")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID: return
    s = await db.get_stats()
    await message.answer(
        f"🛠️ <b>АДМИН ПАНЕЛЬ</b>\n\n"
        f"👥 Пользователей: <b>{s['users']}</b>\n"
        f"⏳ Ожидают: <b>{s['pending']}</b>\n"
        f"💸 Всего выводов: <b>{s['total_withdrawals']}</b>\n"
        f"💰 Общий баланс: <b>{s['total_balance']} ₽</b>",
        reply_markup=admin_keyboard()
    )


@dp.message(F.text == "🏠 Главная")
async def go_home(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Главное меню 👇", reply_markup=main_keyboard(message.from_user.id))


@dp.message(F.text == "📊 Статистика", F.from_user.id == ADMIN_ID)
async def admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID: return
    s = await db.get_stats()
    await message.answer(
        f"📈 <b>СТАТИСТИКА</b>\n\n"
        f"👥 Пользователей: <b>{s['users']}</b>\n"
        f"💸 Выводов всего: <b>{s['total_withdrawals']}</b>\n"
        f"⏳ Ожидают: <b>{s['pending']}</b>\n"
        f"💰 Баланс в системе: <b>{s['total_balance']} ₽</b>"
    )


# ── BROADCAST ──
@dp.message(F.text == "📢 Рассылка")
async def broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("📢 Отправьте сообщение для рассылки.\n\nОтправьте /cancel для отмены.")
    await state.set_state(BroadcastState.message)


@dp.message(BroadcastState.message)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    user_ids = await db.get_all_user_ids()
    success = failed = 0
    status_msg = await message.answer(f"⏳ Отправка {len(user_ids)} пользователям...")
    for uid in user_ids:
        try:
            await message.copy_to(uid)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await status_msg.edit_text(
        f"📢 <b>ГОТОВО</b>\n\n✅ Отправлено: {success}\n❌ Ошибок: {failed}"
    )


# ── MANAGE CHANNELS ──
@dp.message(F.text == "📡 Каналы")
async def manage_channels(message: Message):
    if message.from_user.id != ADMIN_ID: return
    channels = await db.get_channels()
    channels_text = "\n".join([f"• {ch}" for ch in channels]) or "Нет каналов."
    await message.answer(
        f"📡 <b>КАНАЛЫ</b>\n\n{channels_text}",
        reply_markup=manage_channels_keyboard(channels)
    )


@dp.callback_query(F.data == "add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await call.message.answer(
        "➕ Отправьте username канала.\n"
        "Пример: <code>@mycanal</code>\n\n"
        "Отправьте /cancel для отмены."
    )
    await state.set_state(AddChannelState.username)
    await call.answer()


@dp.message(AddChannelState.username)
async def add_channel_save(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    username = message.text.strip()
    await state.clear()
    if not username.startswith("@"):
        return await message.answer("❌ Username должен начинаться с @")
    added = await db.add_channel(username)
    await message.answer(
        f"✅ Канал <b>{username}</b> добавлен!" if added
        else f"⚠️ <b>{username}</b> уже существует."
    )


@dp.callback_query(F.data.startswith("del_channel:"))
async def delete_channel(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    username = call.data.split(":", 1)[1]
    await db.delete_channel(username)
    channels = await db.get_channels()
    channels_text = "\n".join([f"• {ch}" for ch in channels]) or "Нет каналов."
    await call.message.edit_text(
        f"🗑 <b>{username}</b> удалён.\n\n📡 Каналы:\n{channels_text}",
        reply_markup=manage_channels_keyboard(channels) if channels else None
    )
    await call.answer("Удалено ✅")


# ── BAN / UNBAN ──
@dp.message(F.text == "🔨 Забанить")
async def ban_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🔨 Отправьте ID пользователя для бана.")
    await state.set_state(BanState.user_id)


@dp.message(BanState.user_id)
async def ban_execute(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if not message.text.strip().isdigit():
        return await message.answer("❌ Неверный ID.")
    target = int(message.text.strip())
    await db.ban_user(target)
    try:
        await bot.send_message(target, "🚫 Вы заблокированы в этом боте.")
    except Exception:
        pass
    await message.answer(f"🔨 Пользователь <code>{target}</code> заблокирован.")


@dp.message(F.text == "✅ Разбанить")
async def unban_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("✅ Отправьте ID пользователя для разбана.")
    await state.set_state(UnbanState.user_id)


@dp.message(UnbanState.user_id)
async def unban_execute(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if not message.text.strip().isdigit():
        return await message.answer("❌ Неверный ID.")
    target = int(message.text.strip())
    await db.unban_user(target)
    try:
        await bot.send_message(target, "✅ Вы разблокированы!")
    except Exception:
        pass
    await message.answer(f"✅ Пользователь <code>{target}</code> разблокирован.")


# ── FIX SNAPSHOTS ──
@dp.message(Command("fix_snapshots"))
async def fix_snapshots(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⏳ Исправление снимков...")
    try:
        count = await db.fix_snapshots_for_old_users()
        await message.answer(
            f"✅ <b>Готово!</b>\n\n"
            f"👥 Исправлено пользователей: <b>{count}</b>\n\n"
            f"Теперь им нужно пригласить <b>20 новых</b> для следующего вывода."
        )
    except Exception as e:
        logger.error(f"Ошибка fix_snapshots: {e}")
        await message.answer("❌ Техническая ошибка.")


# ── USER INFO ──
@dp.message(Command("userinfo"))
async def user_info(message: Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split(" ", 1)[1])
    except Exception:
        return await message.answer("❌ Формат: /userinfo <ID>")
    user = await db.get_user(target_id)
    if not user:
        return await message.answer("❌ Пользователь не найден.")
    await message.answer(
        f"👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"🆔 ID: <code>{target_id}</code>\n"
        f"💰 Баланс: <b>{user['balance']} ₽</b>\n"
        f"👥 Рефералов: <b>{user['total_referrals']}</b>\n"
        f"🎁 Бонусов: <b>{user['total_bonus']}</b>\n"
        f"🚫 Забанен: {'Да' if user['is_banned'] else 'Нет'}"
    )


# ── FORWARD TO ADMIN ──
@dp.message(F.from_user.id != ADMIN_ID)
async def forward_to_admin(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=f"↩️ Ответить {message.from_user.first_name}",
                callback_data=f"reply_to:{message.from_user.id}"
            )
        ]])
        await bot.send_message(
            ADMIN_ID,
            f"📩 <b>Сообщение от {message.from_user.first_name}</b>\n"
            f"👤 ID: <code>{message.from_user.id}</code>",
            reply_markup=kb
        )
        await message.forward(ADMIN_ID)
    except Exception as e:
        logger.error(f"Не удалось переслать: {e}")


@dp.callback_query(F.data.startswith("reply_to:"))
async def reply_to_user_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    target_id = int(call.data.split(":")[1])
    _admin_reply_target[ADMIN_ID] = target_id
    await call.message.answer(
        f"↩️ Отвечаете пользователю <code>{target_id}</code>\n\n"
        f"Отправьте сообщение или /cancel для отмены."
    )
    await state.set_state(ReplyState.waiting_reply)
    await call.answer()


@dp.message(ReplyState.waiting_reply)
async def reply_to_user_send(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    target_id = _admin_reply_target.get(ADMIN_ID)
    if not target_id:
        return await message.answer("❌ Цель не найдена.")
    try:
        await bot.send_message(target_id, "📨 <b>Сообщение от администратора:</b>")
        await message.copy_to(target_id)
        await message.answer("✅ Ответ отправлен.")
    except Exception as e:
        logger.error(f"Не удалось ответить {target_id}: {e}")
        await message.answer("❌ Не удалось отправить. Пользователь мог заблокировать бота.")
    finally:
        _admin_reply_target.pop(ADMIN_ID, None)


# ── MAIN ──
async def main():
    await db.init_db()
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
