# 数据库迁移

[中文](database-migrations.md) | [English](database-migrations_EN.md)

StockPulse 使用仓库内的 Python Migration Runner 管理 SQLite Schema 演进。第一阶段不引入 Alembic，也不一次性替换已有的 `Base.metadata.create_all()` 和 startup `_ensure_*` 兼容逻辑，而是逐项把 startup DDL 转成正式 migration。

当前生产 registry 的目标版本是 `202607190005_intelligence_item_unique_index`。`202607160001_migration_runner_registry` 建立有序 registry 所需的 additive metadata；`202607190001`~`202607190005` 依次把原先由 startup `_ensure_*` 兼容步骤补写的 `llm_usage` 遥测列，`decision_signals` 的 `decision_profile` 列/索引/回填，`portfolio_idempotency_records` 的 scope 列/唯一索引/规范化/guard trigger，`intelligence_items` 的 legacy scope 值规范化，以及 `intelligence_items` 从 legacy url 唯一到 scoped 复合唯一键的重建改为正式 migration，对缺失的旧库幂等补齐，对 fresh 库为 no-op。至此启动路径不再执行业务 schema DDL 兼容步骤。

数据模型版本化在本仓库分两个正交层次：**DB schema 层**由下文的有序 migration runner 管理（表/列/索引形状演进）；**序列化领域 artifact 层**由内嵌的版本标签管理（持久化或跨模块传递的 payload 内部契约），见文末「序列化 artifact 版本化」。

## 核心契约

每个 migration 都由以下稳定属性定义：

| 属性 | 契约 |
| --- | --- |
| `id` | 全局唯一、严格递增且发布后不变 |
| `description` | 稳定的英文诊断描述 |
| `checksum` | 对完整、规范化 migration 模块源码计算的确定性 SHA-256 |
| `upgrade` | 接收受限 `MigrationExecution` SQL 执行能力、同步执行并返回 `None` 的升级 callable |

`src.migrations.registry` 是执行顺序的唯一事实来源。Runner 不依赖文件系统遍历顺序，也不根据文件名推测 upgrade 函数。重复 import 必须产生相同的 ID、顺序和 checksum。

生产 migration 通过 `Migration.from_source_file()` 将实际 `upgrade`、辅助函数和模块常量所在的完整源码绑定到 checksum；源码只把 CRLF/CR 物理换行统一为 LF，其他字符（包括字符串中的语义空格和文件末尾换行）都保留，绝对路径不进入哈希。已发布的 migration 不可修改、重排或删除。Schema 或数据行为需要调整时，必须新增一个 ID 更高的 migration。修改已 applied migration 会导致 checksum 校验失败，应用会 fail closed。

Production migration 是经过审查并随仓库发布的受信代码，不是用户脚本、插件或远程载荷。Runner 只向 `upgrade` 提供 `execute` 和 `exec_driver_sql`，不提供完整 SQLAlchemy `Connection`、engine、raw cursor、底层 DBAPI handle、`executescript` 或任何事务控制方法。`execute` 只接受精确的 `sqlalchemy.text()` `TextClause`，并由 runner 一次性读取其中的普通 SQL 字符串后通过自己的 driver path 执行；任意 SQLAlchemy executable、`str` 子类或挂在 `TextClause` 实例上的执行回调都不会接触真实 `Connection`。该 capability 只在同步 `upgrade` 调用期间有效；返回或抛错时先拒绝新的调用，再等待已进入 driver path 的语句完成，然后撤销底层连接租约。即使调用方传入仍保持打开的 `Connection`，migration 保留的 facade 也不能在 runner transaction 之外继续执行。查询结果会在租约内先物化为脱离 cursor 的 tuple/dict，再返回给 migration。语句执行/物化失败和禁用能力访问都会在租约中不可逆记录；migration 即使自行捕获对应异常，runner 仍拒绝 applied row 并回滚。已发布 version 模块可能保留历史 `Connection` 类型注解以保持源码 checksum 不变，但运行时对象仍是受限 capability。Migration 注册会递归检查 `inspect.unwrap` wrapper、`functools.partial` 目标和 callable object，拒绝 coroutine、generator、async-generator function 以及循环 wrapper；因此 `contextmanager`/`asynccontextmanager` 也不能隐藏 lazy upgrade。Source-bound AST guard、事务控制 SQL 预检、随机 savepoint 和 transaction 状态检查继续作为纵深防御；runner 不覆盖调用方已安装的 SQLite authorizer。这些边界用于隔离受信代码中的常见误用和回归，不是 Python 安全沙箱，也不能把不受信代码变成可安全执行的 migration。新增 migration 仍必须经过源码审查和完整测试，禁止从配置、数据库或网络动态加载 upgrade 代码。

