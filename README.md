# Agentify Example: Tau-Bench

Example code for agentifying Tau-Bench using A2A and MCP standards.

## Project Structure

```
src/
├── green_agent/    # Assessment manager agent
├── white_agent/    # Target agent being tested
└── launcher.py     # Evaluation coordinator
```

## Usage

```bash
# Start green agent (assessment manager)
uv run python main.py green

# Start white agent (target being tested)
uv run python main.py white

# Launch complete evaluation
uv run python main.py launch
```

## Installation

```bash
uv sync
