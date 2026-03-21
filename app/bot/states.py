"""
FSM states for the card creation wizard.
"""
from aiogram.fsm.state import State, StatesGroup


class CardWizard(StatesGroup):
    choosing_theme    = State()   # Step 1: выбор темы (light / dark)
    choosing_bg       = State()   # Step 2: выбор фона (фото / градиент)
    waiting_for_photo = State()   # Step 2b: ожидание фото от пользователя
    choosing_format   = State()   # Step 3: формат карточки (вертикальный / квадратный)
    choosing_layout   = State()   # Step 4: положение текста
    entering_title    = State()   # Step 5: заголовок
    entering_subtitle = State()   # Step 6: подзаголовок
    entering_tag      = State()   # Step 7: тег → рендер
