"""通过 A2A 协议编排三个旅游专家的命令行管家。"""

import asyncio
import os
import sys

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest
from dotenv import load_dotenv

from agent_runtime import ask_deepseek

load_dotenv()

AGENT_URLS = {
    "景点专家": "http://127.0.0.1:8001",
    "美食专家": "http://127.0.0.1:8002",
    "行程专家": "http://127.0.0.1:8003",
}


def task_artifact_text(event: object) -> str:
    """从 A2A 完成事件的 Artifact 中读取文本。"""
    payload_type = event.WhichOneof("payload")
    if payload_type != "task":
        return ""
    task = event.task
    artifacts = getattr(task, "artifacts", None) or []
    texts = []
    for artifact in artifacts:
        for part in artifact.parts:
            root = getattr(part, "root", part)
            text = getattr(root, "text", None)
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


async def call_agent(name: str, query: str) -> str:
    url = AGENT_URLS[name]
    try:
        async with httpx.AsyncClient(timeout=180.0) as http_client:
            card = await A2ACardResolver(http_client, url).get_agent_card()
            client = await create_client(
                agent=card,
                client_config=ClientConfig(streaming=False, httpx_client=http_client),
            )
            request = SendMessageRequest(
                message=new_text_message(query, role=Role.ROLE_USER)
            )
            result = ""
            async for event in client.send_message(request):
                result = task_artifact_text(event) or result
            await client.close()
    except Exception as exc:
        raise RuntimeError(f"调用{name}失败（{url}）：{exc}") from exc

    if not result:
        raise RuntimeError(f"{name}返回的 A2A Task 中没有文本 Artifact。")
    return result


async def plan_trip(user_request: str) -> str:
    print("[管家] 正在通过 Agent Card 发现景点专家和美食专家……")
    attraction, food = await asyncio.gather(
        call_agent("景点专家", user_request),
        call_agent("美食专家", user_request),
    )

    itinerary_input = (
        f"原始需求：\n{user_request}\n\n"
        f"景点专家建议：\n{attraction}\n\n"
        f"美食专家建议：\n{food}"
    )
    print("[管家] 正在把两位专家的建议交给行程专家……")
    itinerary = await call_agent("行程专家", itinerary_input)

    model = os.getenv("BUTLER_MODEL_ID") or "deepseek-v4-pro"
    print(f"[旅游管家] model={model}，正在生成最终方案……")
    return await ask_deepseek(
        system_prompt=(
            "你是旅游管家。请根据用户原始需求和行程专家方案，输出一份清晰、"
            "简洁、可执行的最终旅行方案。保留重要注意事项，并明确提示票价、"
            "营业时间、交通和预订信息需要出发前再次核实。"
        ),
        user_text=f"原始需求：\n{user_request}\n\n行程专家方案：\n{itinerary}",
        model=model,
    )


def get_user_request() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:]).strip()
    return input("请输入你的旅行需求：").strip()


def console_safe(text: str) -> str:
    """避免 Windows GBK 终端因模型返回 Emoji 而中断。"""
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


if __name__ == "__main__":
    request_text = get_user_request()
    if not request_text:
        print("错误：旅行需求不能为空。", file=sys.stderr)
        raise SystemExit(1)
    try:
        answer = asyncio.run(plan_trip(request_text))
    except Exception as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1) from error
    print("\n========== 旅游管家方案 ==========\n")
    print(console_safe(answer))
