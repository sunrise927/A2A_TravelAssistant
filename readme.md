# 基于 A2A 的旅游管家 Demo

这是一个用于学习 Agent2Agent（A2A）协议的最小 Python 示例。命令行旅游管家会通过标准 A2A 接口调用景点、美食和行程三个专家，所有 Agent 都使用 DeepSeek。

## 项目结构

```text
agent_runtime.py   三个专家共用的 Agent Card、Executor 和服务逻辑
run_agents.py      同时启动三个 A2A 服务
butler.py          A2A 客户端和旅游管家编排逻辑
requirement.txt    Python 依赖
知识讲解.md         A2A 概念与本项目流程说明
```

## 环境要求

- Python 3.10 或以上
- 可用的 DeepSeek API Key

## 安装

在 PowerShell 中执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirement.txt
```

项目会读取当前目录的 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的API密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/anthropic
MODEL_ID=deepseek-v4-flash
```

现有 `.env` 已包含这些字段，请不要把真实密钥提交到公开仓库。

## 运行

打开第一个 PowerShell，启动三个专家：

```powershell
.venv\Scripts\Activate.ps1
python run_agents.py
```

看到三个本地地址后，打开第二个 PowerShell：

```powershell
.venv\Scripts\Activate.ps1
python butler.py "我想去成都玩3天，预算3000元，喜欢历史和美食"
```

也可以直接执行 `python butler.py`，再根据提示输入需求。按 `Ctrl+C` 可停止三个专家服务。

## Agent 地址

| Agent | 服务地址 | Agent Card |
|---|---|---|
| 景点专家 | `http://127.0.0.1:8001` | `http://127.0.0.1:8001/.well-known/agent-card.json` |
| 美食专家 | `http://127.0.0.1:8002` | `http://127.0.0.1:8002/.well-known/agent-card.json` |
| 行程专家 | `http://127.0.0.1:8003` | `http://127.0.0.1:8003/.well-known/agent-card.json` |

## 为每个 Agent 选择模型

默认三个专家使用 `.env` 中的 `MODEL_ID`，没有设置时使用 `deepseek-v4-flash`；管家默认使用 `deepseek-v4-pro`。可以在 `.env` 中增加：

```dotenv
ATTRACTION_MODEL_ID=deepseek-v4-flash
FOOD_MODEL_ID=deepseek-v4-flash
ITINERARY_MODEL_ID=deepseek-v4-flash
BUTLER_MODEL_ID=deepseek-v4-pro
```

启动日志会显示每个 Agent 实际使用的模型。

## 注意

这是协议学习 Demo，不包含实时天气、地图、票价、库存或预订接口。模型给出的营业时间、价格、交通和店铺信息必须在出发前通过官方渠道核实。

如果出现连接失败，请先确认 `run_agents.py` 正在运行且 8001～8003 端口没有被占用。如果出现鉴权或模型错误，请检查 `.env` 中的 API Key、Base URL 和模型名称。
