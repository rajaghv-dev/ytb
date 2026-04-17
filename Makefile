VENV        := .venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
ACTIVATE    := source $(VENV)/bin/activate

CHANNEL     ?=
URL         ?=
LIMIT       ?= 20
FROM        ?=
TO          ?=
LANG        ?= en
OUTPUT      ?= ./transcripts
EXTRA       ?=

# ── setup ──────────────────────────────────────────────────────────────────────
.PHONY: setup
setup:
	bash setup.sh

# ── run: channel ──────────────────────────────────────────────────────────────
.PHONY: transcripts
transcripts:
	@if [ -z "$(CHANNEL)" ]; then \
		echo "Usage: make transcripts CHANNEL=https://www.youtube.com/@handle [LIMIT=20] [FROM=YYYY-MM-DD] [TO=YYYY-MM-DD] [LANG=en] [OUTPUT=./transcripts]"; \
		exit 1; \
	fi
	$(ACTIVATE) && $(PYTHON) ytb.py \
		--channel "$(CHANNEL)" \
		--limit $(LIMIT) \
		--lang $(LANG) \
		--output "$(OUTPUT)" \
		$(if $(FROM),--from $(FROM)) \
		$(if $(TO),--to $(TO)) \
		$(EXTRA)

# ── run: single / multiple videos ─────────────────────────────────────────────
.PHONY: video
video:
	@if [ -z "$(URL)" ]; then \
		echo "Usage: make video URL=https://youtu.be/VIDEO_ID [OUTPUT=./transcripts]"; \
		exit 1; \
	fi
	$(ACTIVATE) && $(PYTHON) ytb.py --urls "$(URL)" --output "$(OUTPUT)" $(EXTRA)

# ── clean ──────────────────────────────────────────────────────────────────────
.PHONY: clean
clean:
	rm -rf transcripts/

.PHONY: clean-all
clean-all: clean
	rm -rf $(VENV)

.PHONY: help
help:
	@echo ""
	@echo "  make setup                              Install everything"
	@echo "  make transcripts CHANNEL=<url>          Fetch last 20 transcripts"
	@echo "  make transcripts CHANNEL=<url> LIMIT=5  Fetch last 5"
	@echo "  make transcripts CHANNEL=<url> FROM=YYYY-MM-DD TO=YYYY-MM-DD"
	@echo "  make video URL=<url>                    Single video transcript"
	@echo "  make clean                              Remove ./transcripts"
	@echo "  make clean-all                          Remove transcripts + venv"
	@echo ""
