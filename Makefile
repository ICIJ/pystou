.PHONY: install lint test clean

install:
	pip install .

lint:
	ruff check .

test:
	python -m unittest discover tests

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf __pycache__/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
