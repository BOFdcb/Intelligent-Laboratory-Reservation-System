# 《智能实验室预约系统》LangGraph 智能体精讲

> 面向零基础读者・以本项目真实代码为主线・建议打开 VS Code 对照 
>
> `backend/app/agent.py`
>
> 、
>
> `backend/app/tools.py`
>
> 、
>
> `backend/app/routers/chat.py`
>
>  同步阅读
> 本文只讲 
>
> **LangGraph**
>
>  这一条主线（智能体流程编排），FastAPI 基础见《doubao_FastAPI.md》。

***

## 阅读指南



* 核心文件只有 3 个：

  * `app/agent.py`（★ 主角：状态图定义与编译，117 行）

  * `app/tools.py`（工具的 "菜单" 与 "执行器"，agent 的行动能力）

  * `app/routers/chat.py`（把图和 FastAPI 的 SSE 流式对接起来）

* 建议先跑起来：启动后端后，在前端聊天页输入 "帮我预约明天下午的实验室"，观察页面一步步展示 "思考→查工具→结果→提交"，再看本文，理解会翻倍。

* 文中【大白话】是通俗解释；【关键点】是要记住的结论。



***

## 第 1 章 LangGraph 是什么

### 1.1 智能体要解决什么问题

【大白话】普通 AI 聊天是 "一问一答"。但你的预约助手要**办成一件事**：



1. 理解用户想预约；

2. 查有哪些实验室；

3. 查目标时段是否空闲；

4. 跟用户确认信息；

5. 真正提交预约（写数据库）。

这是一条**多步骤、有分支、会循环**的流程。如果全部用 `while True` 手写，代码会变成一团乱麻，而且没法可视化、没法中途暂停、没法给前端展示过程。

### 1.2 LangGraph 的答案：把流程画成 "图"

LangGraph 是 LangChain 生态里的一个框架，核心思想：**把你的 AI 流程画成一张有方向的图（节点 + 边），它负责把图跑起来。**



* **节点（Node）** = 流程里的一个步骤（本项目：`llm` 思考、`tools` 行动）；

* **边（Edge）** = 步骤之间的固定连线；

* **条件边（Conditional Edge）** = 岔路口，根据状态决定走哪条路；

* **状态（State）** = 一路上传递的 "公文包"，所有节点共享。

### 1.3 本项目的图长什么样



```
START（入口）
  │  固定边
  ▼
llm 节点（思考：把对话历史 + 工具菜单发给大模型）
  │  条件边 should_continue
  ├───── 有 tool_calls 且 rounds < 8 ────► tools 节点（行动：执行工具函数）
  │                                              │  固定边
  │                                              ▼
  └───── 无 tool_calls / 超 8 轮            （工具结果回填 messages）
  │                                              │
  ▼                                              │
END（输出最终答复）        ◄──────────────────────┘
```

一句话：**大模型 "思考"→ 想用工具就去 "行动"→ 结果拿回来再 "思考"→ …… 直到它觉得搞定了，输出最终答复。** 这就是智能体（Agent）最经典的工作循环：ReAct（Reason + Act）。



***

## 第 2 章 四大核心概念（对照 agent.py）



| 概念  | 英文               | agent.py 里的对应                | 大白话           |
| --- | ---------------- | ---------------------------- | ------------- |
| 状态  | State            | `AgentState(TypedDict)`      | 节点之间传递的 "公文包" |
| 节点  | Node             | `llm_node` / `tools_node`    | 流程图上的一个步骤     |
| 边   | Edge             | `add_edge(START, "llm")`     | 固定路线，走完必到下一步  |
| 条件边 | Conditional Edge | `add_conditional_edges(...)` | 岔路口，根据情况选路    |

【关键点】**节点是普通 Python 函数**：接收 `state`，返回一个 dict（要更新的字段）。LangGraph 自动把返回的 dict 合并进状态，再传给下一个节点。你不用手动管理 "状态在哪里、谁改的"。



***

## 第 3 章 State：AgentState 精讲

来自 `agent.py` 第 29-36 行：



```
class AgentState(TypedDict):
    """图中流转的状态：节点返回的 dict 会整体更新对应字段。"""

    messages: list[dict]  # OpenAI 格式的对话消息（system/user/assistant/tool）
    rounds: int           # 已执行的 LLM 轮次
    db: Session           # 数据库会话（工具节点使用）
    user_id: int          # 当前用户 ID（create_booking 使用）
    events: list[dict]    # 过程事件（tool_call / tool_result），供 SSE 输出
```

