# 《智能实验室预约系统》FastAPI 后端精讲

> 面向零基础读者・以本项目真实代码为主线・建议打开 VS Code 对照 
>
> `backend/app/`
>
>  目录同步阅读
> 本文只讲 
>
> **FastAPI**
>
>  这一条主线（接口层），不涉及 LangGraph / RAG / 前端。



***

## 阅读指南



* 本文讲解与本项目 FastAPI 直接相关的文件：

  `main.py` / `config.py` / `database.py` / `models.py` / `schemas.py` / `security.py` / `llm.py` / `routers/`（5 个文件）

* 阅读方式：先跑起来（第 2 章）→ 按章节顺序读 → 边读边在 `/docs` 页面手动调接口。

* 文中【大白话】是对概念的通俗解释；【关键点】是要记住的结论。



***

## 第 1 章 FastAPI 是什么

### 1.1 后端到底在干什么

【大白话】浏览器（前端）不能直接读写数据库、调用大模型。后端就是 "中间人"：



```
浏览器发请求 ──► FastAPI 后端 ──► 数据库 / 大模型
     ▲                              │
     └──────── 返回 JSON ────────────┘
```

FastAPI 是一个 Python 的 Web 框架，专门帮你把 "中间人服务" 写出来：接收请求、校验数据、执行业务逻辑、返回 JSON。

### 1.2 FastAPI 的三大杀手锏



| 能力   | 说明                         | 在本项目的体现                                       |
| ---- | -------------------------- | --------------------------------------------- |
| 自动校验 | 用类型注解声明参数格式，错了自动拒绝         | `schemas.py`（Pydantic）                        |
| 自动文档 | 接口写好后自动生成可调试的网页文档          | 启动后访问 `http://localhost:8001/docs`            |
| 依赖注入 | 框架自动帮你准备 "依赖"（数据库会话、当前用户等） | `Depends(get_db)`、`Depends(get_current_user)` |

### 1.3 项目 FastAPI 文件地图



| 文件                        | 一句话职责                 | 核心知识点               |
| ------------------------- | --------------------- | ------------------- |
| `app/main.py`             | 应用入口：创建 app、注册路由、统一异常 | 应用实例、中间件、路由注册       |
| `app/config.py`           | 读取 `.env` 配置          | pydantic-settings   |
| `app/database.py`         | 数据库引擎与会话              | SQLAlchemy、yield 依赖 |
| `app/models.py`           | 4 张数据库表的定义            | ORM、外键、关系           |
| `app/schemas.py`          | 请求 / 响应数据的 "形状说明书"    | Pydantic 模型         |
| `app/security.py`         | 密码哈希 + JWT 登录凭证       | 认证鉴权                |
| `app/llm.py`              | 大模型客户端工厂              | OpenAI 兼容接口         |
| `app/routers/auth.py`     | 注册 / 登录接口             | 表单参数、JWT 签发         |
| `app/routers/users.py`    | 用户信息 / 头像上传           | 文件上传                |
| `app/routers/labs.py`     | 实验室与设备 CRUD           | 增删改查标准写法            |
| `app/routers/bookings.py` | 预约提交 / 审核             | 依赖注入、事务、冲突检测        |
| `app/routers/chat.py`     | AI 对话（SSE 流式）         | StreamingResponse   |



***

## 第 2 章 环境与启动

### 2.1 `requirements.txt` —— 项目需要哪些第三方库



```
fastapi>=0.115        # 本教程主角：Web 框架
uvicorn[standard]>=0.30   # 运行 FastAPI 的服务器（就像给网站配的发动机）
sqlalchemy>=2.0       # ORM：用 Python 对象操作数据库
pydantic>=2.7         # 数据校验库（FastAPI 的校验全靠它）
pydantic-settings>=2.3    # 让配置类能自动读取 .env 文件
PyJWT>=2.8            # 签发/验证 JWT 登录令牌
python-multipart>=0.0.9   # 解析表单数据（登录、文件上传需要）
httpx>=0.27           # HTTP 客户端（本项目用它调 ChromaDB）
openai>=1.40          # 官方 OpenAI SDK（本项目用它调 MiniMax 大模型）
langgraph>=1.0        # 智能体框架（下一份文档的主角）
```

【关键点】`uvicorn` 是 "服务器"，`fastapi` 是 "框架"。框架写逻辑，服务器负责跑起来接受网络请求。两者缺一不可。

### 2.2 启动命令拆解



```
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

逐段拆解：



| 片段               | 含义                                               |
| ---------------- | ------------------------------------------------ |
| `-m uvicorn`     | 用 Python 运行 uvicorn                              |
| `app.main:app`   | **导入路径**：`app/main.py` 文件里的 `app` 变量（FastAPI 实例） |
| `--host 0.0.0.0` | 监听所有网卡（局域网内其他设备也能访问；只本机调试可写 `127.0.0.1`）         |
| `--port 8001`    | 端口号。注意：ChromaDB 占用了 8000，所以后端用 8001              |

启动成功后，浏览器打开 `http://localhost:8001/docs`，会看到 FastAPI 自动生成的接口文档 —— 这是学习本项目最快的入口，每个接口都可以点 "Try it out" 直接测试。

### 2.3 `config.py` —— 配置全部集中在这里



