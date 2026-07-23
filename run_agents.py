"""在一个进程中启动三个本地 A2A 专家服务。"""

import asyncio

import uvicorn

from agent_runtime import AGENTS, create_agent_app


async def main() -> None:
    servers = []
    for definition in AGENTS:
        print(f"启动 {definition.name}: http://127.0.0.1:{definition.port}")
        config = uvicorn.Config(
            create_agent_app(definition),
            host="127.0.0.1",
            port=definition.port,
            log_level="warning",
            lifespan="off",
        )
        servers.append(uvicorn.Server(config).serve())
    await asyncio.gather(*servers)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n三个专家服务已停止。")
