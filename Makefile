.PHONY: check check-native

check:
	bash scripts/check.sh

check-native:
	bash scripts/check.sh --native-smoke
