test:
	poetry run tox

lint:
	poetry run black .
	poetry run ruff check --fix -e .

build:
	poetry build

publish:
	poetry publish
