.PHONY: pdf wiki-lint wiki-sync

pdf:
	python3 scripts/render_resume.py
	pdflatex -interaction=nonstopmode resume.tex

wiki-lint:
	python3 scripts/wiki_lint.py

wiki-sync:
	@echo "No automated resume->wiki sync exists: data/*.json is the sole source of truth"
	@echo "and is not mirrored into the wiki (see wiki/SCHEMA.md)."
	@echo "If a decision or architecture change needs recording, edit wiki/decisions/"
	@echo "or wiki/architecture/ directly and append an entry to wiki/log.md."
