"""三个旅游专家共用的 A2A 服务实现。"""

import os
from dataclasses import dataclass

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    TaskState,
)
from a2a.utils.errors import UnsupportedOperationError
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from starlette.applications import Starlette

load_dotenv()


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    name: str
    description: str
    skill_name: str
    skill_description: str
    prompt: str
    port: int


AGENTS = (
    AgentDefinition(
        key="attraction",
        name="景点推荐专家",
        description="根据旅行需求推荐景点和游览重点。",
        skill_name="推荐景点",
        skill_description="推荐适合用户兴趣、时间和预算的景点。",
        prompt=(
            "你是景点推荐专家。请根据用户的目的地、天数、预算和兴趣，"
            "给出精简且有取舍的景点建议，说明推荐理由和大致游览时长。"
            "不要虚构实时票价、营业时间或库存，提醒用户出发前核实。"
        ),
        port=8001,
    ),
    AgentDefinition(
        key="food",
        name="美食推荐专家",
        description="根据旅行需求推荐当地美食和用餐安排。",
        skill_name="推荐美食",
        skill_description="推荐当地代表性食物和适合的用餐区域。",
        prompt=(
            "你是美食推荐专家。请根据用户的目的地、预算和偏好，"
            "推荐当地代表性食物、适合的用餐区域和避坑提示。"
            "不要虚构实时价格、营业状态或具体店铺库存，提醒用户核实。"
        ),
        port=8002,
    ),
    AgentDefinition(
        key="itinerary",
        name="行程规划专家",
        description="把需求以及其他专家建议整理为逐日行程。",
        skill_name="规划行程",
        skill_description="综合景点和美食建议生成可执行的逐日路线。",
        prompt=(
            "你是行程规划专家。输入中会包含原始旅行需求、景点专家建议和"
            "美食专家建议。请减少折返，给出按天、上午/下午/晚上的简洁行程，"
            "并保留必要的弹性时间。不要声称掌握实时信息。"
        ),
        port=8003,
    ),
)


def model_for(agent_key: str) -> str:
    """专用模型变量优先，其次使用全局 MODEL_ID，最后使用 Flash。"""
    variable = f"{agent_key.upper()}_MODEL_ID"
    return os.getenv(variable) or os.getenv("MODEL_ID") or "deepseek-v4-flash"


def make_deepseek_client() -> AsyncAnthropic:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，请先在 .env 中配置。")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic")
    return AsyncAnthropic(api_key=api_key, base_url=base_url)


async def ask_deepseek(system_prompt: str, user_text: str, model: str) -> str:
    response = await make_deepseek_client().messages.create(
        model=model,
        max_tokens=1200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_text}],
    )
    text = "\n".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        raise RuntimeError("DeepSeek 没有返回文本内容。")
    return text


class TravelAgentExecutor(AgentExecutor):
    """把 A2A 请求转换为一次 DeepSeek 调用。"""

    def __init__(self, definition: AgentDefinition) -> None:
        self.definition = definition

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A 请求中缺少消息。")

        task = context.current_task or new_task_from_user_message(context.message)
        if context.current_task is None:
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message(f"{self.definition.name}正在处理请求……"),
        )

        query = get_message_text(context.message)
        if not query:
            raise ValueError("只支持非空的 text/plain 消息。")

        model = model_for(self.definition.key)
        print(f"[{self.definition.name}] model={model}")
        result = await ask_deepseek(self.definition.prompt, query, model)
        await updater.add_artifact(
            parts=[new_text_part(text=result, media_type="text/plain")],
            name="result",
        )
        await updater.update_status(state=TaskState.TASK_STATE_COMPLETED)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError(message="此学习 Demo 不支持取消任务。")


def create_agent_app(definition: AgentDefinition) -> Starlette:
    skill = AgentSkill(
        id=f"{definition.key}_recommendation",
        name=definition.skill_name,
        description=definition.skill_description,
        tags=["travel", definition.key],
        examples=["我想去成都玩3天，预算3000元，喜欢历史和美食。"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    )
    card = AgentCard(
        name=definition.name,
        description=definition.description,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=f"http://127.0.0.1:{definition.port}",
                protocol_version="1.0",
            )
        ],
        skills=[skill],
    )
    handler = DefaultRequestHandler(
        agent_executor=TravelAgentExecutor(definition),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = [
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, "/"),
    ]
    return Starlette(routes=routes)
