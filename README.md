# Agentify Example: Tau-Bench

Example code for agentifying Tau-Bench using A2A and MCP standards.

## Project Structure

```
src/
├── green_agent/       # Assessment manager agent (runs tau-bench, talks to white via A2A)
│   ├── agent.py
│   ├── run.sh         # Entry point for agentbeats controller
│   └── tau_green_agent.toml
├── white_agent/       # Target agent being tested (calls GPT-4o via LiteLLM)
│   ├── agent.py
│   └── run.sh         # Entry point for agentbeats controller
├── my_util/           # A2A client helpers
└── launcher.py        # Local-mode evaluation coordinator
main.py                # CLI entry point
proxy_test.py          # Automated proxy mode test script
```

## Installation

```bash
uv sync
```

Requires an editable install of [earthshaker](../earthshaker) (provides the `agentbeats` CLI).

## Environment Variables

Create a `.env` file in the repo root:

```
OPENAI_API_KEY=sk-...
```

Both agents call `dotenv.load_dotenv()` on startup, which reads this file. The key is used by:
- **White agent** — LiteLLM uses it to call GPT-4o
- **Green agent** — tau-bench uses it internally for the simulated user

## Local Mode

Runs both agents in a single process on localhost. No controller or backend needed.

```bash
uv run python main.py launch
```

Starts green on port 9001 and white on 9002, runs one tau-bench task, and prints the result.

## Proxy Mode

Runs agents behind the agentbeats backend, which proxies A2A traffic between them and manages assessments.

Each agent is started by a controller (`agentbeats run_ctrl`) that sets `AGENT_PORT` and `AGENT_URL` env vars before running the agent's `run.sh`. The agents read these to bind to the correct port and advertise the proxy URL in their agent card.

### Prerequisites

- **`.env`** with `OPENAI_API_KEY` (see above)
- **earthshaker** installed (editable, via `uv sync`)
- **Backend** running at a reachable URL (default: `https://backend.evansandoval.org`)
- **`AB_API_KEY`** env var — your session cookie from the backend (GitHub OAuth). Find it in browser dev tools under Application > Cookies > `ab_api_key`.

### Running

```bash
export AB_API_KEY="your-cookie-value"
python proxy_test.py
```

This automates the full flow:

1. Creates two proxied agents on the backend (green + white)
2. Launches `agentbeats run_ctrl` for each in their `src/` directories
3. Waits for the backend to confirm both agents are reachable
4. Creates a tau-bench assessment
5. Prints a URL to view results

Press Ctrl+C to stop — the script cleans up controllers and deletes agents.

### Options

```
--backend-url URL    Backend API URL (or set AB_BACKEND_URL)
--repeat-n N         Number of assessment repetitions (default: 1)
--no-browser         Don't open results in browser
```

## How It Works

The **green agent** receives an assessment task containing the white agent's URL and a tau-bench config. It sets up the tau-bench environment, then drives a multi-step conversation with the white agent over A2A — sending observations, receiving tool-call responses, executing them in the environment, and repeating until done.

The **white agent** is a stateful A2A server that forwards messages to GPT-4o and returns the response, maintaining per-conversation message history.

In **local mode**, `launcher.py` spawns both as `multiprocessing.Process` on localhost. In **proxy mode**, the backend routes A2A traffic through proxy URLs, so agents only need to reach the backend — not each other directly.
