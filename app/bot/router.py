"""
Telegram bot — card creation wizard (FSM).

Flow:
    /start
    → «Создать карточку»
    → Step 1: выбор фона (кнопки)
    → Step 1b: загрузка изображения как FILE/DOCUMENT (PNG или JPG)
    → Step 2: положение текста
    → Step 3: ввод заголовка
    → Step 4: ввод подзаголовка (или /skip)
    → Step 5: ввод тега (или /skip) → рендер → PNG-документ
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.bot.keyboards import bg_keyboard, layout_keyboard, start_keyboard
from app.bot.states import CardWizard
from app.config import settings
from app.services.card_spec import BackgroundMode, CardSpec, TextLayout
from app.services.renderer import render_card
from app.templates.engine import TemplateVariantNotFound

logger = logging.getLogger(__name__)
router = Router()

# Accepted MIME types for background image upload
_ACCEPTED_MIME = {"image/png", "image/jpeg"}


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я генерирую дизайн-карточки.\n"
        "Нажми кнопку ниже, чтобы начать.",
        reply_markup=start_keyboard(),
    )


# ---------------------------------------------------------------------------
# Step 0 → Step 1: «Создать карточку»
# ---------------------------------------------------------------------------

@router.message(F.text == "🎨 Создать карточку")
async def start_wizard(message: Message, state: FSMContext) -> None:
    await state.set_state(CardWizard.choosing_bg)
    await message.answer("Выберите фон для карточки:", reply_markup=bg_keyboard())


# ---------------------------------------------------------------------------
# Step 1a: выбор градиента
# ---------------------------------------------------------------------------

@router.callback_query(CardWizard.choosing_bg, F.data.startswith("bg:gradient_"))
async def choose_gradient(callback: CallbackQuery, state: FSMContext) -> None:
    gradient_id = callback.data.split(":")[1]  # e.g. "gradient_1"
    await state.update_data(bg_type="gradient", bg_value=gradient_id)
    await state.set_state(CardWizard.choosing_layout)
    await callback.message.edit_text(
        "Положение текста на карточке:", reply_markup=layout_keyboard()
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 1b: выбор фото — запрос загрузки как документа
# ---------------------------------------------------------------------------

@router.callback_query(CardWizard.choosing_bg, F.data == "bg:photo")
async def choose_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CardWizard.waiting_for_photo)
    await callback.message.edit_text(
        "Пришлите изображение как файл (Document).\n\n"
        "📎 В Telegram: нажмите скрепку → Файл → выберите PNG или JPG.\n"
        "Так изображение сохранит оригинальное качество."
    )
    await callback.answer()


# Step 1b: приём документа (PNG / JPG)
@router.message(CardWizard.waiting_for_photo, F.document)
async def receive_document(message: Message, state: FSMContext, bot: Bot) -> None:
    doc = message.document
    mime = doc.mime_type or ""

    if mime not in _ACCEPTED_MIME:
        await message.answer(
            "Поддерживаются только PNG и JPG.\n"
            "Пожалуйста, пришлите изображение как файл (Document)."
        )
        return

    # Determine file extension from MIME
    ext = "png" if mime == "image/png" else "jpg"
    tmp_path = settings.output_dir / f"tmp_{message.from_user.id}.{ext}"

    tg_file = await bot.get_file(doc.file_id)
    await bot.download_file(tg_file.file_path, destination=tmp_path)

    await state.update_data(bg_type="photo", bg_value=str(tmp_path))
    await state.set_state(CardWizard.choosing_layout)
    await message.answer("Положение текста на карточке:", reply_markup=layout_keyboard())


# Если пользователь отправил сжатое фото вместо документа
@router.message(CardWizard.waiting_for_photo, F.photo)
async def photo_instead_of_document(message: Message) -> None:
    await message.answer(
        "Пожалуйста, отправьте изображение как файл, а не как фото.\n\n"
        "📎 В Telegram: нажмите скрепку → Файл → выберите PNG или JPG.\n"
        "Это сохранит оригинальное качество изображения."
    )


# Если пришло что-то другое
@router.message(CardWizard.waiting_for_photo)
async def document_wrong_type(message: Message) -> None:
    await message.answer(
        "Ожидаю PNG или JPG как файл (Document).\n"
        "📎 Нажмите скрепку → Файл → выберите изображение."
    )


# ---------------------------------------------------------------------------
# Step 2: положение текста
# ---------------------------------------------------------------------------

@router.callback_query(CardWizard.choosing_layout, F.data.startswith("layout:"))
async def choose_layout(callback: CallbackQuery, state: FSMContext) -> None:
    layout = callback.data.split(":")[1]  # "top" | "center" | "bottom"
    await state.update_data(text_layout=layout)
    await state.set_state(CardWizard.entering_title)
    await callback.message.edit_text("Введите заголовок:")
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 3: заголовок
# ---------------------------------------------------------------------------

@router.message(CardWizard.entering_title, F.text)
async def enter_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title:
        await message.answer("Заголовок не может быть пустым. Попробуйте ещё раз:")
        return
    if len(title) > 120:
        await message.answer(
            f"Заголовок слишком длинный ({len(title)} символов, максимум 120). "
            "Попробуйте короче:"
        )
        return
    await state.update_data(title=title)
    await state.set_state(CardWizard.entering_subtitle)
    await message.answer("Введите подзаголовок или /skip")


# ---------------------------------------------------------------------------
# Step 4: подзаголовок
# ---------------------------------------------------------------------------

@router.message(CardWizard.entering_subtitle, F.text)
async def enter_subtitle(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    subtitle = None if text == "/skip" else text
    if subtitle and len(subtitle) > 50:
        await message.answer(
            f"Подзаголовок слишком длинный ({len(subtitle)} символов, максимум 50). "
            "Попробуйте короче или /skip:"
        )
        return
    await state.update_data(subtitle=subtitle)
    await state.set_state(CardWizard.entering_tag)
    await message.answer("Введите тег или /skip")


# ---------------------------------------------------------------------------
# Step 5: тег → рендер → отправить как Document
# ---------------------------------------------------------------------------

@router.message(CardWizard.entering_tag, F.text)
async def enter_tag(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    tag = None if text == "/skip" else text

    data = await state.get_data()
    await state.clear()

    status = await message.answer("⏳ Генерирую карточку...")
    try:
        bg_type  = data["bg_type"]   # "photo" | "gradient"
        bg_value = data["bg_value"]

        spec = CardSpec(
            title=data["title"],
            subtitle=data.get("subtitle"),
            tag=tag,
            text_layout=TextLayout(data.get("text_layout", "center")),
            background_mode=(
                BackgroundMode.FILE if bg_type == "photo"
                else BackgroundMode.GRADIENT
            ),
            background_file=(
                Path(bg_value) if bg_type == "photo" else None
            ),
            background_gradient_id=(
                bg_value if bg_type == "gradient" else None
            ),
        )

        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, render_card, spec)

        png_bytes = path.read_bytes()
        # Send as Document to preserve full quality
        doc_file = BufferedInputFile(png_bytes, filename=path.name)
        await message.answer_document(doc_file)

    except TemplateVariantNotFound as exc:
        logger.error("Template not found: %s", exc)
        await message.answer("Шаблон не найден. Обратитесь к администратору.")

    except Exception as exc:
        logger.exception("Render error: %s", exc)
        await message.answer("Не удалось создать карточку. Попробуйте ещё раз.")

    finally:
        await status.delete()
