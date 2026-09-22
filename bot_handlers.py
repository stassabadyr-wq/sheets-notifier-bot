"""
Обработчики бота: FSM для добавления таблиц, работа с Яндекс Таблицами,
уведомления, админ-панель.
"""
import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from config import ADMIN_ID, CHECK_INTERVAL
from database import (
    save_user,
    add_tracking,
    get_user_trackings,
    get_tracking,
    get_all_active_trackings,
    update_tracking_last_row,
    toggle_tracking,
    delete_tracking,
    is_row_sent,
    mark_row_sent,
    get_stats,
)
from keyboards import (
    main_menu,
    cancel_kb,
    trackings_list_kb,
    tracking_actions_kb,
    confirm_delete_kb,
    back_to_menu_kb,
    admin_menu,
    back_to_admin_kb,
)
from yandex_sheets import (
    get_new_rows,
    download_yandex_table,
    extract_folder_url,
    normalize_file_path,
)

log = logging.getLogger(__name__)
router = Router()


# --- FSM ---

class AddTracking(StatesGroup):
    waiting_url = State()
    waiting_file_path = State()
    waiting_name = State()
    waiting_last_row = State()


# --- ВСПОМОГАТЕЛЬНЫЕ ---

def _is_admin(user_id: int) -> bool:
    return ADMIN_ID is not None and user_id == ADMIN_ID


def _format_row(row: dict) -> str:
    """Форматирует строку таблицы для уведомления."""
    lines = []
    for key, value in row.items():
        if key.startswith("_"):
            continue
        if value:
            lines.append(f"• <b>{key}:</b> {value}")
    return "\n".join(lines) if lines else "— пустая строка —"


async def _send_notification(bot: Bot, user_id: int, tracking: dict, row: dict):
    """Отправляет уведомление о новой строке."""
    text = (
        f"🔔 <b>Новая строка в таблице</b>\n\n"
        f"📋 <b>{tracking['sheet_name']}</b>\n"
        f"📊 Строка №{row.get('_row_number', '?')}\n\n"
        f"{_format_row(row)}\n\n"
        f"🔗 <a href=\"{tracking['public_key']}\">Открыть папку</a>"
    )

    try:
        await bot.send_message(
            user_id,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.error(f"Ошибка отправки уведомления: {e}", exc_info=True)


# --- КОМАНДЫ ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await save_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    await message.answer(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"Я — бот-уведомитель для <b>Яндекс Таблиц</b>.\n\n"
        f"<b>Что я делаю:</b>\n"
        f"• Слежу за XLSX-файлом на Яндекс Диске\n"
        f"• Присылаю уведомление при появлении новой строки\n"
        f"• Работаю каждые {CHECK_INTERVAL // 60} минут\n\n"
        f"<b>Как настроить:</b>\n"
        f"1. Создайте папку на Яндекс Диске\n"
        f"2. Загрузите в неё XLSX-файл\n"
        f"3. Сделайте папку публичной (доступ по ссылке)\n"
        f"4. Отправьте ссылку мне через <b>➕ Добавить таблицу</b>\n\n"
        f"Жмите <b>➕ Добавить таблицу</b>, чтобы начать!",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "❓ <b>Как это работает</b>\n\n"
        "<b>1. Подготовьте Яндекс Диск</b>\n"
        "• Откройте Яндекс Диск → создайте папку\n"
        "• Загрузите в неё XLSX-файл (например, <code>Заявки.xlsx</code>)\n"
        "• Нажмите <b>Поделиться</b> → <b>Скопировать ссылку</b>\n\n"
        "<b>2. Добавьте таблицу в бота</b>\n"
        "• Нажмите <b>➕ Добавить таблицу</b>\n"
        "• Отправьте ссылку на папку (<code>https://disk.yandex.ru/d/...</code>)\n"
        "• Укажите имя файла (например, <code>Заявки.xlsx</code>)\n"
        "• Укажите название (например, «Заявки»)\n"
        "• Укажите номер последней строки (или 1)\n\n"
        "<b>3. Получайте уведомления</b>\n"
        f"• Бот проверяет файл каждые {CHECK_INTERVAL // 60} минут\n"
        "• При новой строке → уведомление в Telegram\n\n"
        "<b>Важно:</b> чтобы данные обновлялись, файл на Яндекс Диске "
        "нужно периодически перезаливать (если вы редактируете его "
        "в другом месте).\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/help — эта справка\n"
        "/cancel — отменить действие",
        reply_markup=main_menu(),
    )


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.", reply_markup=main_menu())


