.PHONY: test lint dist clean

test:
	python3 tests/test_sejfik.py

lint:
	python3 -m py_compile sejfik
	shellcheck install.sh

dist: test
	sha256sum sejfik install.sh > SHA256SUMS
	@cat SHA256SUMS

clean:
	rm -rf __pycache__ tests/__pycache__ SHA256SUMS