```
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "智能实验室预约系统"
    DEBUG: bool = True

    SECRET_KEY: str = "dev-secret"          # JWT 签名密钥（生产环境必须换成随机长字符串！）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 令牌有效期：10080 分钟 = 7 天

    DATABASE_URL: str = "sqlite:///./data/lab.db"   # SQLite 数据库文件路径

    LLM_BASE_URL: str = "https://api.minimax.cn/v1"  # 大模型接口地址
    LLM_API_KEY: str = ""                             # 密钥（写在 .env 里，不写进代码）
    LLM_MODEL: str = "MiniMax-M3"

    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"  # Embedding 服务
    SILICONFLOW_API_KEY: str = ""
    EMBED_MODEL_NAME: str = "Pro/BAAI/bge-m3"
    EMBED_DIM: int = 1024

    CHROMA_HOST: str = "localhost"    # 向量数据库地址
    CHROMA_PORT: int = 8000


settings = Settings()   # 全局唯一配置实例，其他文件都 import 它
```

【大白话】配置文件就是 "项目的设置面板"。字段写在这里，其他文件通过 `from .config import settings` 拿到，比如 `main.py` 里 `FastAPI(title=settings.APP_NAME)`。

【关键点】`env_file=".env"` 表示：`.env` 文件里的同名变量会**覆盖**类里写的默认值（API Key 这种敏感信息放 `.env`，不提交到 Git）。



***

## 第 3 章 `main.py` 入口逐行精讲

这是整个后端的 "心脏" 文件，一共 54 行。先看全貌：



```
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .database import Base, engine
from .routers import auth, users, labs, bookings, chat

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content={"code": exc.status_code, "message": exc.detail, "data": None})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    msg = exc.errors()[0].get("msg", "参数校验失败") if exc.errors() else "参数校验失败"
    return JSONResponse(status_code=422, content={"code": 422, "message": msg, "data": None})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500,
                        content={"code": 500, "message": f"服务器内部错误: {exc}", "data": None})


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(labs.router)
app.include_router(bookings.router)
app.include_router(chat.router)


@app.get("/api/health")
def health():
    return {"code": 200, "message": "ok", "data": {"status": "up"}}
```

### 3.1 第 1 行到第 12 行：导入



```
from fastapi import FastAPI, Request
```



* `FastAPI`：框架本身，后面要 `FastAPI(...)` 创建实例。

* `Request`：请求对象，异常处理器里用来接收 "这次请求" 的信息（本例没用到，但参数必须有）。



```
from fastapi.middleware.cors import CORSMiddleware      # 跨域中间件
from fastapi.responses import JSONResponse              # 返回 JSON 的响应类
from fastapi.staticfiles import StaticFiles             # 提供静态文件（图片等）
from starlette.exceptions import HTTPException as StarletteHTTPException
# 把 HTTPException 起个别名，避免和后面我们自己抛的冲突
```



```
from .config import settings        # 配置（第 2.3 节）
from .database import Base, engine  # 数据库基类 + 引擎
from .routers import auth, users, labs, bookings, chat   # 5 个路由模块
```

### 3.2 第 14 行：自动建表



```
Base.metadata.create_all(bind=engine)
```

【大白话】`models.py` 里定义的 4 个类（User/Laboratory/Equipment/Booking）就是 "表的设计图纸"。这一行在**启动时**根据图纸创建表（表已存在则跳过）。SQLite 是文件数据库，表存在 `backend/data/lab.db` 里。

【关键点】这是教学项目的简写。生产环境一般用专门的迁移工具（Alembic）管理表结构，而不是每次启动 create\_all。

### 3.3 第 16 行：创建 FastAPI 实例



```
app = FastAPI(title=settings.APP_NAME)
```



* `app` 就是整个后端应用，`uvicorn app.main:app` 启动的就是它。

* `title` 会显示在 `/docs` 文档页顶部。

### 3.4 第 18-22 行：CORS 中间件（打开跨域门禁）



```
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 允许所有来源（开发期写法）
    allow_credentials=True,    # 允许携带 Cookie 等凭证
    allow_methods=["*"],       # 允许所有 HTTP 方法
    allow_headers=["*"],       # 允许所有请求头
)
```

【大白话】前端跑在 `localhost:5173`，后端在 `localhost:8001`，**端口不同 = 跨域**。浏览器默认禁止跨域请求，CORS 中间件就是 "给门卫打招呼：这些请求放行"。第 11 章详细讲。

### 3.5 第 24 行：挂载静态文件



```
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
```

把本地 `uploads/` 目录映射成 URL 路径 `/uploads/...`。用户上传头像后，前端可以直接访问 `http://localhost:8001/uploads/xxx.png` 显示图片。

### 3.6 第 27-42 行：三个全局异常处理器（统一 "报错长相"）

**处理器 1：HTTP 业务错误**（比如 "用户名已存在" 这种主动抛出的错误）



```
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content={"code": exc.status_code, "message": exc.detail, "data": None})
```

**处理器 2：参数校验失败**（前端传错格式）



```
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    msg = exc.errors()[0].get("msg", "参数校验失败") if exc.errors() else "参数校验失败"
    return JSONResponse(status_code=422, content={"code": 422, "message": msg, "data": None})
```



* 固定返回 `422` 状态码；

* `exc.errors()[0].get("msg")`：取出**第一个**校验错误信息（比如 "Input should be a valid integer"）。

**处理器 3：兜底异常**（没被上面接住的意外错误）



```
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500,
                        content={"code": 500, "message": f"服务器内部错误: {exc}", "data": None})
```