@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Отменено.")
    await call.message.answer("Возвращаю в меню.", reply_markup=main_menu())
    await call.answer()


# --- ДОБАВЛЕНИЕ ТАБЛИЦЫ ---

@router.message(F.text == "➕ Добавить таблицу")
async def add_tracking_start(message: Message, state: FSMContext):
    await state.set_state(AddTracking.waiting_url)
    await message.answer(
        "📋 <b>Шаг 1 из 4</b>\n\n"
        "Отправьте <b>ссылку на папку</b> Яндекс Диска.\n\n"
        "<i>Как получить:</i>\n"
        "1. Откройте Яндекс Диск\n"
        "2. Создайте папку и загрузите в неё XLSX-файл\n"
        "3. Нажмите <b>Поделиться</b> на папке\n"
        "4. Включите доступ по ссылке\n"
        "5. Скопируйте ссылку\n\n"
        "<i>Пример: https://disk.yandex.ru/d/xxxxx</i>",
        reply_markup=cancel_kb(),
    )


@router.message(AddTracking.waiting_url, F.text, ~F.text.startswith("/"))
async def add_tracking_url(message: Message, state: FSMContext):
    url = message.text.strip()

    folder_url = extract_folder_url(url)
    if not folder_url:
        await message.answer(
            "❌ Это не похоже на ссылку на папку Яндекс Диска.\n\n"
            "Ссылка должна содержать <code>/d/</code> и начинаться с "
            "<code>https://disk.yandex.ru/</code>\n\n"
            "Попробуйте ещё раз или /cancel.",
            parse_mode="HTML",
        )
        return

    await state.update_data(public_key=folder_url)
    await state.set_state(AddTracking.waiting_file_path)

    await message.answer(
        "✅ Ссылка сохранена.\n\n"
        "📋 <b>Шаг 2 из 4</b>\n\n"
        "Введите <b>имя файла</b> внутри папки.\n\n"
        "<i>Например: Книга1.xlsx или Заявки.xlsx</i>\n\n"
        "⚠️ Имя должно быть точным, включая расширение <code>.xlsx</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(AddTracking.waiting_file_path, F.text, ~F.text.startswith("/"))
async def add_tracking_file(message: Message, state: FSMContext):
    filename = message.text.strip()
    file_path = normalize_file_path(filename)

    data = await state.get_data()
    public_key = data.get("public_key")

    msg = await message.answer("⏳ Проверяю доступ к файлу…")

    rows = await asyncio.to_thread(
        download_yandex_table, public_key, file_path
    )

    if not rows:
        await msg.edit_text(
            "❌ <b>Не удалось прочитать файл.</b>\n\n"
            "Возможные причины:\n"
            "• Неверное имя файла (проверьте расширение)\n"
            "• Файл не XLSX (только XLSX поддерживается)\n"
            "• Папка не публичная\n"
            "• Файл пустой\n\n"
            "Попробуйте снова или /cancel."
        )
        return

    headers = rows[0] if rows else []
    headers_text = ", ".join([h for h in headers if h][:5])
    if len(headers) > 5:
        headers_text += "…"

    await msg.edit_text(
        f"✅ <b>Файл доступен!</b>\n\n"
        f"📊 Строк: <b>{len(rows)}</b>\n"
        f"📋 Колонки: <i>{headers_text}</i>\n\n"
        f"<b>Шаг 3 из 4.</b> Как назвать эту таблицу?\n\n"
        f"<i>Например: «Заявки», «Заказы», «Клиенты»</i>"
    )
    await state.update_data(file_path=file_path)
    await state.set_state(AddTracking.waiting_name)


@router.message(AddTracking.waiting_name, F.text, ~F.text.startswith("/"))
async def add_tracking_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Название должно быть от 2 до 50 символов.")
        return

    await state.update_data(sheet_name=name)
    await state.set_state(AddTracking.waiting_last_row)

    await message.answer(
        f"✅ Название: <b>{name}</b>\n\n"
        f"<b>Шаг 4 из 4.</b> С какой строки начать отслеживание?\n\n"
        f"• Введите <b>1</b> — чтобы получать ВСЕ новые строки\n"
        f"• Введите <b>номер текущей последней строки</b> — чтобы "
        f"пропустить уже существующие данные\n\n"
        f"<i>Например: 1 или 6</i>",
        reply_markup=cancel_kb(),
    )


@router.message(AddTracking.waiting_last_row, F.text, ~F.text.startswith("/"))
async def add_tracking_last_row(message: Message, state: FSMContext, bot: Bot):
    try:
        last_row = int(message.text.strip())
        if last_row < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число (например, 1 или 6).")
        return

    data = await state.get_data()
    await state.clear()

    tracking_id = await add_tracking(
        user_id=message.from_user.id,
        public_key=data["public_key"],
        file_path=data["file_path"],
        sheet_name=data["sheet_name"],
        last_row=last_row,
    )

    await message.answer(
        f"✅ <b>Таблица добавлена!</b>\n\n"
        f"📋 Название: <b>{data['sheet_name']}</b>\n"
        f"📄 Файл: <code>{data['file_path']}</code>\n"
        f"🆔 ID отслеживания: <b>#{tracking_id}</b>\n"
        f"📊 Начинаю со строки: <b>{last_row}</b>\n\n"
        f"Теперь я буду присылать уведомления при появлении новых строк. "
        f"Проверка — каждые {CHECK_INTERVAL // 60} минут.",
        reply_markup=main_menu(),
    )
    log.info(f"Пользователь {message.from_user.id} добавил tracking #{tracking_id}")


# --- МОИ ТАБЛИЦЫ ---

@router.message(F.text == "📋 Мои таблицы")
async def my_trackings(message: Message):
    trackings = await get_user_trackings(message.from_user.id)

    if not trackings:
        await message.answer(
            "📭 У вас пока нет отслеживаемых таблиц.\n\n"
            "Нажмите <b>➕ Добавить таблицу</b>, чтобы начать.",
            reply_markup=main_menu(),
        )
        return

    await message.answer(
        f"📋 <b>Ваши таблицы</b> ({len(trackings)})\n\n"
        f"🟢 — активна, 🔴 — на паузе\n"
        f"Нажмите на таблицу, чтобы открыть настройки:",
        reply_markup=trackings_list_kb(trackings),
    )


@router.callback_query(F.data == "back_to_list")
async def cb_back_to_list(call: CallbackQuery):
    trackings = await get_user_trackings(call.from_user.id)
    if not trackings:
        await call.message.edit_text("📭 Нет таблиц.")
        await call.answer()
        return

    await call.message.edit_text(
        f"📋 <b>Ваши таблицы</b> ({len(trackings)})\n\n"
        f"🟢 — активна, 🔴 — на паузе",
        reply_markup=trackings_list_kb(trackings),
    )
    await call.answer()


# --- НАСТРОЙКИ КОНКРЕТНОЙ ТАБЛИЦЫ ---

@router.callback_query(F.data.startswith("track:"))
async def cb_track_info(call: CallbackQuery):
    tracking_id = int(call.data.split(":")[1])
    tracking = await get_tracking(tracking_id)

    if not tracking or tracking["user_id"] != call.from_user.id:
        await call.answer("Не найдено", show_alert=True)
        return

    status = "🟢 Активна" if tracking["is_active"] else "🔴 На паузе"

    text = (
        f"📋 <b>{tracking['sheet_name']}</b>\n\n"
        f"🆔 ID: <b>#{tracking['id']}</b>\n"
        f"📄 Файл: <code>{tracking['file_path']}</code>\n"
        f"📊 Статус: <b>{status}</b>\n"
        f"📈 Последняя строка: <b>{tracking['last_row']}</b>\n"
        f"🕒 Создана: <code>{tracking['created_at'][:16]}</code>\n\n"
        f"🔗 <a href=\"{tracking['public_key']}\">Открыть папку</a>"
    )

    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=tracking_actions_kb(tracking_id, bool(tracking["is_active"])),
        disable_web_page_preview=True,
    )
    await call.answer()