## Applied registry

`schema_migrations` 保留历史 `version`、`description` 和 `applied_at` 语义，并以 additive 方式持久化 checksum。

- 已知 legacy baseline 可写入确定性 checksum 或 legacy marker。
- 未知历史记录不会被自动改写或盖章为已验证状态。
- registry 的 `version` 必须是唯一主键，`version`、`description`、`applied_at` 必须保持 `NOT NULL`；畸形 registry 或重复 applied ID 会 fail closed，不会被折叠读取。
- applied row 只在对应 migration 的 Schema/DML 完整成功后插入。
- applied row 不更新、不删除、不覆盖；唯一例外是 registry metadata bootstrap 在确认 legacy baseline ID、description 和原 checksum 均匹配后，一次性把该 baseline 的 `NULL` checksum 补为确定值。
- 数据库含当前 registry 不认识的更高版本时，旧应用停止启动，避免写入新 Schema。

## DatabaseManager 初始化顺序

`DatabaseManager` 仍是业务运行时唯一的 engine、Session 和数据库配置入口。API、Bot、Desktop、Docker 和 Actions 在首次进入 `DatabaseManager` 时共用同一 migration package 和以下初始化顺序：

```text
create engine / install SQLite PRAGMAs / create Session factory
  -> BEGIN IMMEDIATE and preflight any existing registry
  -> Base.metadata.create_all()
  -> remaining _ensure_* compatibility and repair steps
  -> stamp a fresh/known legacy baseline
  -> apply pending migrations in registry order within the same transaction
  -> prove the fresh/known legacy baseline (schema shape and foreign keys)
  -> commit the serialized initialization transaction
  -> mark DatabaseManager initialized
```

Migration 在 `DatabaseManager` 初始化调用内同步完成，不会在后台继续升级。SQLite 的 `create_all + baseline stamp + pending migrations + baseline 证明` 全部在同一个数据库级写锁和事务内串行化，避免两个 fresh 进程竞争建表，并让整笔初始化对 registry、Schema 与 baseline 证明保持原子性。startup 在这把写锁内直接应用有序 migration，因此 baseline 证明看到的是补齐后的完整 Schema。startup 不再执行任何业务 schema DDL 兼容步骤：初始化期间的全部 `CREATE`/`ALTER`/`DROP` 只发生在 `metadata.create_all`（fresh baseline）或已登记 migration 的 `upgrade` callable 实际执行期间，回归测试会捕获这些 DDL，并拒绝 create_all 与已登记 callable 之外的游离 schema DDL（包括 runner 外层编排、savepoint、bootstrap 检查与 applied-row 写入阶段重新引入的启动期 ensure）。首次需要 `DatabaseManager` 的后端路径只有在迁移完成后才会返回。初始化任一步失败时，`DatabaseManager` 保持未初始化；create_all、applied row 与该事务内的所有 DDL/DML 一起回滚，不留半迁移状态。

通用 `/api/health` 当前不是数据库 readiness probe，因此 health 响应不承诺已 eager 初始化数据库。该 lazy 边界不会产生后台 migration：实际首次进入 `DatabaseManager` 的调用仍会等待 runner 完整成功或失败。

## 事务、锁与并发

