"""
Клавиатуры бота для работы с Яндекс Таблицами.
"""
from aiogram.types import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> ReplyKeyboardMarkup:
    """Главное меню."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить таблицу")],
            [
                KeyboardButton(text="📋 Мои таблицы"),
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие…",
    )


def cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()


def trackings_list_kb(trackings: list[dict]) -> InlineKeyboardMarkup:
    """Список отслеживаний — каждая как кнопка."""
    builder = InlineKeyboardBuilder()
    for t in trackings[:20]:
        status = "🟢" if t["is_active"] else "🔴"
        sheet = t["sheet_name"][:20]
        builder.button(
            text=f"{status} #{t['id']} · {sheet}",
            callback_data=f"track:{t['id']}",
        )
    builder.adjust(1)
    return builder.as_markup()


def tracking_actions_kb(tracking_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """Кнопки для конкретной таблицы."""
    builder = InlineKeyboardBuilder()

    if is_active:
        builder.button(
            text="⏸ Пауза",
            callback_data=f"toggle:{tracking_id}",
        )
    else:
        builder.button(
            text="▶️ Включить",
            callback_data=f"toggle:{tracking_id}",
        )

    builder.button(
        text="👁 Проверить сейчас",
        callback_data=f"check:{tracking_id}",
    )
    builder.button(
        text="🗑 Удалить",
        callback_data=f"delete:{tracking_id}",
    )
    builder.button(
        text="⬅️ К списку",
        callback_data="back_to_list",
    )
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_kb(tracking_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, удалить",
        callback_data=f"confirm_delete:{tracking_id}",
    )
    builder.button(
        text="❌ Отмена",
        callback_data=f"track:{tracking_id}",
    )
    builder.adjust(2)
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    """Возврат в главное меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В меню", callback_data="back_to_menu")
    return builder.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    """Админ-панель."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="📋 Все отслеживания", callback_data="admin_trackings")
    builder.adjust(1)
    return builder.as_markup()


def back_to_admin_kb() -> InlineKeyboardMarkup:
    """Возврат в админку."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="admin_menu")
    return builder.as_markup()