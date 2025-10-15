"""Green agent implementation - manages assessment and evaluation."""

import uvicorn
import tomllib
import dotenv
import json
import time
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, SendMessageSuccessResponse, Message
from a2a.utils import new_agent_text_message, get_text_parts
from src.my_util import parse_tags, my_a2a

# from tau_bench.agents.tool_calling_agent import ToolCallingAgent
from tau_bench.envs import get_env
from tau_bench.types import SolveResult, RESPOND_ACTION_NAME, Action

dotenv.load_dotenv()


def load_agent_card_toml(agent_name):
    current_dir = __file__.rsplit("/", 1)[0]
    with open(f"{current_dir}/{agent_name}.toml", "rb") as f:
        return tomllib.load(f)


async def ask_agent_to_solve(white_agent_url, env, task_index, max_num_steps=30):
    # migrated from https://github.com/sierra-research/tau-bench/blob/4754e6b406507dbcbce8e8b3855dcf80aaec18ac/tau_bench/agents/tool_calling_agent.py#L27
    total_cost = 0.0
    env_reset_res = env.reset(task_index=task_index)
    obs = env_reset_res.observation
    info = env_reset_res.info.model_dump()
    reward = 0.0

    # messages = [
    #     {"role": "system", "content": env.wiki},
    #     {"role": "user", "content": obs},
    # ]

    # Here, instead of calling white agent like calling an LLM, we need to present
    #   the assessment scenario to the white agent as if it is a independent task
    # Specifically, here we provide the tool information for the agent to reply with
    task_description = f"""
{env.wiki}
Here's a list of tools you can use (you can use at most one tool at a time):
{json.dumps(env.tools_info, indent=2)}
Please response in the JSON format. Please wrap the JSON part with <json>...</json> tags.
The JSON should contain:
- "name": the tool call function name, or "{RESPOND_ACTION_NAME}" if you want to respond directly.
- "kwargs": the arguments for the tool call, or {{"content": "your message here"}} if you want to respond directly.

Next, I'll provide you with the user message and tool call results.
User message: {obs}
    """

    next_green_message = task_description
    context_id = None
    for _ in range(max_num_steps):
        # # --> messages (message history)
        # res = completion(
        #     messages=messages,
        #     model=self.model,
        #     custom_llm_provider=self.provider,
        #     tools=self.tools_info,
        #     temperature=self.temperature,
        # )
        # next_message = res.choices[0].message.model_dump()
        # total_cost += res._hidden_params["response_cost"] or 0
        # action = message_to_action(next_message)
        # # --> action (to be executed in the environment)
        print(
            f"@@@ Green agent: Sending message to white agent{'ctx_id=' + str(context_id) if context_id else ''}... -->\n{next_green_message}"
        )
        white_agent_response = await my_a2a.send_message(
            white_agent_url, next_green_message, context_id=context_id
        )
        res_root = white_agent_response.root
        assert isinstance(res_root, SendMessageSuccessResponse)
        res_result = res_root.result
        assert isinstance(
            res_result, Message
        )  # though, a robust design should also support Task
        if context_id is None:
            context_id = res_result.context_id
        else:
            assert context_id == res_result.context_id, (
                "Context ID should remain the same in a conversation"
            )

        text_parts = get_text_parts(res_result.parts)
        assert len(text_parts) == 1, (
            "Expecting exactly one text part from the white agent"
        )
        white_text = text_parts[0]
        print(f"@@@ White agent response:\n{white_text}")
        # parse the action out
        white_tags = parse_tags(white_text)
        action_json = white_tags["json"]
        action_dict = json.loads(action_json)
        action = Action(**action_dict)

        env_response = env.step(action)
        reward = env_response.reward
        info = {**info, **env_response.info.model_dump()}

        # instead of maintain history, just prepare the next message with the latest observation
        if action.name != RESPOND_ACTION_NAME:
            next_green_message = f"""
Tool call result:
{env_response.observation}
            """
        else:
            next_green_message = f"""
User message:
{env_response.observation}
            """
        if env_response.done:
            break

    return SolveResult(
        reward=reward,
        info=info,
        messages=[],  # incompatible, thus removed
        total_cost=total_cost,
    )


class TauGreenAgentExecutor(AgentExecutor):
    def __init__(self):
        pass

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # parse the task
        print("Green agent: Received a task, parsing...")
        user_input = context.get_user_input()
        tags = parse_tags(user_input)
        white_agent_url = tags["white_agent_url"]
        env_config_str = tags["env_config"]
        env_config = json.loads(env_config_str)

        # set up the environment
        # migrate from https://github.com/sierra-research/tau-bench/blob/4754e6b406507dbcbce8e8b3855dcf80aaec18ac/tau_bench/run.py#L20
        print("Green agent: Setting up the environment...")
        assert len(env_config["task_ids"]) == 1, (
            "Only single task supported for demo purpose"
        )
        task_index = env_config["task_ids"][0]
        env = get_env(
            env_name=env_config["env"],
            user_strategy=env_config["user_strategy"],
            user_model=env_config["user_model"],
            task_split=env_config["task_split"],
            user_provider=env_config.get("user_provider", None),
            task_index=task_index,
        )
        metrics = {}

        print("Green agent: Starting evaluation...")
        timestamp_started = time.time()
        # TODO: replace
        # agent = ToolCallingAgent(
        #     tools_info=env.tools_info,
        #     wiki=env.wiki,
        #     model="openai/gpt-4o",
        #     provider="openai",
        # )
        # res = agent.solve(
        #     env=env,
        #     task_index=task_index,
        # )
        res = await ask_agent_to_solve(white_agent_url, env, task_index)

        metrics["time_used"] = time.time() - timestamp_started
        result_bool = metrics["success"] = res.reward == 1
        result_emoji = "✅" if result_bool else "❌"

        print("Green agent: Evaluation complete.")
        await event_queue.enqueue_event(
            new_agent_text_message(
                f"Finished. White agent success: {result_emoji}\nMetrics: {metrics}\n"
            )
        )  # alternative, impl as a task-generating agent

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def start_green_agent(agent_name="tau_green_agent", host="localhost", port=9001):
    print("Starting green agent...")
    agent_card_dict = load_agent_card_toml(agent_name)
    url = f"http://{host}:{port}"
    agent_card_dict["url"] = url  # complete all required card fields

    request_handler = DefaultRequestHandler(
        agent_executor=TauGreenAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=AgentCard(**agent_card_dict),
        http_handler=request_handler,
    )

    uvicorn.run(app.build(), host=host, port=port)