- SQLite 初始化用一个 `BEGIN IMMEDIATE` 串行化 `create_all + _ensure_* + baseline stamp + pending migrations + baseline 证明`，复用应用现有 busy timeout 契约；startup 在这把写锁内直接应用有序 migration，不再为每个 migration 单独取锁。
- startup 路径下所有 pending migration 的 DDL/DML 与 applied row 位于初始化事务内，随该事务一次提交或整体回滚。`apply_pending`（engine 入口，供独立诊断与工具复用）仍为每个 migration 单独取得数据库级写锁并单独提交；两条路径复用同一守卫、savepoint 与 applied row 写入逻辑。
- `upgrade` 必须同步执行并返回 `None`。已知 lazy function 和循环 wrapper 在注册期被拒绝；任何运行时非 `None` 返回值都会以 `migration_upgrade_invalid_return` fail closed。Runner 会先关闭可同步关闭的原生 coroutine/generator，再回滚当前事务，因此 upgrade 在返回非法值前执行的 DDL/DML 和 applied row 都不会提交。
- Runner 独占事务控制。`upgrade` 只接收受限 SQL capability，无法从其公开接口取得完整 `Connection`、engine、raw cursor、底层 DBAPI handle、`executescript`、`begin`、`commit`、`rollback`、savepoint、`close` 或 `execution_options`。`execute` 拒绝自定义 executable，并把精确 `TextClause` 的单次 SQL 快照走 runner-owned driver path，避免 SQLAlchemy statement callback 或并发 mutation 获得底层连接或替换已验证语句。返回或抛错时，runner 先发布 revoked 状态，拒绝所有新调用和已经排队但尚未取得连接的调用；已在途语句必须在同一 transaction 内完成和物化后，runner 才写 applied row。任何在途语句失败都会锁存为 migration failure；禁用属性、任意 executable、非内建 SQL 字符串和 helper 间接事务控制请求也会锁存为 capability violation，因此 migration 捕获异常后继续返回 `None` 仍不能提交。此前通过 capability 执行的 DDL/DML 会与 applied row 一起回滚；在调用期之外复用保留的 facade 不会产生额外数据库改动。显式 SQL 中注释、空语句或 BOM 之后的 `BEGIN`、`COMMIT`、`END`、`ROLLBACK`、`SAVEPOINT` 和 `RELEASE` 会在进入真实 Connection 前被拒绝；随机 savepoint 和 transaction 状态检查继续验证 runner ownership，调用方已有的 SQLite authorizer 保持不变。
- 第一个 migration 失败后，后续 migration 不执行。
- 两个进程同时启动时，第二个进程等待写锁，然后重新读取 applied registry。同一 upgrade 不会执行两次。
- busy timeout 会返回稳定迁移错误，不会靠进程内 `threading.Lock` 掩盖跨进程竞争。

错误只包含稳定分类和失败 migration ID，不记录完整 `db_url`、绝对路径、SQL 参数或敏感数据。

## Fresh DB 和历史 DB

### Fresh DB

Fresh DB 仅在初始化锁内、`create_all()` 前检查不到用户表时被识别为 fresh，并继续由 SQLAlchemy metadata 创建当前表结构。Runner 随后 bootstrap applied registry 并记录基线。即使 `create_all()` 已经创建了目标列，对应 migration 仍必须按契约运行并获得 applied 记录。再次启动只校验 registry，不重复执行 upgrade。

### 历史 DB

历史数据库先在初始化锁内验证已有 registry，再运行现有 `_ensure_*` 兼容步骤，然后在同一事务内应用有序 runner，最后证明 baseline。当前明确支持以下真实发布边界：

- `v3.0.0`、`v3.4.0`、`v3.20.0`：没有 registry 时，必须匹配对应固定 release profile。
- `v3.21.0`、`v3.26.3`：必须携带已知 legacy baseline row；checksum 列可尚未存在。

Pre-baseline profile 固定记录来源 tag/commit，并完整校验该版本的必需表、列顺序、SQLite type affinity、主键、`NOT NULL`、默认值、唯一键及 collation、外键和 `WITHOUT ROWID` / `STRICT` option；partial/expression unique index、显式 `ON CONFLICT` 策略和已知后续版本表也进入 fail-closed 边界。匹配按新到旧顺序执行，残缺的较新库不能降级命中较旧 profile。兼容修复后还必须精确证明当前 ORM baseline 并通过 `PRAGMA foreign_key_check`，之后才可写 baseline row。普通同名残缺表、缺约束表、错误 affinity、部分 profile 或只有无关表的 SQLite 文件会 fail closed，整笔兼容事务回滚。自定义额外表不会作为 profile 证据，也不能替代任何必需表。无法识别的旧库不会被当作 Fresh DB 或自动 stamp；请先停止写入并完整备份，再由维护者确认来源版本和显式迁移路径。

