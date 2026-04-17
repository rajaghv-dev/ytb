VENV        := .venv
PYTHON      := $(VENV)/bin/python
ACTIVATE    := source $(VENV)/bin/activate

# ── shared args ───────────────────────────────────────────────────────────────
CHANNEL     ?=
URL         ?=
LIMIT       ?= 20
FROM        ?=
TO          ?=
LANG        ?= en
OUTPUT      ?=
QUALITY     ?= 720p
THROTTLE    ?=
EXTRA       ?=

# ── setup ──────────────────────────────────────────────────────────────────────
.PHONY: setup
setup:
	bash setup.sh

# ── transcripts: channel ──────────────────────────────────────────────────────
.PHONY: transcripts
transcripts:
	@if [ -z "$(CHANNEL)" ]; then \
		echo "Usage: make transcripts CHANNEL=https://www.youtube.com/@handle [LIMIT=20] [FROM=YYYY-MM-DD] [TO=YYYY-MM-DD] [LANG=en]"; \
		exit 1; \
	fi
	$(ACTIVATE) && $(PYTHON) ytb.py \
		--channel "$(CHANNEL)" \
		--limit $(LIMIT) \
		--lang $(LANG) \
		$(if $(OUTPUT),--output "$(OUTPUT)",--output ./transcripts) \
		$(if $(FROM),--from $(FROM)) \
		$(if $(TO),--to $(TO)) \
		$(EXTRA)

# ── transcripts: single video ─────────────────────────────────────────────────
.PHONY: transcript
transcript:
	@if [ -z "$(URL)" ]; then \
		echo "Usage: make transcript URL=https://youtu.be/VIDEO_ID"; \
		exit 1; \
	fi
	$(ACTIVATE) && $(PYTHON) ytb.py \
		--urls "$(URL)" \
		$(if $(OUTPUT),--output "$(OUTPUT)",--output ./transcripts) \
		$(EXTRA)

# ── download: channel ─────────────────────────────────────────────────────────
.PHONY: download
download:
	@if [ -z "$(CHANNEL)" ]; then \
		echo "Usage: make download CHANNEL=https://www.youtube.com/@handle [LIMIT=20] [QUALITY=720p] [THROTTLE=800K] [FROM=YYYY-MM-DD] [TO=YYYY-MM-DD]"; \
		exit 1; \
	fi
	$(ACTIVATE) && $(PYTHON) ytb_dl.py \
		--channel "$(CHANNEL)" \
		--limit $(LIMIT) \
		--quality $(QUALITY) \
		$(if $(OUTPUT),--output "$(OUTPUT)",--output ./videos) \
		$(if $(FROM),--from $(FROM)) \
		$(if $(TO),--to $(TO)) \
		$(if $(THROTTLE),--throttle $(THROTTLE)) \
		$(EXTRA)

# ── download: single video ────────────────────────────────────────────────────
.PHONY: video
video:
	@if [ -z "$(URL)" ]; then \
		echo "Usage: make video URL=https://youtu.be/VIDEO_ID [QUALITY=720p] [THROTTLE=800K]"; \
		exit 1; \
	fi
	$(ACTIVATE) && $(PYTHON) ytb_dl.py \
		--urls "$(URL)" \
		--quality $(QUALITY) \
		$(if $(OUTPUT),--output "$(OUTPUT)",--output ./videos) \
		$(if $(THROTTLE),--throttle $(THROTTLE)) \
		$(EXTRA)

# ── audio-only ────────────────────────────────────────────────────────────────
.PHONY: audio
audio:
	@if [ -z "$(URL)$(CHANNEL)" ]; then \
		echo "Usage: make audio URL=https://youtu.be/VIDEO_ID"; \
		echo "       make audio CHANNEL=https://www.youtube.com/@handle [LIMIT=20]"; \
		exit 1; \
	fi
	$(ACTIVATE) && $(PYTHON) ytb_dl.py \
		$(if $(URL),--urls "$(URL)",--channel "$(CHANNEL)" --limit $(LIMIT)) \
		--audio-only \
		$(if $(OUTPUT),--output "$(OUTPUT)",--output ./audio) \
		$(if $(THROTTLE),--throttle $(THROTTLE)) \
		$(EXTRA)

# ── clean ──────────────────────────────────────────────────────────────────────
.PHONY: clean
clean:
	rm -rf transcripts/ videos/ audio/

.PHONY: clean-all
clean-all: clean
	rm -rf $(VENV)

.PHONY: help
help:
	@echo ""
	@echo "  Transcripts"
	@echo "  -----------"
	@echo "  make transcripts CHANNEL=<url>                    Last 20 transcripts"
	@echo "  make transcripts CHANNEL=<url> LIMIT=5            Last 5"
	@echo "  make transcripts CHANNEL=<url> FROM=YYYY-MM-DD TO=YYYY-MM-DD"
	@echo "  make transcript  URL=<url>                        Single video"
	@echo ""
	@echo "  Video download"
	@echo "  --------------"
	@echo "  make download CHANNEL=<url>                       720p, last 20 videos"
	@echo "  make download CHANNEL=<url> QUALITY=1080p         1080p"
	@echo "  make download CHANNEL=<url> QUALITY=best          Best available"
	@echo "  make download CHANNEL=<url> THROTTLE=800K         Throttled to 800 KB/s"
	@echo "  make download CHANNEL=<url> FROM=YYYY-MM-DD TO=YYYY-MM-DD"
	@echo "  make video    URL=<url>                           Single video"
	@echo "  make audio    URL=<url>                           Audio only (m4a)"
	@echo "  make audio    CHANNEL=<url> LIMIT=10              Audio from channel"
	@echo ""
	@echo "  Other"
	@echo "  -----"
	@echo "  make setup                                        Install everything"
	@echo "  make clean                                        Remove output dirs"
	@echo "  make clean-all                                    Remove output + venv"
	@echo ""