@router.callback_query(F.data.startswith("toggle:"))
async def cb_toggle(call: CallbackQuery):
    tracking_id = int(call.data.split(":")[1])
    tracking = await get_tracking(tracking_id)

    if not tracking or tracking["user_id"] != call.from_user.id:
        await call.answer("Не найдено", show_alert=True)
        return

    new_state = await toggle_tracking(tracking_id)
    status = "включена" if new_state else "поставлена на паузу"
    await call.answer(f"Таблица {status}", show_alert=True)

    tracking = await get_tracking(tracking_id)
    status_text = "🟢 Активна" if tracking["is_active"] else "🔴 На паузе"

    text = (
        f"📋 <b>{tracking['sheet_name']}</b>\n\n"
        f"🆔 ID: <b>#{tracking['id']}</b>\n"
        f"📄 Файл: <code>{tracking['file_path']}</code>\n"
        f"📊 Статус: <b>{status_text}</b>\n"
        f"📈 Последняя строка: <b>{tracking['last_row']}</b>\n\n"
        f"🔗 <a href=\"{tracking['public_key']}\">Открыть папку</a>"
    )

    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=tracking_actions_kb(tracking_id, bool(tracking["is_active"])),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("check:"))
async def cb_check_now(call: CallbackQuery, bot: Bot):
    tracking_id = int(call.data.split(":")[1])
    tracking = await get_tracking(tracking_id)

    if not tracking or tracking["user_id"] != call.from_user.id:
        await call.answer("Не найдено", show_alert=True)
        return

    await call.answer("Проверяю…")

    rows = await asyncio.to_thread(
        download_yandex_table, tracking["public_key"], tracking["file_path"]
    )

    if not rows:
        await call.message.answer(
            "❌ Не удалось прочитать файл. Проверьте доступ."
        )
        return

    total_rows = len(rows)
    last_row = tracking["last_row"]
    new_count = max(0, total_rows - last_row)

    await call.message.answer(
        f"📊 <b>Результат проверки</b>\n\n"
        f"📋 Таблица: <b>{tracking['sheet_name']}</b>\n"
        f"📄 Файл: <code>{tracking['file_path']}</code>\n"
        f"📈 Всего строк: <b>{total_rows}</b>\n"
        f"📌 Последняя обработанная: <b>{last_row}</b>\n"
        f"🆕 Новых строк: <b>{new_count}</b>"
    )