升级不删除现有业务表、字段或数据。`llm_usage`、`decision_signals`、`portfolio_idempotency_records` 与 `intelligence_items` 的全部 startup 兼容步骤已分别转为 `202607190001`~`202607190005` 正式 migration；startup 路径不再执行业务 schema DDL 兼容步骤，只保留 `create_all`（fresh baseline 建表）与 baseline 记录登记，其余 schema 演进都必须通过新增的独立 migration 完成。

## 状态与校验 CLI

CLI 直接包装同一 runner，不复制版本判断：

```bash
python -m src.migrations.cli status
python -m src.migrations.cli verify
```

Runner 的 `status` 结果可表示 current/target version、applied、pending、unknown 和 checksum mismatch 等结构化状态；`verify` 使用相同 registry 检查顺序、未知版本和 checksum 漂移。

两个命令都使用 `get_config().get_db_url()` 的同一配置来源和与 startup 共用的最小 engine builder，但不会创建或注册业务 `DatabaseManager` singleton。SQLite 连接使用 URI `mode=ro`，并对每个连接强制 `PRAGMA query_only=ON`。命令不会调用 `create_all`、`_ensure_*` 或 `apply_pending`，也不会修改 Schema、业务数据、registry、journal mode 或 `user_version`。

| 状态 | `status` | `verify` |
| --- | --- | --- |
| 已完成 | exit 0，输出当前状态 | exit 0 |
| 存在 pending migration | exit 0，原样输出 pending | 非 0，`pending_migrations` |
| unknown / checksum mismatch / 畸形 registry | 非 0，稳定结构化错误 | 非 0，稳定结构化错误 |
| 数据库不存在 | 非 0，`database_not_found`，不创建文件或父目录 | 同左 |
| 非 SQLite backend | 非 0，`unsupported_backend`，不打开业务连接 | 同左 |

CLI 只负责诊断；应用首次进入 `DatabaseManager` 时仍会同步 apply pending migration。输出不包含完整数据库路径、URL、SQL、参数或原始异常。

开发或 CI smoke 必须显式指向隔离的临时数据库：

```bash
tmp_dir="$(mktemp -d)"
DATABASE_PATH="$tmp_dir/stockpulse-migration-smoke.sqlite" python -c \
  'from src.storage import DatabaseManager; DatabaseManager.get_instance(); DatabaseManager.reset_instance()'
DATABASE_PATH="$tmp_dir/stockpulse-migration-smoke.sqlite" python -m src.migrations.cli status
DATABASE_PATH="$tmp_dir/stockpulse-migration-smoke.sqlite" python -m src.migrations.cli verify
```

第一条命令只初始化该临时数据库；后两条诊断必须保持文件不变。不要用 smoke 命令访问默认数据库、Desktop 用户数据库或真实部署 volume。Runner 不提供 downgrade 命令。

## 失败与向前恢复

正常恢复方式是修复后向前重试，不是删除 registry 记录或执行破坏性 down migration：

1. 停止所有使用该 SQLite 数据库的进程。
2. 保留完整错误分类和失败 migration ID，不粘贴敏感路径或 SQL 参数。
3. 备份数据库，然后修复锁竞争、磁盘、权限或数据前置条件。
4. 使用包含同一已发布 registry 的修复版本重新启动。未成功的 migration 没有 applied row，因此会重新执行。
5. 运行 `status` 和 `verify`，确认 current version 等于 target version 且无 mismatch/unknown ID。

通过受支持 execution capability 发生的失败会完整回滚，可以在修复前置条件或 migration 后向前重试。不要手工补 applied row。Python 进程内无法为恶意代码提供安全沙箱；若受信 migration 刻意使用反射、重新打开数据库或执行其他 capability 之外的写入，属于不受支持的代码违规，应停止写入、与升级前备份比对，并恢复备份或发布能显式证明和修复状态的向前 migration。

