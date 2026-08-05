SHELL := /bin/bash

.DEFAULT_GOAL := help

.PHONY: help doctor sync build up down restart status logs shell test view view-stop

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

doctor: ## Check local tools, remote access, storage, and GPUs
	@./tools/doctor

sync: ## Commit and synchronize source (MESSAGE="...")
	@./tools/gpu sync "$${MESSAGE:-}"

build: ## Build the synchronized remote ROS/Gazebo image
	@./tools/sim build

up: ## Start the synchronized remote development container
	@./tools/sim up

down: ## Stop the remote development container
	@./tools/sim down

restart: ## Restart the synchronized remote development container
	@./tools/sim restart

status: ## Show remote container status
	@./tools/sim status

logs: ## Follow remote container logs
	@./tools/sim logs

shell: ## Open an interactive shell in the remote container
	@./tools/sim shell

test: ## Build and test the synchronized ROS workspace remotely
	@./tools/sim test

view: ## Start the Foxglove tunnel and open the Mac client
	@./tools/view start

view-stop: ## Stop the Foxglove SSH tunnel
	@./tools/view stop
