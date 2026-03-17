# Деплой Design Bot на Ubuntu 22.04 VPS

## Системные зависимости

```bash
sudo apt update && sudo apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi-dev \
    fonts-inter
```

## Создать пользователя

```bash
sudo useradd --system --create-home --shell /bin/bash designbot
```

## Клонировать репозиторий

```bash
sudo mkdir -p /opt/design-bot
sudo git clone https://github.com/YOUR_ORG/design-bot.git /opt/design-bot
sudo chown -R designbot:designbot /opt/design-bot
```

## Python venv и зависимости

```bash
cd /opt/design-bot
sudo -u designbot python3.11 -m venv venv
sudo -u designbot venv/bin/pip install --upgrade pip
sudo -u designbot venv/bin/pip install -r requirements.txt
```

## Настройка .env

```bash
sudo -u designbot cp .env.example .env
sudo -u designbot nano .env
```

Минимальный `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here

ASSETS_DIR=assets
TEMPLATES_DIR=assets/templates
FONTS_DIR=assets/fonts
OUTPUT_DIR=assets/output

RENDERER_BACKEND=cairosvg
```

## Шрифты

**Inter** устанавливается через apt (см. выше).

**Panama** — кастомный шрифт, отсутствует в репозиториях. Скопировать файл на сервер и установить:

```bash
# Скопировать файл на сервер (с локальной машины):
scp PanamaProportionalRegular.otf user@your-server:/tmp/

# На сервере:
sudo cp /tmp/PanamaProportionalRegular.otf /usr/local/share/fonts/
sudo fc-cache -fv
```

Проверить наличие шрифта:
```bash
fc-list | grep -i panama
fc-list | grep -i inter
```

Если Panama не установлен — cairosvg применит fallback (`Arial Black` / sans-serif). Карточки будут генерироваться, но шрифт отличается от оригинального.

## Права на директории

```bash
sudo -u designbot mkdir -p /opt/design-bot/assets/output
sudo -u designbot mkdir -p /opt/design-bot/assets/images
```

## Smoke test

Перед запуском systemd убедиться, что рендер работает:

```bash
cd /opt/design-bot
sudo -u designbot venv/bin/python render_test.py
# Ожидаемый результат: файлы в assets/output/
ls assets/output/
```

## Установка systemd service

```bash
sudo cp /opt/design-bot/deploy/design-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable design-bot
sudo systemctl start design-bot
```

## Управление сервисом

```bash
# Статус
sudo systemctl status design-bot

# Логи в реальном времени
sudo journalctl -u design-bot -f

# Последние 100 строк
sudo journalctl -u design-bot -n 100

# Перезапуск (например, после обновления кода)
sudo systemctl restart design-bot

# Остановить
sudo systemctl stop design-bot
```

## Обновление кода

```bash
cd /opt/design-bot
sudo -u designbot git pull
sudo -u designbot venv/bin/pip install -r requirements.txt
sudo systemctl restart design-bot
sudo journalctl -u design-bot -f   # проверить запуск
```

## Проверка через Telegram

1. Открыть бота в Telegram
2. Отправить `/start`
3. Нажать **🎨 Создать карточку**
4. Пройти все шаги мастера
5. Получить PNG-файл в чате

---

## Структура проекта

```
design-bot/
├── app/
│   ├── bot/
│   │   ├── keyboards.py     # inline/reply клавиатуры
│   │   ├── router.py        # FSM wizard (5 шагов)
│   │   └── states.py        # CardWizard StatesGroup
│   ├── services/
│   │   ├── card_spec.py     # CardSpec (Pydantic модель)
│   │   └── renderer.py      # SVG → PNG pipeline
│   ├── templates/
│   │   └── engine.py        # Jinja2 + cairosvg
│   └── config.py            # pydantic-settings
├── assets/
│   ├── fonts/               # .ttf шрифты
│   ├── output/              # временные PNG (gitignored)
│   └── templates/           # *.svg шаблоны
├── deploy/
│   └── design-bot.service   # systemd unit
├── .env.example
├── .gitignore
├── main.py
├── Makefile
├── render_test.py
├── requirements.txt
└── run.sh
```