### 3.1 为什么用 TypedDict



```
from typing import TypedDict
```



* `TypedDict` 是 Python 的 "**带类型的字典**"：它要求 `messages` 是 list、`rounds` 是 int…… 但运行时它**就是普通 dict**，不强制检查；

* LangGraph 官方推荐用它定义 State：编辑器能有代码补全和类型提示，写错字段立刻飘红；

* 运行时的灵活性保留 —— 节点返回的 dict 只要包含要更新的 key 即可，不必每次把整个 State 都返回。

### 3.2 每个字段的职责



| 字段         | 类型          | 谁写                | 干什么             |
| ---------- | ----------- | ----------------- | --------------- |
| `messages` | list\[dict] | llm/tools 节点都追加   | 大模型的 "记忆"，会越滚越长 |
| `rounds`   | int         | llm 节点 +1         | 记 "思考了几轮"，防死循环  |
| `db`       | Session     | 外部传入（chat.py 初始化） | 工具节点查库 / 写库用的会话 |
| `user_id`  | int         | 外部传入              | 提交预约时记录 "谁预约的"  |
| `events`   | list\[dict] | llm/tools 节点都追加   | 过程事件，前端按它展示进度   |

### 3.3 状态更新的规则（最核心的机制）

```
初始 State（chat.py 构造）
  messages=[system, user]   rounds=0   db=会话   user_id=3   events=[]

执行 llm 节点 → 返回 {"messages": [...+assistant], "rounds": 1, "events": [...]}
  → LangGraph 把这些字段合并进 State：messages 变长、rounds 变 1、events 变长
  → 其他字段（db、user_id）原样保留

执行 tools 节点 → 返回 {"messages": [...+tool], "events": [...]}
  → 继续合并……
```

【关键点】**每个节点只 "增量更新" 自己关心的字段**，返回的 dict 被整体合并。这就是 "状态图" 的含义：状态在节点间流转、累积。



***

## 第 4 章 节点一：`llm_node` —— 思考

来自 `agent.py` 第 40-63 行：



```
def llm_node(state: AgentState) -> dict:
    client = get_llm_client()                                  # ① 拿大模型客户端
    resp = client.chat.completions.create(
        model=settings.LLM_MODEL,                              # ② 指定模型
        messages=state["messages"],                            # ③ 整个对话历史
        tools=TOOLS_SCHEMA,                                    # ④ 告诉大模型"你能用这些工具"
        tool_choice="auto",                                    # ⑤ 让它自己决定用不用
    )
    msg = resp.choices[0].message                              # ⑥ 大模型的回复
    assistant = {"role": "assistant", "content": msg.content or ""}
    events: list[dict] = []
    if msg.tool_calls:                                         # ⑦ 它想调用工具！
        assistant["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
        for tc in assistant["tool_calls"]:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            events.append({"type": "tool_call", "name": tc["function"]["name"], "arguments": args})
    return {
        "messages": state["messages"] + [assistant],           # ⑧ 追加 assistant 消息
        "rounds": state["rounds"] + 1,                         # ⑨ 轮次 +1
        "events": state["events"] + events,                    # ⑩ 追加事件
    }
```

逐段拆解：



| #   | 代码                              | 大白话                                                 |
| --- | ------------------------------- | --------------------------------------------------- |
| ①   | `get_llm_client()`              | 从 `llm.py` 拿 OpenAI 兼容客户端（连 MiniMax）                |
| ②   | `model=settings.LLM_MODEL`      | 用配置里的模型名（MiniMax-M3）                                |
| ③   | `messages=state["messages"]`    | 把**全部**对话历史发给大模型 —— 它靠这个 "记住" 前面说了什么                |
| ④   | `tools=TOOLS_SCHEMA`            | 附上工具清单（JSON Schema），大模型 "知道" 有这些工具可用                |
| ⑤   | `tool_choice="auto"`            | 让大模型自主判断 "要不要调用工具、调用哪个"                             |
| ⑥   | `msg = resp.choices[0].message` | 取出大模型的回复消息                                          |
| ⑦   | `msg.tool_calls`                | **关键**：如果大模型决定用工具，回复里会带 `tool_calls`（工具名 + 参数），否则为空 |
| ⑧   | `messages + [assistant]`        | 把 assistant 消息追加进历史                                 |
| ⑨   | `rounds + 1`                    | 记一次 "思考"，供轮次上限判断                                    |
| ⑩   | `events + events`               | 记录 "调用了哪个工具" 事件，前端可展示                               |