【关键点】三个处理器保证了：**不管什么错误，返回给前端的永远长一个样**——`{"code": ..., "message": ..., "data": null}`。前端只要写一套解析逻辑就够了。

### 3.7 第 45-49 行：注册 5 个路由器



```
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(labs.router)
app.include_router(bookings.router)
app.include_router(chat.router)
```

【大白话】`routers/` 里每个文件定义了自己的接口，但必须 "装" 到 `app` 上才生效 ——`include_router` 就是安装动作。装完，接口就上线了。

### 3.8 第 52-54 行：一个最简单的接口（健康检查）



```
@app.get("/api/health")
def health():
    return {"code": 200, "message": "ok", "data": {"status": "up"}}
```

这就是 FastAPI 最基础的接口形态：



* `@app.get("/api/health")`：**装饰器**，声明 " 当收到 GET 请求 `/api/health` 时，调用下面这个函数 "；

* 函数返回的 dict 会被自动转成 JSON 返回给前端。



***

## 第 4 章 路由系统：前端怎么找到你的接口

### 4.1 什么是路由

【大白话】路由 = 地址簿。每个接口有一个 "方法 + 路径"（如 `POST /api/bookings`），FastAPI 收到请求后，照着地址簿找到对应的函数来执行。

### 4.2 APIRouter：把接口分组

`routers/auth.py` 的开头：



```
from fastapi import APIRouter, Depends, HTTPException
...
router = APIRouter(prefix="/api/auth", tags=["认证"])
```



* `prefix="/api/auth"`：这个模块所有接口的路径前缀。所以模块里写 `@router.post("/register")`，实际对外是 `POST /api/auth/register`。

* `tags=["认证"]`：在 `/docs` 文档里归到 "认证" 分组，方便查找。

* 模块内的接口用 `@router.xxx(...)` 而不是 `@app.xxx(...)`，最后由 `main.py` 统一 `include_router` 安装。

### 4.3 HTTP 方法与本项目接口总表



| 方法     | 语义           | 本项目接口举例                                        |
| ------ | ------------ | ---------------------------------------------- |
| GET    | 获取数据（不改变状态）  | `GET /api/labs`、`GET /api/bookings/mine`       |
| POST   | 创建新资源 / 提交动作 | `POST /api/auth/register`、`POST /api/bookings` |
| PUT    | 整体更新         | `PUT /api/labs/{lab_id}`                       |
| DELETE | 删除           | `DELETE /api/labs/{lab_id}`                    |

【关键点】方法表示 "动作类型"，路径表示 "对谁做"。同一个路径可以有多个方法：`GET /api/labs`（查列表）、`POST /api/labs`（新建）。

### 4.4 路径参数 与 查询参数

**路径参数**：写在 URL 路径里，用 `{名称}` 占位。来自 `routers/labs.py`：



```
@router.get("/labs/{lab_id}")
def get_lab(lab_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
```



* 访问 `GET /api/labs/3`，`lab_id` 自动等于 3；

* 声明 `lab_id: int`，前端传 `abc` 会直接 422 报错 ——**类型注解就是校验**。

**查询参数**：URL 里 `?` 后面的键值对。来自 `routers/labs.py`：



```
@router.get("/labs")
def list_labs(page: int = 1, size: int = 20, keyword: str = "",
              db: Session = Depends(get_db), _: User = Depends(get_current_user)):
```



* 访问 `GET /api/labs?page=2&size=10&keyword=网络`；

* 有默认值的参数可省略：不传就用默认值（page=1, size=20, keyword=""）。

### 4.5 一个接口的完整解剖（全书最重要的代码）

来自 `routers/bookings.py` 的提交预约接口，把 FastAPI 的核心机制浓缩在一段里：



```
@router.post("")                                        # ① 方法+路径（前缀在文件头定义）
def create_booking(payload: BookingCreate,              # ② 请求体校验
                   db: Session = Depends(get_db),       # ③ 依赖注入：数据库会话
                   current_user: User = Depends(get_current_user)):  # ④ 依赖注入：当前用户
    lab = db.query(Laboratory).filter(Laboratory.id == payload.lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="实验室不存在")   # ⑤ 业务错误
    if lab.status != "enabled":
        raise HTTPException(status_code=400, detail="实验室已停用")
    if payload.start_time >= payload.end_time:
        raise HTTPException(status_code=400, detail="开始时间必须早于结束时间")
    if payload.start_time < lab.open_time or payload.end_time > lab.close_time:
        raise HTTPException(status_code=400, detail="预约时段超出实验室开放时间")
    if _check_conflict(db, payload.lab_id, payload.booking_date,
                       payload.start_time, payload.end_time):
        raise HTTPException(status_code=400, detail="该时段已被占用，请选择其他时段")

    booking = Booking(user_id=current_user.id, status="pending", **payload.model_dump())
    db.add(booking)          # ⑥ 写入数据库
    db.commit()
    db.refresh(booking)
    return ok(BookingOut.model_validate(booking).model_dump(mode="json"), "预约已提交，等待审核")  # ⑦ 返回
```

按编号逐个拆：