出现 checksum mismatch 时，不要编辑 migration 或手工改表记录。恢复匹配的应用与数据库组合，或使用包含新的显式 migration 的版本。出现未知更高 migration ID 时，应使用认识该版本的更新应用，不能强制旧应用启动。

## 备份、回滚与灾难恢复

Migration Runner 不替代备份系统，也不自动制作部署备份。

- 升级前停止所有写入者，优先使用 SQLite Online Backup API 或已验证的 volume snapshot。
- 只有在应用完全退出后才能做文件级备份，并保持主数据库、`-wal` 和 `-shm` 文件的一致性。不要在运行中只复制主 `.db` 文件。
- Docker 升级前备份或快照 `./data/` volume；Desktop 升级前完全退出应用，Windows 打包版备份 exe 同级的 `data/`，macOS 打包版备份 Electron `userData` 下的 `data/`。
- 备份恢复用于数据库损坏、capability 之外的代码违规或其他灾难场景。受支持 execution capability 内的普通 migration 失败使用事务回滚和向前重试。
- 代码回滚后，旧应用可能因数据库包含未知更高 migration 而 fail closed。必须恢复匹配的代码与备份，不能删除 applied row 来伪造降级。

恢复后应在隔离环境先运行 SQLite integrity check 和 migration `verify`，再重新开放服务。

## Desktop、Docker 和 GitHub Actions

### Desktop

Windows 和 macOS PyInstaller 构建显式包含 `src.migrations`、`src.migrations.registry`、`src.migrations.versions` 及用于 source-bound checksum 的 version `.py` 源码，并对冻结后端执行 `src.migrations.registry` import probe。Electron 仍只负责启动和监控 Python 后端，不复制或在后台调度 runner。

Fresh Desktop DB 和从旧版保留的 DB 使用同一顺序。冻结后端首次进入 `DatabaseManager` 的路径在迁移成功后才返回；迁移失败时，该数据库依赖路径失败并使用 Desktop 现有日志路径。这不代表通用 health 端点会 eager 初始化数据库。

### Docker 与 Actions

Docker image 使用与源码、CLI 和 Desktop 相同的 importable migration package。新 image 中首次初始化 `DatabaseManager` 时，旧 volume 会在该调用返回前同步升级。多个容器指向同一 SQLite 文件时，数据库写锁使 migration 串行化，但升级前仍应尽量只保留一个写入者。

CI Docker smoke 除了导入 `src.migrations.registry`、调用 `get_migrations()` 并断言最后一项等于 `TARGET_VERSION`，还会把受支持的 legacy SQLite fixture 作为 `/app/data` volume 挂载到镜像。检查通过镜像默认 entrypoint 以降权后的 `dsa`（UID 1000）初始化真实 `DatabaseManager`，验证业务 canary、applied checksum 和 target version，再以同一 volume 启动第二个容器验证幂等。这样同时覆盖容器用户权限、volume 路径、startup migration、migration 资源发现和重启恢复，不依赖开发机绝对路径，也不会访问默认或用户真实数据库。

## 新增 migration

1. 在 `src/migrations/versions/` 新增一个比当前 target 更高的稳定 ID。
2. 使用稳定英文 description，且 upgrade 不根据业务配置改变 Schema 形状。
3. `upgrade` 使用同步、非 generator callable，接收 `MigrationExecution` 并显式或隐式返回 `None`；`execute` 仅传入 `sqlalchemy.text()` 直接创建的 `TextClause`，或使用 `exec_driver_sql`，再通过安全结果读取执行当前 migration 的参数化 DDL/DML；不要传入自定义 executable，也不要尝试取得完整 Connection、raw handle、cursor 或事务控制，并确保 source-bound 源码 guard 通过。不要把 capability 或 guard 当作运行不受信 migration 的沙箱。
4. 在显式 registry 中按严格递增顺序注册，不使用目录自动发现。
5. 增加 fresh、historical、repeat、failure/recovery、checksum 和 concurrency 测试。
6. 通过 Desktop package probe、Docker legacy-volume startup/restart smoke 和完整 backend gate 后才发布。

发布后不得编辑原 migration。所有修正都使用新 ID 向前演进。