【关键点】**llm 节点不执行任何真实操作**。它只做一件事：把 "记忆 + 工具清单" 发给大模型，看它想说什么、想不想用工具。大模型给出的 `tool_calls` 只是一张 "申请单"。



***

## 第 5 章 节点二：`tools_node` —— 行动

来自 `agent.py` 第 67-91 行：



```
def tools_node(state: AgentState) -> dict:
    last = state["messages"][-1]                               # ① 取最后一条消息（assistant）
    new_messages = list(state["messages"])
    events = list(state["events"])
    for tc in last.get("tool_calls") or []:                    # ② 遍历所有工具申请
        name = tc["function"]["name"]                          # ③ 工具名
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        func = TOOL_DISPATCH.get(name)                         # ④ 菜单名 → 真实函数
        if not func:
            result = {"error": f"未知工具 {name}"}
        else:
            try:
                result = func(state["db"], user_id=state["user_id"], **args)   # ⑤ 真正执行！
            except Exception as e:
                result = {"error": str(e)}                    # ⑥ 工具报错也兜住
        new_messages.append({
            "role": "tool",                                    # ⑦ 结果包成 tool 消息
            "tool_call_id": tc["id"],                         # ⑧ 关联"是哪次申请的结果"
            "content": json.dumps(result, ensure_ascii=False),
        })
        events.append({"type": "tool_result", "name": name, "result": result})
    return {"messages": new_messages, "events": events}
```

逐段拆解：



| #   | 代码                                       | 大白话                                            |
| --- | ---------------------------------------- | ---------------------------------------------- |
| ①   | `last = state["messages"][-1]`           | 上一步 llm 节点刚追加的 assistant 消息，里面可能有 `tool_calls` |
| ②   | `for tc in last.get("tool_calls") or []` | 大模型一次可以申请多个工具，逐个执行                             |
| ③   | `name = tc["function"]["name"]`          | 取工具名（如 `check_availability`）                   |
| ④   | `func = TOOL_DISPATCH.get(name)`         | **查表**：从名字找到真正的 Python 函数（第 8 章细讲）             |
| ⑤   | `func(state["db"], user_id=..., **args)` | **真正的执行点**：调数据库、做校验、写记录                        |
| ⑥   | `except Exception`                       | 工具内部报错也不让整个图崩掉，转成 `{"error": ...}`             |
| ⑦   | `role: "tool"`                           | 执行结果以 "工具消息" 身份放回对话                            |
| ⑧   | `tool_call_id`                           | 和 assistant 的申请单用 id 配对 —— 大模型靠它认领结果           |

【关键点】**执行权和数据库的钥匙永远在你自己手里**。大模型只输出 "我想调用 check\_availability，参数是 {lab\_id: 1, ...}"，真正去查数据库的是 `tools.py` 里的函数。



***

## 第 6 章 条件边：`should_continue` 与轮次控制

来自 `agent.py` 第 95-99 行：



```
def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if last.get("tool_calls") and state["rounds"] < MAX_ROUNDS:
        return "tools"        # 大模型还想用工具 → 去执行工具
    return END                # 没想用工具（或超 8 轮）→ 结束
```

### 6.1 条件边的工作原理



* 条件边函数是**普通函数**：接收 state，**返回一个字符串**（`"tools"` 或 `"end"`）；

* 返回值会被拿去查 "路由表"（第 7 章 `{"tools": "tools", END: END}`），决定下一个节点；

* 这就是 "岔路口"：同一节点出发，不同情况走不同路。

### 6.2 两种 "结束" 情况



| 情况             | 判断                      | 结果           |
| -------------- | ----------------------- | ------------ |
| 大模型决定不再用工具     | `last` 里没有 `tool_calls` | 走 END，输出最终答复 |
| 大模型一直想用工具但轮次超限 | `rounds >= 8`           | 强制 END，防止死循环 |