| # | 代码                                               | 干什么    | 大白话                                                                |
| - | ------------------------------------------------ | ------ | ------------------------------------------------------------------ |
| ① | `@router.post("")`                               | 声明接口   | 完整路径 = 文件头的 prefix (`/api/bookings`) + `""` = `POST /api/bookings` |
| ② | `payload: BookingCreate`                         | 请求体校验  | 前端 JSON 自动按 `BookingCreate` 检查，不过关 → 422（第 5 章）                    |
| ③ | `db: Session = Depends(get_db)`                  | 依赖注入   | 框架自动开一个数据库会话传进来，用完自动关闭                                             |
| ④ | `current_user: User = Depends(get_current_user)` | 登录鉴权   | 框架自动验 JWT、查出当前用户；没登录 → 401                                         |
| ⑤ | `raise HTTPException(...)`                       | 抛业务错误  | 主动拒绝，被 main.py 全局处理器接住变统一 JSON                                     |
| ⑥ | `add / commit / refresh`                         | 事务三件套  | 加入会话 → 落盘 → 刷新拿到自增 id                                              |
| ⑦ | `ok(...)`                                        | 统一返回格式 | `{"code":200,"message":"...","data":{...}}`                        |

【关键点】**接口函数本身不关心 "数据库会话怎么来的、用户怎么验的"**—— 这些脏活全交给依赖注入。函数只写业务逻辑，这就是 FastAPI 的生产力来源。



***

## 第 5 章 请求校验：Pydantic 与 `schemas.py`

### 5.1 什么是 Pydantic

【大白话】Pydantic 是一个 "数据质检员"。你声明一个类描述数据长什么样（字段名、类型、默认值），它自动帮你：



* **检查传入数据**：类型不对、必填缺失 → 报错（FastAPI 转成 422 返回前端）；

* **转换类型**：前端传字符串 `"2026-10-05"`，自动转成 Python 的 `date` 对象；

* **序列化输出**：把 Python 对象转回 JSON 能表示的格式。

### 5.2 `schemas.py` 全部模型讲解

**统一响应格式（项目自定的 "信封"）**



```
class R(BaseModel):
    code: int = 200
    message: str = "ok"
    data: Optional[object] = None

def ok(data=None, message="ok"):
    return {"code": 200, "message": message, "data": data}

def fail(message, code=400):
    return {"code": code, "message": message, "data": None}
```



* 所有接口的返回值都套这个信封：`code`（业务码）、`message`（提示语）、`data`（真正的数据）；

* 用函数 `ok()` / `fail()` 生成信封，避免手写 dict 出错。

**用户系列**



```
class UserBase(BaseModel):          # 公共字段
    username: str
    nickname: Optional[str] = ""
    avatar: Optional[str] = ""
    email: Optional[str] = ""

class UserCreate(UserBase):         # 注册请求体 = 公共字段 + password
    password: str

class UserUpdate(BaseModel):        # 修改资料：只允许改这两个字段
    nickname: Optional[str] = None
    email: Optional[str] = None

class UserOut(UserBase):            # 返回给前端的用户信息（不含密码！）
    model_config = ConfigDict(from_attributes=True)   # 允许直接从 ORM 对象转换
    id: int
    role: str
    created_at: Optional[datetime] = None
```

【关键点】为什么要有 `UserOut`？因为数据库表里有 `password_hash`，**绝不能返回给前端**。输入用什么模型、输出用什么模型，分开定义，这是安全习惯。

**实验室系列 / 设备系列 / 预约系列**（同样的套路：Base 公共 → Create/Update 输入 → Out 输出）



```
class LaboratoryOut(LaboratoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int

class BookingCreate(BookingBase):
    lab_id: int            # 提交预约必须指定实验室

class BookingOut(BookingBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    lab_id: int
    status: str
    review_note: Optional[str] = ""
    created_at: Optional[datetime] = None
    lab: Optional[LaboratoryOut] = None    # 嵌套：预约里带出实验室信息
    user: Optional[UserOut] = None         # 嵌套：预约里带出用户信息
```

**分页包装**



```
class Paged(BaseModel):
    items: List[object]
    total: int
    page: int = 1
    size: int = 20
```

### 5.3 校验失败长什么样

用 Swagger 试试：给 `POST /api/bookings` 传 `{"lab_id": "abc"}`，你会收到：



```
{
  "code": 422,
  "message": "Input should be a valid integer, got a string",
  "data": null
}
```

流程：Pydantic 校验失败 → FastAPI 抛出 `RequestValidationError` → `main.py` 的处理器 2 接住 → 统一 422 JSON。这就是第 3.6 节的意义。

### 5.4 两个高频方法：`model_dump` 与 `model_validate`

本项目几乎每个接口都有这两句：



```
# 输出方向：Pydantic 模型 → 普通 dict → JSON
BookingOut.model_validate(booking).model_dump(mode="json")

# 输入方向：请求体模型 → dict，作为关键字参数建 ORM 对象
Booking(user_id=..., status="pending", **payload.model_dump())
```



| 方法                     | 方向        | 说明                                           |
| ---------------------- | --------- | -------------------------------------------- |
| `model_dump()`         | 模型 → dict | `mode="json"` 表示输出 JSON 兼容格式（date 变字符串）      |
| `model_validate(obj)`  | 任意对象 → 模型 | `from_attributes=True` 允许直接吃 ORM 对象（数据库查出来的） |
| `model_dump()` 配合 `**` | 请求体 → 参数  | 把校验过的字段展开传给构造函数                              |

【大白话】`model_validate` 把数据库记录 "翻译" 成安全输出格式，`model_dump` 把模型 "翻译" 成 JSON。一进一出，数据永远干净。



***

## 第 6 章 依赖注入：FastAPI 的灵魂

