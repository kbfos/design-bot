"""
FSM states for the card creation wizard.
"""
from aiogram.fsm.state import State, StatesGroup


class CardWizard(StatesGroup):
    choosing_bg       = State()   # Step 1: выбор фона (кнопки)
    waiting_for_photo = State()   # Step 1b: ожидание фото от пользователя
    choosing_format   = State()   # Step 2: формат карточки (вертикальный / квадратный)
    choosing_layout   = State()   # Step 3: положение текста
    entering_title    = State()   # Step 4: заголовок
    entering_subtitle = State()   # Step 5: подзаголовок
    entering_tag      = State()   # Step 6: тег