### 6.3 `MAX_ROUNDS = 8` 为什么要设上限

【大白话】如果大模型每次都说 "我还要再查一个工具"，图就会无限循环下去（每次还花钱调大模型）。`MAX_ROUNDS = 8` 就是**安全阀**：最多思考 8 轮，到点强制收工，宁可答得糙一点，不能把服务器拖死。

【关键点】`rounds` 由 llm 节点 +1。条件边判断的是 "**已经**思考了几轮 "：第 8 轮时如果还想用工具，`rounds < 8` 为假 → END。



***

## 第 7 章 组装与编译：`build_agent_graph`

来自 `agent.py` 第 102-116 行：



```
def build_agent_graph():
    """构建并编译预约 Agent 状态图。"""
    builder = StateGraph(AgentState)              # ① 创建画布，声明状态类型
    builder.add_node("llm", llm_node)            # ② 画上"思考"节点
    builder.add_node("tools", tools_node)        # ③ 画上"行动"节点
    builder.add_edge(START, "llm")               # ④ 固定边：入口 → 思考
    builder.add_conditional_edges(               # ⑤ 条件边：思考后的岔路口
        "llm", should_continue, {"tools": "tools", END: END}
    )
    builder.add_edge("tools", "llm")             # ⑥ 固定边：行动完 → 回去再思考
    return builder.compile()                     # ⑦ 编译成可运行对象


# 编译产物可复用（无状态，请求级数据都在 AgentState 里）
agent_graph = build_agent_graph()
```

逐行拆解：



| #   | 代码                                      | 作用                                              |
| --- | --------------------------------------- | ----------------------------------------------- |
| ①   | `StateGraph(AgentState)`                | 新建状态图，告诉它 "状态长什么样"                              |
| ②③  | `add_node("名字", 函数)`                    | 注册节点：起个名字，绑定函数                                  |
| ④   | `add_edge(START, "llm")`                | 固定边：图一启动就进 llm 节点                               |
| ⑤   | `add_conditional_edges("llm", fn, 路由表)` | 岔路口：`llm` 执行完，调用 `should_continue`，按返回值查路由表     |
| ⑥   | `add_edge("tools", "llm")`              | 固定边：工具执行完，把结果带回 llm 再思考                         |
| ⑦   | `compile()`                             | 把图 "编译" 成可调用对象（类似 `agent_graph.stream(...)` 入口） |

### 7.1 路由表是什么



```
{"tools": "tools", END: END}
```

条件边函数的返回值是 key，路由表给出 "下一个节点名"。所以：



* `should_continue` 返回 `"tools"` → 走 `tools` 节点；

* 返回 `END` → 结束（END 是 LangGraph 内置的 "终点" 标记）。

### 7.2 为什么编译一次、全局复用



```
agent_graph = build_agent_graph()   # 模块加载时编译一次
```



* 编译后的图是**无状态的**：它只包含 "怎么走" 的结构，不包含任何用户数据；

* 每个请求的数据（messages、db、user\_id）都存在 `AgentState` 里，由请求自己构造；

* 所以**一张图可以同时服务无数个用户的请求**，不用每次请求重新编译。

【关键点】LangGraph 的图 = 一份 "路线图"（静态、可复用）；State = 每位旅客的 "行李"（动态、请求级）。



***

## 第 8 章 工具怎么被调用（tools.py 快速回顾）

agent 之所以能 "动手"，全靠 `tools.py` 提供的两个东西：**菜单**和**执行器**。

### 8.1 菜单 `TOOLS_SCHEMA`：告诉大模型 "你会什么"



```
TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "check_availability",
        "description": "查询某实验室在某天的预约占用情况，判断哪些时段空闲",
        "parameters": {
            "type": "object",
            "properties": {
                "lab_id": {"type": "integer", "description": "实验室ID"},
                "booking_date": {"type": "string", "description": "日期，格式 YYYY-MM-DD"},
            },
            "required": ["lab_id", "booking_date"],
        },
    }},
    # ... 共 5 个工具
]
```

【大白话】菜单 = JSON 描述。大模型**不会执行**这些工具，它只是 "读菜单、点菜"。`description` 写得越清楚，大模型越知道 "什么时候该点这道菜"。

5 个工具一览：