### 6.1 什么是依赖注入

【大白话】接口函数经常需要 "别人准备好的东西"：数据库会话、当前登录用户、管理员权限…… 如果每个函数自己手动创建，代码会重复且容易忘记关闭。**依赖注入 = 你声明 "我需要什么"，框架自动准备好送进来。**



```
def create_booking(..., db: Session = Depends(get_db), ...):
    # 你只管用 db，不操心它是怎么来的、什么时候关
```

### 6.2 `get_db`：yield 依赖（数据库会话的生命周期）

来自 `database.py`：



```
def get_db():
    db = SessionLocal()        # 1. 开一个会话
    try:
        yield db               # 2. 把会话"递"给接口函数用
    finally:
        db.close()             # 3. 接口用完，一定关闭（防泄漏）
```

用 `yield`（而不是 `return`）的依赖叫**生成器依赖**，它的好处是：



```
请求开始 → FastAPI 执行 get_db() → yield 出 db → 接口函数使用 → 函数结束 → finally 关闭 db → 响应返回
```

【关键点】数据库连接 "开、用、关" 三件事，被 `get_db` 一个函数管完，接口里永远不会出现 "忘记关连接" 的 bug。

### 6.3 `get_current_user`：JWT 鉴权依赖

来自 `security.py`：



```
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user_id = verify_token(token)              # 验签 JWT，取出用户 id
    user = db.query(User).filter(User.id == user_id).first()   # 查数据库
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user                                # 返回当前用户对象
```

注意：**依赖自己也在用别的依赖**（`oauth2_scheme` 取令牌、`get_db` 开数据库）—— 依赖可以层层嵌套，FastAPI 会自动按顺序解析。

`oauth2_scheme` 的定义：



```
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
```

【大白话】`OAuth2PasswordBearer` 告诉 FastAPI：" 令牌从请求头 `Authorization: Bearer xxx` 里取 "。前端登录后把 JWT 放在这个头里，`get_current_user` 就能拿到并验证。

### 6.4 `require_admin`：依赖套依赖（权限升级）



```
def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user
```



* `require_admin` 先调用 `get_current_user`（验登录），再检查角色（验权限）；

* 接口只要写 `_: User = Depends(require_admin)`，就同时获得 "必须登录 + 必须是管理员" 两道保障；

* 参数名用 `_` 表示 "我不需要这个值，只是用来触发检查"。

### 6.5 依赖用法速查表



| 写法                                               | 效果               |
| ------------------------------------------------ | ---------------- |
| `db: Session = Depends(get_db)`                  | 注入数据库会话          |
| `current_user: User = Depends(get_current_user)` | 要求登录，注入当前用户      |
| `_: User = Depends(require_admin)`               | 要求管理员权限          |
| `token: str = Depends(oauth2_scheme)`            | 取出原始令牌字符串        |
| `form: OAuth2PasswordRequestForm = Depends()`    | 解析登录表单（用户名 / 密码） |



***

## 第 7 章 数据库：SQLAlchemy 集成

### 7.1 三件套：engine / SessionLocal / Base（`database.py`）



```
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
```



* `engine`：数据库 "总连接"，负责真正读写 SQLite 文件；

* `check_same_thread=False`：允许 FastAPI 的多线程使用同一个连接（SQLite 默认不允许，必须关掉）。



```
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```



* SQLite 默认**不强制**外键约束，这里用事件监听在每次连接时手动打开 —— 保证 "删实验室时，关联数据不会变成孤儿"。



```
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
```



* `SessionLocal`：会话工厂（每次 `SessionLocal()` 得到一个会话，配合 `get_db` 使用）；

* `Base`：所有模型类的父类，`models.py` 里的 `class User(Base)` 都继承它。

### 7.2 `models.py`：四张表的设计图纸



```
class User(Base):
    __tablename__ = "users"                      # 表名
    id = Column(Integer, primary_key=True, autoincrement=True)   # 主键，自增
    username = Column(String(64), unique=True, nullable=False, index=True)  # 唯一、非空、建索引
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="student")   # student / admin
    nickname = Column(String(64), default="")
    avatar = Column(String(255), default="")
    email = Column(String(128), default="")
    created_at = Column(DateTime, default=datetime.now)
    bookings = relationship("Booking", back_populates="user")   # 关系：一个用户多张预约
```

字段类型速记：`Integer` 整数 / `String(长度)` 字符串 / `Text` 长文本 / `Date` 日期 / `Time` 时间 / `DateTime` 日期时间。

**外键与关系**（`Equipment` 和 `Laboratory`）：



```
class Equipment(Base):
    __tablename__ = "equipment"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lab_id = Column(Integer, ForeignKey("laboratories.id"), nullable=False)  # 外键：属于哪个实验室
    name = Column(String(128), nullable=False)
    ...
    lab = relationship("Laboratory", back_populates="equipment")   # 反向关系
```

【大白话】`ForeignKey("laboratories.id")` 表示 "这一列的值必须是某张表里存在的主键"。`relationship` 让你在 Python 里像操作对象属性一样查关联数据：



```
lab = db.query(Laboratory).filter(Laboratory.id == 1).first()
lab.equipment          # 自动查出该实验室的所有设备（列表）
lab.bookings           # 自动查出所有预约
```

**唯一约束**（`Booking`）：



```
class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("lab_id", "booking_date", "start_time", "end_time",
                         name="uq_lab_slot"),    # 数据库层面的防重
    )
```

