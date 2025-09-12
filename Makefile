test:
	poetry run tox

lint:
	poetry run black .
	poetry run ruff check --fix -e .

build:
	poetry build

publish:
	poetry publish

changelog:
	@git log -n 1 --pretty=format:"* %s (%an, %ad)" --date=short | cat - CHANGELOG.md > CHANGELOG.tmp && mv CHANGELOG.tmp CHANGELOG.md