| 工具名                  | 干什么          | 需要参数                                                    |
| -------------------- | ------------ | ------------------------------------------------------- |
| `list_labs`          | 查所有实验室       | 无                                                       |
| `get_lab_equipment`  | 查某实验室设备      | lab\_id                                                 |
| `check_availability` | 查某天空闲时段      | lab\_id, booking\_date                                  |
| `search_rules`       | 检索规则知识库（RAG） | query                                                   |
| `create_booking`     | 提交预约（写库）     | lab\_id, booking\_date, start\_time, end\_time, purpose |

### 8.2 执行器 `TOOL_DISPATCH`：菜单名 → 真实函数



```
TOOL_DISPATCH = {
    "list_labs": tool_list_labs,
    "get_lab_equipment": tool_get_lab_equipment,
    "check_availability": tool_check_availability,
    "search_rules": tool_search_rules,
    "create_booking": tool_create_booking,
}
```

【大白话】这是 "菜单名 → 后厨" 的对照表。`tools_node` 第 ④ 步 `TOOL_DISPATCH.get(name)` 就是靠它把大模型的 "申请单" 变成真实函数调用。

### 8.3 工具函数的统一签名



```
def tool_check_availability(db: Session, lab_id: int, booking_date: str, **_) -> dict:
    # 查库 → 返回 dict（可能是 {"lab":..., "occupied_slots":[...]}，也可能是 {"error": "..."}）
```



* 第一个参数固定是 `db`（tools\_node 传 `state["db"]`）；

* 工具函数**永远返回 dict**，会被 `json.dumps` 成字符串塞进 tool 消息；

* 返回 `{"error": ...}` 也是正常设计：大模型看到错误会自己调整策略（比如换个时段）。



***

## 第 9 章 与 FastAPI 对接：`/api/chat/agent` 接口

图写好了，怎么暴露给前端？看 `routers/chat.py` 的 agent 接口（第 105-157 行）。

### 9.1 系统提示词（AI 的行为准则）



```
AGENT_SYSTEM = """你是智能实验室预约助手。今天是 {today}。

你可以使用工具查询实验室、设备、空闲时段、使用规则，并帮助用户提交预约。

工作流程：
1. 理解用户意图。若用户想预约但信息不全（缺实验室/日期/时段/用途），请追问澄清。
2. 预约前先用 check_availability 查询目标时段是否空闲；若冲突，建议其他时段。
3. 信息齐全后，先向用户复述预约信息请其确认，得到肯定答复后再调用 create_booking。
4. 规则类问题用 search_rules 检索。
5. 所有回复使用中文，简洁友好。"""
```

【大白话】系统提示词就是给 AI 定的**工作手册**：先澄清、再查空闲、确认后才提交。大模型严格照做，这就是 "可控的智能体"。

### 9.2 构造初始状态并启动图



```
state = {
    "messages": messages,        # system + 历史 + 用户新消息
    "rounds": 0,                 # 从第 0 轮开始
    "db": db,                    # FastAPI 注入的数据库会话
    "user_id": current_user.id,  # 当前登录用户
    "events": [],                # 事件从空开始
}
for update in agent_graph.stream(state, stream_mode="updates"):
    node_name, node_state = next(iter(update.items()))
    ...
```

### 9.3 `stream(stream_mode="updates")` 是什么

LangGraph 提供多种流式模式，本项目用 `"updates"`：



| 模式           | 产出                 | 适用场景       |
| ------------ | ------------------ | ---------- |
| `"values"`   | 每次节点执行后**完整的新状态**  | 想看每步全貌     |
| `"updates"`  | 每个节点**返回的增量 dict** | 本项目：只关心新变化 |
| `"messages"` | 逐条消息级产出            | 聊天应用逐字流式   |

`"updates"` 模式下，每次迭代 `update` 是形如 `{"llm": {...返回的增量...}}` 的字典，所以代码用 `next(iter(update.items()))` 取出「节点名 + 该节点返回的状态增量」。

### 9.4 事件游标技巧（只输出新事件）



```
event_cursor = 0                          # 已输出的事件位置
for update in agent_graph.stream(state, stream_mode="updates"):
    node_name, node_state = next(iter(update.items()))
    events = node_state.get("events") or []
    for ev in events[event_cursor:]:      # 只取"新多出来"的事件
        yield _sse(ev)                    # 推给前端
    event_cursor = max(event_cursor, len(events))
```