@router.callback_query(F.data.startswith("delete:"))
async def cb_delete_confirm(call: CallbackQuery):
    tracking_id = int(call.data.split(":")[1])
    tracking = await get_tracking(tracking_id)

    if not tracking or tracking["user_id"] != call.from_user.id:
        await call.answer("Не найдено", show_alert=True)
        return

    await call.message.edit_text(
        f"🗑 <b>Удалить таблицу?</b>\n\n"
        f"📋 <b>{tracking['sheet_name']}</b>\n\n"
        f"Это действие нельзя отменить. История отправленных строк "
        f"также будет удалена.",
        reply_markup=confirm_delete_kb(tracking_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_delete(call: CallbackQuery):
    tracking_id = int(call.data.split(":")[1])
    tracking = await get_tracking(tracking_id)

    if not tracking or tracking["user_id"] != call.from_user.id:
        await call.answer("Не найдено", show_alert=True)
        return

    await delete_tracking(tracking_id)
    await call.answer("Удалено", show_alert=True)

    trackings = await get_user_trackings(call.from_user.id)
    if trackings:
        await call.message.edit_text(
            f"📋 <b>Ваши таблицы</b> ({len(trackings)})\n\n"
            f"🟢 — активна, 🔴 — на паузе",
            reply_markup=trackings_list_kb(trackings),
        )
    else:
        await call.message.edit_text("📭 У вас больше нет таблиц.")
        await call.message.answer(
            "Возвращаю в меню.",
            reply_markup=main_menu(),
        )


@router.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(call: CallbackQuery):
    await call.message.edit_text("Главное меню.")
    await call.message.answer("Выберите действие:", reply_markup=main_menu())
    await call.answer()


# --- АДМИНКА ---

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Команда только для администратора.")
        return

    await message.answer(
        "🛠 <b>Админ-панель</b>\n\nВыберите раздел:",
        reply_markup=admin_menu(),
    )


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    await call.message.edit_text(
        "🛠 <b>Админ-панель</b>\n\nВыберите раздел:",
        reply_markup=admin_menu(),
    )
    await call.answer()


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    stats = await get_stats()
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"📋 Всего отслеживаний: <b>{stats['trackings']}</b>\n"
        f"🟢 Активных: <b>{stats['active']}</b>\n"
        f"🔔 Отправлено уведомлений: <b>{stats['notifications']}</b>"
    )
    await call.message.edit_text(text, reply_markup=back_to_admin_kb())
    await call.answer()


@router.callback_query(F.data == "admin_trackings")
async def cb_admin_trackings(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    trackings = await get_all_active_trackings()

    if not trackings:
        await call.message.edit_text(
            "📭 Нет активных отслеживаний.",
            reply_markup=back_to_admin_kb(),
        )
        await call.answer()
        return

    lines = ["📋 <b>Активные отслеживания</b>\n"]
    for t in trackings[:15]:
        lines.append(
            f"🟢 <b>#{t['id']}</b> · {t['sheet_name']}\n"
            f"   👤 user_id: <code>{t['user_id']}</code>\n"
            f"   📄 {t['file_path']}\n"
            f"   📈 last_row: {t['last_row']}\n"
        )

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=back_to_admin_kb(),
    )
    await call.answer()


# --- WORKER: ПРОВЕРКА ТАБЛИЦ ---

async def check_all_trackings(bot: Bot):
    """
    Проверяет все активные отслеживания.
    Вызывается из main.py по расписанию.
    """
    trackings = await get_all_active_trackings()
    if not trackings:
        return

    log.info(f"🔍 Проверяю {len(trackings)} таблиц...")

    for tracking in trackings:
        try:
            new_rows = await asyncio.to_thread(
                get_new_rows,
                tracking["public_key"],
                tracking["file_path"],
                tracking["last_row"],
            )

            if not new_rows:
                continue

            for row in new_rows:
                row_number = row.get("_row_number")
                if not row_number:
                    continue

                if await is_row_sent(tracking["id"], row_number):
                    continue

                await _send_notification(
                    bot, tracking["user_id"], tracking, row
                )

                row_data = " | ".join(
                    f"{k}: {v}" for k, v in row.items()
                    if not k.startswith("_") and v
                )
                await mark_row_sent(
                    tracking["id"], row_number, row_data[:500]
                )

            last_sent = max(
                (r.get("_row_number", 0) for r in new_rows),
                default=tracking["last_row"],
            )
            await update_tracking_last_row(tracking["id"], last_sent)

        except Exception as e:
            log.error(
                f"Ошибка проверки tracking #{tracking['id']}: {e}",
                exc_info=True,
            )