【关键点】同一个实验室、同一天、同一开始时间、同一结束时间，数据库层面**不允许出现第二条**—— 这是和代码里的冲突检测配合的 "双保险"。

### 7.3 CRUD 标准写法（全部来自本项目真实代码）

**查询单个**（查不到返回 404）：



```
lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
if not lab:
    raise HTTPException(status_code=404, detail="实验室不存在")
```

**条件过滤 + 排序 + 分页**：



```
q = db.query(Booking).options(joinedload(Booking.lab), joinedload(Booking.user)) \
     .filter(Booking.user_id == current_user.id) \
     .order_by(Booking.id.desc())          # 倒序：最新在前
total = q.count()                          # 总条数
items = q.offset((page - 1) * size).limit(size).all()   # 跳过 (page-1)*size 条，取 size 条
```



* `joinedload`：一次性把关联的实验室 / 用户一起查出来，避免 N+1 查询问题；

* `offset/limit`：标准分页写法（第 2 页 = 跳过 20 条取 20 条）。

**模糊搜索**：



```
q = q.filter(Laboratory.name.like(f"%{keyword}%"))   # 名字里包含 keyword
```

**创建 / 更新 / 删除**：



```
# 创建：new → add → commit → refresh
lab = Laboratory(**payload.model_dump())
db.add(lab); db.commit(); db.refresh(lab)

# 更新：改属性 → commit
for k, v in payload.model_dump().items():
    setattr(lab, k, v)     # 把请求里的字段逐个赋给数据库对象
db.commit(); db.refresh(lab)

# 删除：delete → commit
db.delete(lab); db.commit()
```

### 7.4 事务三件套为什么缺一不可



| 步骤                | 作用                   | 类比     |
| ----------------- | -------------------- | ------ |
| `db.add(obj)`     | 把对象放进 "待办清单"         | 写好草稿   |
| `db.commit()`     | 真正写进数据库              | 盖章生效   |
| `db.refresh(obj)` | 从数据库重新读一遍（拿到自增 id 等） | 拿到官方回执 |

【关键点】`commit()` 之前数据库什么都没变；中间出错可以 `rollback()` 全部撤销 —— 这就是 "事务" 的原子性。



***

## 第 8 章 认证与安全：`security.py`

### 8.1 登录流程全图



```
用户输入 用户名+密码
   │
   ▼
POST /api/auth/login  →  verify_password(密码, 库里存的哈希)
   │
   ├─ 不对 → 400 "用户名或密码错误"
   │
   ▼ 对
create_access_token(user.id)  →  签发 JWT 令牌
   │
   ▼
返回 {"access_token": "eyJhbGci...", "token_type": "bearer"}
   │
   ▼（之后每次请求）
前端带 Authorization: Bearer eyJhbGci...  →  get_current_user 验签 → 查出用户
```

### 8.2 密码哈希：绝不存明文



```
def hash_password(password: str) -> str:
    salt = os.urandom(16)                    # 1. 随机生成 16 字节"盐"
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    # 2. 用 PBKDF2 算法把密码+盐搅 10 万次
    return f"pbkdf2_sha256${salt.hex()}${dk.hex()}"   # 3. 盐和结果一起存

def verify_password(password: str, password_hash: str) -> bool:
    _, salt_hex, dk_hex = password_hash.split("$")   # 取出盐
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 100_000)
    return hmac.compare_digest(dk.hex(), dk_hex)     # 常量时间比较，防时序攻击
```

【大白话】数据库里存的是 `pbkdf2_sha256$盐$结果`。即使数据库泄露，黑客也无法直接得到明文密码（还得暴力破解 10 万次哈希）。每个用户盐不同，相同的密码也产生不同哈希。

### 8.3 JWT：登录后的 "门票"



```
def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id),                       # 载荷：用户 id
                 "exp": datetime.utcnow() + expires_delta}  # 载荷：过期时间
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")   # 签名
```



```
def verify_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return int(payload["sub"])          # 验签通过 → 返回用户 id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="无效的认证凭据",
                            headers={"WWW-Authenticate": "Bearer"})
```

【大白话】JWT = 一张**防伪门票**。里面有 "你是谁"（sub）和 "什么时候过期"（exp），用密钥签名。后端验票时只要密钥对得上、没过期，就认账 ——**不需要查数据库**（这就是 JWT 比 session 快的地方）。

### 8.4 用依赖保护接口



```
# 登录才能访问
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return ok(UserOut.model_validate(current_user).model_dump(mode="json"))

# 登录 + 管理员才能访问
@router.get("")
def list_users(page: int = 1, size: int = 20, db: Session = Depends(get_db),
               _: User = Depends(require_admin)):
```

未登录 → 401；已登录但不是管理员 → 403。两道锁都由依赖完成，接口函数零侵入。



***

## 第 9 章 响应与异常：统一格式

### 9.1 三个状态码速记



| 状态码 | 含义              | 本项目出现位置                 |
| --- | --------------- | ----------------------- |
| 200 | 成功              | 所有正常返回                  |
| 400 | 业务错误（参数对但业务不允许） | "用户名已存在"、"时段已占用"        |
| 401 | 未登录 / 令牌无效      | `get_current_user` 验签失败 |
| 403 | 没权限             | 非管理员访问管理接口              |
| 404 | 资源不存在           | "实验室不存在"                |
| 422 | 参数格式校验失败        | Pydantic 拒绝坏数据          |
| 500 | 服务器内部错误         | 兜底异常处理器                 |

