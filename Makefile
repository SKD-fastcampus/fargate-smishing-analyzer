.PHONY: setup deploy build run status results

setup:
	terraform init

deploy:
	terraform apply

build:
	./scripts/push.sh

# Usage: make run url=http://example.com
run:
	@if [ -z "$(url)" ]; then echo "Error: url is required. Usage: make run url=http://example.com"; exit 1; fi
	./scripts/run_task.sh "$(url)"

status:
	./scripts/check_status.sh

results:
	./scripts/ls_results.sh
