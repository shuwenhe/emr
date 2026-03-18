GO ?= go
SERVICE ?= report-file-service
PKG ?= ./...
CMD ?= ./cmd/server
BIN_DIR ?= bin
BIN ?= $(BIN_DIR)/$(SERVICE)
DOCKER_IMAGE ?= $(SERVICE):local

.PHONY: help run build test fmt vet tidy clean docker-build

help:
	@echo "Available targets:"
	@echo "  make help         # list available commands"
	@echo "  make run          # run service locally"
	@echo "  make build        # build binary to $(BIN)"
	@echo "  make test         # run go tests"
	@echo "  make fmt          # format go code"
	@echo "  make vet          # run go vet"
	@echo "  make tidy         # tidy go modules"
	@echo "  make clean        # remove build artifacts"
	@echo "  make docker-build # build docker image"

run:
	$(GO) run $(CMD)

build:
	@mkdir -p $(BIN_DIR)
	$(GO) build -o $(BIN) $(CMD)

test:
	$(GO) test $(PKG)

fmt:
	$(GO) fmt $(PKG)

vet:
	$(GO) vet $(PKG)

tidy:
	$(GO) mod tidy

clean:
	@rm -rf $(BIN_DIR)

docker-build:
	docker build -t $(DOCKER_IMAGE) -f Dockerfile .

default: help