### 9.2 HTTPException：在业务代码里主动拒绝



```
raise HTTPException(status_code=400, detail="该时段已被占用，请选择其他时段")
```

抛出后，FastAPI 会把它转成 `StarletteHTTPException`，被 `main.py` 处理器 1 接住，变成：



```
{"code": 400, "message": "该时段已被占用，请选择其他时段", "data": null}
```

### 9.3 异常处理层级图



```
业务代码抛 HTTPException ──► 处理器1 (StarletteHTTPException) → 状态码+detail
Pydantic 校验失败        ──► 处理器2 (RequestValidationError) → 422
其他任何未处理异常        ──► 处理器3 (Exception)              → 500
```

### 9.4 正常响应 vs 错误响应（前端视角）



```
// 成功
{"code": 200, "message": "预约已提交，等待审核", "data": {"booking_id": 12, "status": "pending"}}
// 业务失败
{"code": 400, "message": "该时段已被占用，请选择其他时段", "data": null}
// 校验失败
{"code": 422, "message": "Input should be a valid integer", "data": null}
```



***

## 第 10 章 SSE 流式响应：AI 回答 "打字机"

### 10.1 为什么用 SSE

AI 大模型生成一段回答要几秒，如果等全部生成完再一次性返回，用户干等体验很差。SSE（Server-Sent Events）让后端**边生成边推送**，前端逐字显示 —— 这就是 "打字机效果"。

### 10.2 代码拆解（`routers/chat.py`）



```
def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"   # SSE 的标准数据格式
```



```
@router.post("")
def chat(payload: ChatRequest, db: Session = Depends(get_db),
         current_user: User = Depends(get_current_user)):
    ...
    def stream() -> Generator[str, None, None]:      # 生成器：一段一段产出
        yield _sse({"type": "thinking", "content": "正在思考..."})
        resp = client.chat.completions.create(model=..., messages=..., stream=True)  # 大模型流式
        for chunk in resp:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield _sse({"type": "answer", "content": delta.content})   # 逐字推送
        yield _sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream")
```

要点：



| 概念                               | 说明                                                 |
| -------------------------------- | -------------------------------------------------- |
| `Generator`                      | 用 `yield` 的函数，可以 "产出一点、暂停、再产出"                     |
| `StreamingResponse`              | FastAPI 专门用来返回流式内容的响应类                             |
| `media_type="text/event-stream"` | 告诉浏览器 "这是 SSE 流"，前端用 `fetch` 的 `ReadableStream` 读取 |

### 10.3 事件类型表（前端按 type 分别处理）



| type          | 含义       | 前端表现           |
| ------------- | -------- | -------------- |
| `thinking`    | 开始思考     | 显示 "正在思考…"     |
| `answer`      | 回答内容片段   | 追加到气泡          |
| `tool_call`   | AI 要调用工具 | 显示 "正在查询空闲时段…" |
| `tool_result` | 工具执行结果   | 显示结果摘要         |
| `done`        | 全部结束     | 停止接收           |
| `error`       | 出错       | 提示错误           |



***

## 第 11 章 中间件与 CORS

### 11.1 什么是中间件

【大白话】中间件是夹在 "请求进入" 和 "响应出去" 之间的**关卡**，每个请求都会路过它：



```
请求 → [中间件1] → [中间件2] → 路由函数 → [中间件2] → [中间件1] → 响应
```

适合做：日志记录、跨域放行、请求耗时统计等 "横切" 功能。

### 11.2 CORS 参数逐个解释



```
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 允许哪些前端域名访问（* = 所有）
    allow_credentials=True,     # 是否允许携带 Cookie / 凭证
    allow_methods=["*"],        # 允许哪些 HTTP 方法
    allow_headers=["*"],        # 允许哪些请求头
)
```