## 序列化 artifact 版本化

上文的有序 migration registry 负责 **DB schema 层**演进。除此之外，仓库对一部分**序列化领域 artifact**（持久化或跨模块传递的 Pydantic / dataclass payload）内嵌显式版本标签，使历史 payload 在模型演进后仍可被正确解释。这一层与 DB migration 正交：DB migration 管的是表/列/索引形状，序列化版本管的是 payload 内部契约。

### 当前版本标签清单

| Artifact | 版本常量 | 当前值 | 字段 | 落点 |
| --- | --- | --- | --- | --- |
| `AnalysisContextPack` | `PACK_VERSION` | `1.0` | `pack_version`（`Literal["1.0"]`） | `analysis_history.context_snapshot`、Prompt summary、overview |
| `MarketThemeContext` | `MARKET_THEME_SCHEMA_VERSION` | `market-theme-v1` | `schema_version` | market structure 快照 |
| `StockMarketPosition` | `STOCK_MARKET_POSITION_SCHEMA_VERSION` | `stock-market-position-v1` | `schema_version` | market structure 快照 |
| `MarketStructureContext` | `MARKET_STRUCTURE_SCHEMA_VERSION` | `market-structure-v1` | `schema_version` | market structure 快照、Prompt section |
| Canonical decision scale | `CANONICAL_DECISION_SCALE_VERSION` | `decision-scale-v1` | `scale_version`（`score_band_metadata`） | DecisionSignal / 报告评分口径 |
| Runtime event | `RUNTIME_EVENT_SCHEMA_VERSION` | `1` | `schema_version` | Agent runtime 事件 |
| Provider usage | `PROVIDER_USAGE_SCHEMA_VERSION`（+ `PROVIDER_USAGE_SCHEMA_NAME`） | `2026-06-10`（`provider_usage_v1`） | `provider_usage_schema_version` | `llm_usage.provider_usage_schema_version` 列 |

清单与实际常量由守护测试 `tests/schemas/test_data_model_versioning_guard.py` 绑定，任何常量漂移或序列化时丢弃版本字段都会被捕获。

### 向后 / 向前兼容规则

- **版本内加字段**：新增可选字段并带安全默认值，不升级版本常量。旧 payload 缺该字段时消费方用默认值补齐，历史读取不受影响。
- **破坏性变更才升级版本**：重命名 / 删除 / 改语义 / 改类型属破坏性变更，必须把版本常量升到新值（如 `market-structure-v2`），并保留对旧值的读取处理。已发布的版本值不复用、不回收。
- **生产者始终写入当前版本标签**：序列化必须带上版本字段，禁止在 dump 时丢弃它（守护测试对此回归覆盖）。
- **消费者遇到不认识的版本必须优雅降级**：跳过该区块 / 返回空 / 回落默认值，绝不因历史 payload 版本不符而硬失败。既有实现：`src/market_structure_prompt.py` 与 `src/utils/data_processing.py` 在 `schema_version` 不匹配时跳过；`AnalysisContextPack.pack_version` 用 `Literal` 拒绝未知值。
- **不原地改写历史 payload**：历史记录按其内嵌版本解释，不做批量“升级”改写。若持久化落点（列 / 表）本身要变形，走上文 DB migration；payload 内版本与 DB migration 各司其职。

### 升级某个序列化版本的流程

1. 把对应版本常量升到新值，保留旧值的读取 / 降级分支。
2. 更新本清单表与守护测试 `tests/schemas/test_data_model_versioning_guard.py`。
3. 若该 artifact 的持久化列 / 表形状同时变化，另配一个更高 ID 的 DB migration（见上文「新增 migration」）。
4. 走常规源码审查与完整 backend gate。

### 尚未版本化的 artifact（后续）

`Report`（`src/schemas/report_schema.py`）、`RunFlowSnapshot`（`src/schemas/run_flow.py`）、`DecisionSignalPresentation`（`src/schemas/decision_signal_presentation.py`）目前未内嵌显式版本字段。它们在下次改变持久化形状时，按上文“版本内加字段 / 破坏性才升级”的加字段模式补齐即可，成本很低——这正是本策略要保证的“低迁移成本演进”。