【大白话】`events` 在状态里是**只增不减**的列表（llm 加 tool\_call 事件，tools 加 tool\_result 事件）。用游标记住 "上次输出到哪了"，每次只推送新事件 —— 否则同一个事件会被重复推送好多次。

### 9.5 取最终答复



```
if final_state:
    answer = final_state["messages"][-1].get("content") or ""
if answer:
    yield _sse({"type": "answer", "content": answer})
```

【大白话】图结束时，`messages` 的最后一条就是大模型的最终答复（此时它已经看完所有工具结果、不再申请新工具）。

### 9.6 前端看到的事件流（真实格式）



```
data: {"type":"thinking","content":"思考中（第1轮）..."}
data: {"type":"tool_call","name":"list_labs","arguments":{}}
data: {"type":"tool_result","name":"list_labs","result":{"labs":[...]}}
data: {"type":"thinking","content":"思考中..."}
data: {"type":"tool_call","name":"check_availability","arguments":{"lab_id":1,"booking_date":"2026-10-05"}}
data: {"type":"tool_result","name":"check_availability","result":{...}}
data: {"type":"answer","content":"好的，AI 实验室明天 14:00-16:00 空闲，已为你提交预约，等待管理员审核。"}
data: {"type":"done"}
```

【关键点】整个接口 30 行左右，核心就是 `for update in agent_graph.stream(...)` 这个循环 ——**LangGraph 负责跑图，FastAPI 负责把图的每一步 "直播" 给前端**。



***

## 第 10 章 一次运行的完整过程（把全书串起来）

以用户说 "帮我预约明天下午的实验室" 为例：



| 轮   | 执行节点  | messages 发生了什么                                                                  | rounds |
| --- | ----- | ------------------------------------------------------------------------------- | ------ |
| 0   | （构造）  | `[system, user]`                                                                | 0      |
| 1   | llm   | 大模型发现信息不全（不知道哪个实验室 / 几点）→ 返回纯文字："请问您想预约哪个实验室、几点到几点？"（无 tool\_calls）             | 1      |
| 2   | llm   | 用户回复 "AI 实验室，明天 14:00-16:00" → 大模型决定先查空闲 → 返回 `tool_calls=[check_availability]` | 2      |
| —   | tools | 执行 `check_availability` → 结果包成 tool 消息                                          | 2      |
| 3   | llm   | 看到结果（空闲）→ 复述信息请用户确认（无 tool\_calls）                                              | 3      |
| 4   | llm   | 用户说 "确认" → 大模型返回 `tool_calls=[create_booking]`                                  | 4      |
| —   | tools | 执行 `create_booking` → 写库成功，返回 `{"booking_id": 12, ...}`                         | 4      |
| 5   | llm   | 看到提交成功 → 输出最终答复（无 tool\_calls）                                                  | 5      |
| —   | （条件边） | 无 tool\_calls → END                                                             | 5      |

注意：`llm` 节点和 `tools` 节点**交替执行**，中间夹着 "用户说话"（历史里的 user 消息）。每执行一次 llm，`rounds` +1。整个过程就是 ReAct 循环：**推理 → 行动 → 观察结果 → 再推理**。



***

## 第 11 章 概念对比：LangGraph vs 其他写法

### 11.1 手写 while 循环 vs LangGraph



```
# 手写版（示意，不推荐）：逻辑混在一起，没法可视化、难维护
while True:
    resp = llm(messages, tools)
    if not resp.tool_calls:
        break
    for tc in resp.tool_calls:
        result = dispatch(tc)
        messages.append(tool_message(result))
```



| 维度      | 手写循环           | LangGraph     |
| ------- | -------------- | ------------- |
| 可读性     | 流程藏在代码里        | 节点 / 边一目了然    |
| 可视化     | 无              | 可画图、可调试       |
| 流式输出    | 要自己造           | `stream()` 内置 |
| 分支 / 循环 | 全靠 if/while 嵌套 | 条件边天然支持       |
| 状态管理    | 手动传参           | State 自动合并    |

### 11.2 LangGraph vs LangChain AgentExecutor（上一代方案）



* `AgentExecutor` 是 LangChain 早期封装，逻辑黑盒、难定制；

