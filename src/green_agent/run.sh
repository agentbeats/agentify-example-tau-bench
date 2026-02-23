#!/bin/bash
cd "$(dirname "$0")/../.."
PYTHONPATH=. python src/green_agent/agent.py
