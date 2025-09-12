test:
	poetry run tox

lint:
	black .
	ruff check --fix -e .

build:
	poetry build

publish:
	poetry publish
