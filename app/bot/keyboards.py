"""
InlineKeyboard builders for the card creation wizard.
"""
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def start_keyboard() -> ReplyKeyboardMarkup:
    """Main menu — single «Создать карточку» button."""
    b = ReplyKeyboardBuilder()
    b.button(text="🎨 Создать карточку")
    return b.as_markup(resize_keyboard=True)


def theme_keyboard() -> InlineKeyboardMarkup:
    """Step 1 — choose card theme (light / dark)."""
    b = InlineKeyboardBuilder()
    b.button(text="☀️ Светлая тема",  callback_data="theme:light")
    b.button(text="🌑 Тёмная тема",   callback_data="theme:dark")
    b.adjust(1)
    return b.as_markup()


def bg_keyboard() -> InlineKeyboardMarkup:
    """Step 2 — choose background type (photo / gradient)."""
    b = InlineKeyboardBuilder()
    b.button(text="🖼 Загрузить фото",  callback_data="bg:photo")
    b.button(text="🌌 Градиент 1",      callback_data="bg:gradient_1")
    b.button(text="🌃 Градиент 2",      callback_data="bg:gradient_2")
    b.button(text="🌆 Градиент 3",      callback_data="bg:gradient_3")
    b.adjust(1)
    return b.as_markup()


def format_keyboard() -> InlineKeyboardMarkup:
    """Step 3 — choose card format (aspect ratio)."""
    b = InlineKeyboardBuilder()
    b.button(text="📱 Вертикальная  1080×1350", callback_data="format:vertical")
    b.button(text="⬛ Квадратная    1080×1080", callback_data="format:square")
    b.adjust(1)
    return b.as_markup()


def layout_keyboard() -> InlineKeyboardMarkup:
    """Step 4 — choose text position."""
    b = InlineKeyboardBuilder()
    b.button(text="⬆ Сверху",    callback_data="layout:top")
    b.button(text="⬛ По центру", callback_data="layout:center")
    b.button(text="⬇ Снизу",     callback_data="layout:bottom")
    b.adjust(3)
    return b.as_markup()
