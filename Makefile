.PHONY: venv install test bot figma clean

VENV   := venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip

# macOS (Apple Silicon): cairosvg needs the Homebrew lib path.
# On Linux libcairo is a system library — no extra env needed.
UNAME := $(shell uname)
ifeq ($(UNAME), Darwin)
  CAIRO_ENV := DYLD_LIBRARY_PATH=/opt/homebrew/lib
else
  CAIRO_ENV :=
endif

venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip --quiet

install: venv
	$(PIP) install -r requirements.txt

test:
	$(CAIRO_ENV) $(PYTHON) render_test.py

figma:
	$(PYTHON) figma_convert.py

bot:
	set -a && . ./.env && set +a && $(CAIRO_ENV) $(PYTHON) main.py

clean:
	rm -rf $(VENV) assets/output/*.png assets/output/_grad_*.png
