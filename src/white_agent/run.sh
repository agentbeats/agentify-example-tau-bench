#!/bin/bash
cd "$(dirname "$0")/../.."
PYTHONPATH=. python src/white_agent/agent.py
