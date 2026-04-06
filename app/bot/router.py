"""
Telegram bot — card creation wizard (FSM).

Flow:
    /start
    → «Создать карточку»
    → Step 1:  выбор темы (light / dark)
    → Step 2:  выбор фона (фото / градиент)
    → Step 2b: загрузка изображения как FILE/DOCUMENT (PNG или JPG)
    → Step 3:  выбор формата (1080×1350 / 1080×1080)
    → Step 4:  положение текста
    → Step 5:  ввод заголовка
    → Step 6:  ввод подзаголовка (или /skip)
    → Step 7:  ввод тега (или /skip) → рендер → PNG-документ
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.bot.keyboards import bg_keyboard, format_keyboard, layout_keyboard, start_keyboard, theme_keyboard
from app.bot.states import CardWizard
from app.config import settings
from app.services.card_spec import BackgroundMode, CardSpec, Palette, TextLayout
from app.services.renderer import render_card
from app.templates.engine import TemplateVariantNotFound

from PIL import Image

logger = logging.getLogger(__name__)
router = Router()


def _convert_to_png(src: Path) -> Path:
    """Convert any Pillow-readable image to PNG. Deletes src if different from dst."""
    if src.suffix.lower() in (".heic", ".heif"):
        try:
            import pillow_heif  # type: ignore
            pillow_heif.register_heif_opener()
        except ImportError:
            pass  # pillow-heif not installed; Pillow will raise on open
    dst = src.with_suffix(".png")
    Image.open(src).convert("RGB").save(dst, "PNG")
    if dst != src:
        src.unlink(missing_ok=True)
    return dst

# MIME types accepted as background image upload
# Native formats (no conversion needed by Pillow):
_NATIVE_MIME = {"image/png", "image/jpeg"}
# Formats requiring pillow-heif registration or are less common but Pillow-supported:
_EXTRA_MIME  = {"image/heic", "image/heif", "image/webp", "image/bmp", "image/tiff"}
_ALL_MIME    = _NATIVE_MIME | _EXTRA_MIME

# MIME → file extension for saving the downloaded file
_MIME_EXT: dict[str, str] = {
    "image/png":  "png",
    "image/jpeg": "jpg",
    "image/heic": "heic",
    "image/heif": "heif",
    "image/webp": "webp",
    "image/bmp":  "bmp",
    "image/tiff": "tiff",
}

_FORMATS_HINT = "PNG, JPG, HEIC, WebP, BMP, TIFF"


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
    await state.set_state(CardWizard.choosing_theme)
    await message.answer("Выберите тему карточки:", reply_markup=theme_keyboard())


# ---------------------------------------------------------------------------
# Step 1: выбор темы
# ---------------------------------------------------------------------------

@router.callback_query(CardWizard.choosing_theme, F.data.startswith("theme:"))
async def choose_theme(callback: CallbackQuery, state: FSMContext) -> None:
    palette = callback.data.split(":")[1]   # "light" | "dark"
    await state.update_data(theme=palette)
    await state.set_state(CardWizard.choosing_bg)
    await callback.message.edit_text(
        "Выберите фон для карточки:", reply_markup=bg_keyboard()
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 2a: выбор градиента
# ---------------------------------------------------------------------------

@router.callback_query(CardWizard.choosing_bg, F.data.startswith("bg:gradient_"))
async def choose_gradient(callback: CallbackQuery, state: FSMContext) -> None:
    gradient_id = callback.data.split(":")[1]   # e.g. "gradient_1"
    await state.update_data(bg_type="gradient", bg_value=gradient_id)
    await state.set_state(CardWizard.choosing_format)
    await callback.message.edit_text(
        "Выберите формат карточки:", reply_markup=format_keyboard()
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 2b: выбор фото — запрос загрузки как документа
# ---------------------------------------------------------------------------

@router.callback_query(CardWizard.choosing_bg, F.data == "bg:photo")
async def choose_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CardWizard.waiting_for_photo)
    await callback.message.edit_text(
        f"Пришлите изображение как файл (Document).\n\n"
        f"📎 В Telegram: нажмите скрепку → Файл → выберите изображение.\n"
        f"Поддерживаются: {_FORMATS_HINT}."
    )
    await callback.answer()


# Step 2b: приём документа (PNG / JPG / HEIC / WebP / …)
@router.message(CardWizard.waiting_for_photo, F.document)
async def receive_document(message: Message, state: FSMContext, bot: Bot) -> None:
    doc = message.document
    mime = doc.mime_type or ""

    if mime not in _ALL_MIME:
        await message.answer(
            f"Неподдерживаемый формат.\n"
            f"Пожалуйста, пришлите изображение как файл (Document).\n"
            f"Поддерживаются: {_FORMATS_HINT}."
        )
        return

    ext = _MIME_EXT.get(mime, "bin")
    tmp_path = settings.output_dir / f"tmp_{message.from_user.id}.{ext}"

    tg_file = await bot.get_file(doc.file_id)
    await bot.download_file(tg_file.file_path, destination=tmp_path)

    # HEIC and other non-native formats: convert to PNG so Pillow compositor works reliably
    if mime not in _NATIVE_MIME:
        tmp_path = await asyncio.get_event_loop().run_in_executor(
            None, _convert_to_png, tmp_path
        )

    await state.update_data(bg_type="photo", bg_value=str(tmp_path))
    await state.set_state(CardWizard.choosing_format)
    await message.answer("Выберите формат карточки:", reply_markup=format_keyboard())


# Если пользователь отправил сжатое фото вместо документа
@router.message(CardWizard.waiting_for_photo, F.photo)
async def photo_instead_of_document(message: Message) -> None:
    await message.answer(
        "Пожалуйста, отправьте изображение как файл, а не как фото.\n\n"
        f"📎 В Telegram: нажмите скрепку → Файл → выберите изображение.\n"
        f"Поддерживаются: {_FORMATS_HINT}."
    )


# Если пришло что-то другое
@router.message(CardWizard.waiting_for_photo)
async def document_wrong_type(message: Message) -> None:
    await message.answer(
        f"Ожидаю изображение как файл (Document).\n"
        f"📎 Нажмите скрепку → Файл → выберите изображение.\n"
        f"Поддерживаются: {_FORMATS_HINT}."
    )


# ---------------------------------------------------------------------------
# Step 3: формат карточки
# ---------------------------------------------------------------------------

_FORMAT_SIZES = {
    "vertical": (1080, 1350),
    "square":   (1080, 1080),
}

@router.callback_query(CardWizard.choosing_format, F.data.startswith("format:"))
async def choose_format(callback: CallbackQuery, state: FSMContext) -> None:
    fmt = callback.data.split(":")[1]   # "vertical" | "square"
    await state.update_data(card_format=fmt)
    await state.set_state(CardWizard.choosing_layout)
    await callback.message.edit_text(
        "Положение текста на карточке:", reply_markup=layout_keyboard()
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 4: положение текста
# ---------------------------------------------------------------------------

@router.callback_query(CardWizard.choosing_layout, F.data.startswith("layout:"))
async def choose_layout(callback: CallbackQuery, state: FSMContext) -> None:
    layout = callback.data.split(":")[1]   # "top" | "center" | "bottom"
    await state.update_data(text_layout=layout)
    await state.set_state(CardWizard.entering_title)
    await callback.message.edit_text("Введите заголовок:")
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 5: заголовок
# ---------------------------------------------------------------------------

@router.message(CardWizard.entering_title, F.text)
async def enter_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title:
        await message.answer("Заголовок не может быть пустым. Попробуйте ещё раз:")
        return
    if len(title) > 90:
        await message.answer(
            f"Заголовок слишком длинный ({len(title)} символов, максимум 90). "
            "Попробуйте короче:"
        )
        return
    await state.update_data(title=title)
    await state.set_state(CardWizard.entering_subtitle)
    await message.answer("Введите подзаголовок или /skip")


# ---------------------------------------------------------------------------
# Step 6: подзаголовок
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
# Step 7: тег → рендер → отправить как Document
# ---------------------------------------------------------------------------

@router.message(CardWizard.entering_tag, F.text)
async def enter_tag(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    tag = None if text == "/skip" else text

    data = await state.get_data()
    await state.clear()

    status = await message.answer("⏳ Генерирую карточку...")
    try:
        bg_type  = data["bg_type"]    # "photo" | "gradient"
        bg_value = data["bg_value"]
        palette  = Palette(data.get("theme", "dark"))

        fmt = data.get("card_format", "vertical")
        w, h = _FORMAT_SIZES.get(fmt, (1080, 1350))

        spec = CardSpec(
            size={"width": w, "height": h},
            title=data["title"],
            subtitle=data.get("subtitle"),
            tag=tag,
            palette=palette,
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