* LangGraph 是新一代：**每个节点都可见、可改、可加**。本项目直接手写节点函数，完全掌控流程。

### 11.3 本项目为什么用 LangGraph 而不是别的



1. **过程可见**：`stream(stream_mode="updates")` 让前端能 "直播"AI 的每一步（这是 README 的卖点）；

2. **可控性**：轮次上限、条件分支、工具错误兜底，全部显式写在图里；

3. **轻量**：两个节点就够用，不引入重框架。



***

## 第 12 章 自测与进阶

### 12.1 概念自测（先自己想，再翻前文）



1. LangGraph 里的 State、Node、Edge、Conditional Edge 分别对应 agent.py 的哪些代码？

2. 节点函数的返回值是怎么影响 State 的？（提示：整体合并）

3. `llm_node` 里 `tools=TOOLS_SCHEMA` 的作用是什么？大模型会执行工具吗？

4. `tools_node` 里 `TOOL_DISPATCH.get(name)` 在做什么？

5. `should_continue` 什么时候返回 `"tools"`，什么时候返回 `END`？

6. `MAX_ROUNDS = 8` 防的是什么？如果去掉会怎样？

7. 为什么 `agent_graph` 只在模块加载时编译一次？请求数据存在哪里？

8. `stream_mode="updates"` 产出的 `update` 长什么样？`event_cursor` 为什么要存在？

9. 工具函数返回 `{"error": ...}` 是 bug 吗？大模型会怎么处理？

10. 系统提示词（AGENT\_SYSTEM）在整张图里扮演什么角色？

### 12.2 动手练习（改代码验证理解）



1. 把 `MAX_ROUNDS` 改成 2，然后连续追问需要 3 次工具查询的复杂请求，观察 AI 提前收场 —— 理解轮次上限的意义。

2. 在 `tools.py` 加一个工具 `get_lab_rules`（返回某实验室的 rules 字段），然后在 `TOOLS_SCHEMA` 和 `TOOL_DISPATCH` 各加一条，重启后问 AI"AI 实验室有什么规定"，看它会不会主动调用新工具。

3. 给 `AgentState` 加一个 `user_name: str` 字段，在 `llm_node` 的系统提示里使用它，感受 "状态字段如何跨节点流转"。

4. 把 `chat.py` 的 `stream_mode` 从 `"updates"` 改成 `"values"`，观察打印出来的 state 差异，理解两种模式的区别。

### 12.3 学习路线建议



1. 第 3-7 章是核心：先把 agent.py 的 5 个函数背熟；

2. 用 Swagger 调 `POST /api/chat/agent`，看返回的 SSE 事件流，把 "图在跑" 变成直观感受；

3. 动手加工具（练习 2）是理解 Tool Calling 最快的路径；

4. 之后可以继续学习 LangGraph 进阶特性：并行分支、子图、持久化（Checkpointer）、人工介入（interrupt）—— 本项目还没用到，是很好的延伸方向。



***

## 附录：LangGraph 常用 API 速查



| API                                       | 作用        | 本项目用法                                                                         |
| ----------------------------------------- | --------- | ----------------------------------------------------------------------------- |
| `StateGraph(StateClass)`                  | 创建状态图     | `StateGraph(AgentState)`                                                      |
| `add_node(name, fn)`                      | 注册节点      | `add_node("llm", llm_node)`                                                   |
| `add_edge(src, dst)`                      | 固定边       | `add_edge(START, "llm")`                                                      |
| `add_conditional_edges(src, fn, mapping)` | 条件边       | `add_conditional_edges("llm", should_continue, {"tools": "tools", END: END})` |
| `compile()`                               | 编译成可运行图   | `builder.compile()`                                                           |
| `graph.stream(state, stream_mode=...)`    | 流式运行      | `stream(state, stream_mode="updates")`                                        |
| `START` / `END`                           | 起点 / 终点标记 | 条件边返回 `END`                                                                   |



***

## 一句话总结

**LangGraph = 把 AI 的 "思考 - 行动" 循环画成一张可运行的图**：`AgentState` 是传递的公文包，`llm_node` 负责思考（只申请工具），`tools_node` 负责行动（真正执行），`should_continue` 是岔路口，`compile()` 变成一张随时能跑的路线图 —— 然后 FastAPI 用 `stream(stream_mode="updates")` 把每一步直播给用户看。