为什么需要它？前端 `localhost:5173` 请求后端 `localhost:8001`：**域名不同（**[localhost](https://localhost)**&#x20;也算不同源，因为端口不同）**。浏览器安全策略会拦截跨域响应，CORS 中间件就是在响应头里加 "白名单声明"，让浏览器放行。

【关键点】`allow_origins=["*"]` + `allow_credentials=True` 是开发期便利写法，生产环境应改成具体的域名白名单（如 `["https://your.site"]`），否则任何网站都能跨域调用你的接口。



***

## 第 12 章 一次请求的完整生命周期

以 "学生提交预约" 为例，把所有章节串起来：



```
浏览器（Vue3 前端）
  │  POST /api/bookings
  │  请求头：Authorization: Bearer <JWT>
  │  请求体：{"lab_id": 1, "booking_date": "2026-10-05", "start_time": "14:00", "end_time": "16:00", "purpose": "课程实验"}
  ▼
FastAPI 应用（main.py 创建的 app）
  │  ① CORS 中间件：检查跨域是否放行
  │  ② 路由匹配：POST + /api/bookings → bookings.py 的 create_booking
  │  ③ 依赖注入准备：
  │       get_db() → 打开数据库会话
  │       get_current_user() → 从 Authorization 头取 JWT → 验签 → 查出当前用户
  │  ④ Pydantic 校验：请求体是否符合 BookingCreate（类型、必填）
  ▼
create_booking 函数体
  │  ⑤ 业务校验：实验室存在？启用？时间顺序？在开放时间内？时段冲突？
  │     （任一不过 → raise HTTPException → 全局处理器 → 统一错误 JSON）
  │  ⑥ 写库：db.add(booking) → db.commit() → db.refresh(booking)
  ▼
return ok(...)
  │  JSON：{"code":200,"message":"预约已提交，等待审核","data":{...}}
  ▼
浏览器收到 → 前端弹提示 → 刷新"我的预约"列表
```

**一张图记住 FastAPI 全家桶**：



```
路由(router) ──► 依赖注入(Depends) ──► 业务逻辑 ──► 数据库(SQLAlchemy)
    │                                      │
  参数校验(Pydantic/schemas)         异常处理(HTTPException→全局处理器)
    │                                      │
统一响应格式(ok/fail) ◄───────────── 统一错误格式(code/message/data)
```



***

## 第 13 章 自测与进阶

### 13.1 概念自测（先自己想，再翻前面）



1. `uvicorn app.main:app` 里的 `app.main` 和 `:app` 分别指什么？

2. `include_router` 的作用是什么？

3. 路径参数和查询参数的区别？

4. 为什么要有 `schemas.py`？`UserOut` 和 `UserCreate` 为什么要分开？

5. `Depends(get_db)` 解决了什么问题？`yield` 依赖的 `finally` 是干什么的？

6. `get_current_user` 和 `require_admin` 的区别？

7. `db.add / commit / refresh` 三步各是什么作用？

8. HTTPException 抛出去后，谁把它变成统一 JSON？

9. 422 和 400 分别代表什么？什么时候会触发？

10. JWT 里存了什么？为什么验签不用查数据库？

11. `model_dump` 和 `model_validate` 的方向分别是什么？

12. SSE 和普通返回有什么区别？`StreamingResponse` 是干什么的？

13. `check_same_thread=False` 为什么必须设置？

14. `UniqueConstraint` 在数据库层面防什么？

15. `allow_origins=["*"]` 为什么不适合生产环境？

### 13.2 动手练习（改代码验证理解）



1. 在 `routers/labs.py` 给 `list_labs` 加一个 `status` 查询参数（默认 `""`），实现按状态筛选。

2. 在 `schemas.py` 给 `LaboratoryOut` 加一个字段 `equipment_count`（提示：需要手动构造 dict，不能直接 `model_validate`）。

3. 在 `security.py` 把 `ACCESS_TOKEN_EXPIRE_MINUTES` 改成 1，登录后等一分钟再访问 `/api/users/me`，观察 401。

4. 把 `main.py` 的 `allow_origins` 改成 `["http://localhost:9999"]`，再用前端页面请求，观察 CORS 报错。

### 13.3 阅读顺序建议（配合本文）



1. `config.py` → `database.py`（地基）

2. `models.py` → `schemas.py`（表和数据的形状）

3. `security.py`（认证）

4. `routers/bookings.py`（最典型的 CRUD + 依赖注入）

5. `routers/auth.py`（登录流程）

6. `main.py`（最后看入口，此时会豁然开朗）

7. `routers/chat.py`（SSE 流式，进阶）



***

## 附录：本项目全部接口速查



| 方法     | 路径                             | 权限  | 说明                          |
| ------ | ------------------------------ | --- | --------------------------- |
| POST   | `/api/auth/register`           | 公开  | 注册                          |
| POST   | `/api/auth/login`              | 公开  | 登录（表单），返回 JWT               |
| GET    | `/api/users/me`                | 登录  | 我的信息                        |
| PUT    | `/api/users/me`                | 登录  | 修改昵称 / 邮箱                   |
| POST   | `/api/users/me/avatar`         | 登录  | 上传头像                        |
| GET    | `/api/users`                   | 管理员 | 用户列表                        |
| GET    | `/api/labs`                    | 登录  | 实验室列表（支持 keyword/page/size） |
| GET    | `/api/labs/{lab_id}`           | 登录  | 实验室详情（含设备）                  |
| POST   | `/api/labs`                    | 管理员 | 新建实验室                       |
| PUT    | `/api/labs/{lab_id}`           | 管理员 | 更新实验室                       |
| DELETE | `/api/labs/{lab_id}`           | 管理员 | 删除实验室                       |
| GET    | `/api/labs/{lab_id}/equipment` | 登录  | 设备列表                        |
| POST   | `/api/labs/{lab_id}/equipment` | 管理员 | 添加设备                        |
| PUT    | `/api/equipment/{equip_id}`    | 管理员 | 更新设备                        |
| DELETE | `/api/equipment/{equip_id}`    | 管理员 | 删除设备                        |
| POST   | `/api/bookings`                | 登录  | 提交预约（自动冲突检测）                |
| GET    | `/api/bookings/mine`           | 登录  | 我的预约                        |
| POST   | `/api/bookings/{id}/cancel`    | 本人  | 取消预约                        |
| GET    | `/api/bookings`                | 管理员 | 全部预约                        |
| POST   | `/api/bookings/{id}/approve`   | 管理员 | 审核通过                        |
| POST   | `/api/bookings/{id}/reject`    | 管理员 | 审核驳回                        |
| POST   | `/api/chat`                    | 登录  | AI 普通对话（SSE + RAG）          |
| POST   | `/api/chat/agent`              | 登录  | 智能预约 Agent（SSE + LangGraph） |
| GET    | `/api/chat/history`            | 登录  | 会话历史                        |
| GET    | `/api/health`                  | 公开  | 健康检查                        |