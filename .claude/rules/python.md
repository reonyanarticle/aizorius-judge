# Python モダン開発 Rules（AIzorius Judge）

AIzorius Judge の Python 実装の細則。**人間と Claude の両方**が従う。プロジェクト固有の方針（LLM非搭載・ツール設計・Scryfall・評価）は [[coding]] が正本で、本書は**言語・ツール・設計の細則**を担う（重複させない）。

> 出典：Astral公式（docs.astral.sh）、Real Python、PEP 484/526、Effective Python（Brett Slatkin・第3版/Python 3.13対応）。📘 印は Effective Python 由来の Pythonic な設計原則。

## 0. このプロジェクトの確定事項（参考文献より優先）
- **整形＝Black／lint＝Ruff**（決定）。Ruff は lint 専用（import順の整列＝isort相当を含む）、整形は Black。isort を別途導入しない。
- **型チェッカ＝basedpyright（pyright系）**（決定）。mypy・`ty`（プレビュー）は不採用。
- **型定義は `models.py` に集約**（決定）。Pydantic モデル・`dataclass`・`Enum`・`TypedDict` 等は原則 `src/aizorius_judge/models.py` に置く。規模が増えたら層ごとの `models.py` に分割可。
- **グローバル状態・設定は `settings.py` に集約**（決定）。`pydantic-settings` の `BaseSettings` 1クラスに env／`.env`／デフォルト（`EMBEDDING_MODEL` / `EMBEDDING_DEVICE` / `DATA_DIR` / `RERANKER_*`）を型付きで統合。モジュール横断のグローバル変数を各所に散らさない。ランタイム依存（HybridSearcher・httpxクライアント・ChromaDBコレクション等）は settings ではなく**注入**で渡す。
  - **settings とモジュール定数の線引き**：環境・マシンによって変えたくなる値（デバイス・モデル名・メモリ依存の max_length/batch 等）は settings（env上書き可）。**計測で確定したアルゴリズム定数**（`CANDIDATE_POOL`・RRFの重み等。環境で変えると計測済み品質が無効になる）と固定識別子（コレクション名・User-Agent）は PEP8 のモジュール定数のまま置き、実測の根拠をコメントで残す。**可変のグローバル変数（`global` 文）は禁止**。
- **パッケージ構成＝`src/aizorius_judge/`（src layout）**（決定）。`src/servers/` のような「src直下の汎用サブディレクトリ」構成は採らない。理由：
  - PyPA の定義する「src layout」は `src/<パッケージ名>/`（プロジェクト名のパッケージを src 内に置く）であり、src直下に裸のモジュール/汎用ディレクトリを置く形ではない。uv も CLI を持つアプリには `uv init --package`（= `src/<pkg>/` ＋ `[project.scripts]`）を推奨。
  - **MCP公式リファレンスサーバー**（例：mcp-server-git）も `src/mcp_server_git/` ＋ `[project.scripts]` で、`uvx mcp-server-git` / `python -m mcp_server_git` で起動する。Claude Desktop への配布・登録がこの形を前提とする。
  - `import servers` / `import search` のような汎用トップレベル名は PyPI パッケージと衝突しうる。`aizorius_judge.` 名前空間で衝突を避ける。
  - フラットsrc（src直下に裸のモジュールを置き `pythonpath` で参照するPoC向けの形）は、配布するMCPサーバーには適用しない。
  - テストは最上位 `tests/`。ツール群のような内部の層分けはパッケージ内サブパッケージ（`aizorius_judge/tools/`）で行う。

## 1. ツールチェーン
- **パッケージ・環境管理は `uv` を単一の真実の源**。pip / virtualenv / pyenv / poetry を混在させない。
  - 依存追加 `uv add <pkg>`、開発依存 `uv add --dev <pkg>`、実行 `uv run <cmd>`（手動 activate 不要）。
  - Python は `uv python pin` ＋ `.python-version` でプロジェクト固定（**3.12**）。`uv.lock` はコミットし手動編集しない。
- **lint＝Ruff**：`uv run ruff check .` / 自動修正 `uv run ruff check --fix`。※日本語コメント/docstringの全角文字を誤検知する `RUF001`〜`RUF003` は `pyproject.toml` で無効化。
- **整形＝Black**：`uv run black .`（チェックは `--check`）。
- **型＝basedpyright**：`uv run basedpyright`。設定は `pyproject.toml` の `[tool.basedpyright]`。新規のため**標準〜厳格**で開始し、段階的に強める。
- **テスト＝pytest**（補助：`pytest-cov`／`pytest-asyncio`（Scryfall呼び出しのテストに使用）／必要なら `hypothesis`）。
- **pre-commit でコミット前に Ruff・Black・型チェックを走らせる**（CI往復を防ぐ）。

## 2. プロジェクト構成
- **設定は `pyproject.toml` に集約**（setup.py/setup.cfg/.flake8/mypy.ini を新設しない）：`[project]` / `[tool.uv]` / `[tool.ruff]`・`[tool.ruff.lint]` / `[tool.black]` / `[tool.basedpyright]` / `[tool.pytest.ini_options]`。
- ディレクトリ構造の正本は [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) §8。
- 依存に **anthropic / openai を入れない**（評価用 openai は `[project.optional-dependencies]` の `eval` のみ → [[coding]]）。

## 3. 型ヒント（必須）
- 公開API・重要ロジックには**必ず型ヒント**。型はドキュメントでなく補完・静的解析・実行時検証の基盤。
- **モダン記法**：`X | None`（`Optional` 不可）、`list[int]`/`dict[str,int]`（`typing.List` 等不可）、ユニオンは `int | str`。必要に応じ `from __future__ import annotations`。
- **構造的部分型は `Protocol`**（継承を強制しない）。継承を強制したいときのみ ABC。
- **`Any` は最小限**。動的データ（Scryfall JSON・CR JSON等）は早期に具体型へナローイング。
- **構造化データ**：TypedDict → dataclass → Pydantic を用途で使い分け、実行時バリデーションが要るなら Pydantic。いずれも**定義は `models.py`**。
- 📘 辞書ネストやタプル多用で複雑化したら、その場しのぎをやめ **`dataclass` 等にリファクタ**して意図と型を明示。

## 4. アーキテクチャ・設計
- **コアを純粋に保つ（Ports & Adapters）**。中核ロジック（RRF融合・スコア計算・差分検出）は**純粋関数＋データクラス**に閉じ、フレームワークやI/Oを知らないこと。副作用（HTTP・ChromaDB・ファイル）は外側のシェル層へ。
  - 本プロジェクトでは検索の融合ロジック（RRF）と差分計算を決定論的に純粋関数化し、ChromaDB/Scryfall への I/O と分離する。
- **小さな自動化でも「ソフトウェア」として構造化**（実データ操作・外部API・スケジュール実行をする時点でスクリプトでない）。`src/`＋`tests/`＋`pyproject.toml`。
- **責務でモジュール分割**。巨大モジュールを避ける（server / search / data_loader / rules_updater / tools）。
- 📘 **戻り値設計**：戻り値が4つ以上なら**専用の結果オブジェクト（dataclass等）**を返す（タプル展開ミス防止）。**特殊状態を `None` で表さず例外**を送出（チェック漏れ防止）。ただしMCPツールの「該当なし」は例外でなく**分かりやすいメッセージ**で返す（→ [[coding]]）。
- 📘 **例外は階層設計**：ルート独自例外を定義し派生させる。呼び出し側が対処できる粒度で投げる。
- 📘 **リソースは必ず `with`（コンテキストマネージャ）**。`try/except/else/finally` を役割で使い分ける。

## 5. FastMCP（サーバー層の規約）
> 「フレームワークを使う外側のシェル層」の規約。§4「コアはフレームワークを知らない」を破らない。
- **ツール関数は薄く**：受付・バリデーション・整形に専念し、検索ロジックは `search.py` 等のサービス層へ。
- **依存の注入を徹底**：HybridSearcher・httpxクライアント・設定は lifespan で生成しコンテキスト経由で渡す（テストで差し替え可能に）。**グローバルで依存を持ち回らない**（設定値は `settings.py`、ランタイム依存は注入）。
- **Pydantic v2 を全面活用**：ツールI/O・設定・バリデーション。型定義は §0 のとおり `models.py` に集約。
- **`async` を惰性で全付与しない**：`await` する非同期I/O（Scryfall呼び出し等）がある時だけ `async def`。CPU負荷（Embedding計算・rerank）や同期ブロッキングはイベントループを止めない工夫をする（`asyncio.to_thread` 等）。
- **リソースの確保/解放は `lifespan`**（起動時のインデックスロード・httpxクライアント生成、終了時のクローズ）。
- 独自例外階層で**一貫したエラー整形**。**ログは標準 `logging`**（`logger = logging.getLogger(__name__)`）。※stdio transport では **stdout に print しない**（プロトコルが壊れる）。ログは stderr へ。
- ⚠ AI支援は全ツールを安易に `async` 化／グローバル変数での依存持ち回し／Pydantic v1 記法を生成しがち。明示的に矯正する。

## 6. コーディング規約
### 基本スタイル
- **PEP 8**（4スペース、関数 snake_case、クラス PascalCase、定数 UPPER、private は `_` 前置）。整形は Black に任せ人手で議論しない。
- **f-string を標準**（`%`/`.format()` 不可）。デバッグは `f"{value=}"`。
- **`pathlib.Path`**（`os.path` 不可）。
- **データ保持は `dataclass`**（`__init__`/`__repr__`/`__eq__` を手書きしない）。
- **import はパッケージ絶対で**（例 `from aizorius_judge.models import RuleEntry`）。相対importは使わない。import順は Ruff(isort) に従う。
- **自己文書化を優先**：命名と構造で意図を表す。コメントは「why」を書き「what」を繰り返さない。docstring は **Google style・日本語可**。
### 📘 Pythonic な書き方（Effective Python）
- 複雑な式を1行に詰めない（ヘルパーへ抽出）。代入式 `:=` は繰り返し排除に有効な場面で。`match` は分割代入を伴う分岐に限る。
- 手動インデックスより `enumerate`、複数イテラブルは `zip`。スライス/アンパックを活用。
- 辞書の欠損キーは `get`/`setdefault`/`defaultdict` を使い分け（`in`＋`KeyError` の多用を避ける）。
- `map`/`filter` より内包表記。ただし3段以上ネストする内包表記は通常ループに展開。
- 大きなデータ（CR全文のパース等）は**ジェネレータ（`yield`）で逐次処理**。
- **可変デフォルト引数の罠**：デフォルトに `[]`/`{}`/現在時刻を使わず `None` を番兵に。省略可能な振る舞いはキーワード引数で明示。
- 単純なインターフェースはクラスより関数を受け取る（第一級オブジェクト）。多重継承は慎重に。

## 7. 並行性・性能（📘 Effective Python）
- **用途で使い分け**：ブロッキングI/Oは `asyncio`（Scryfall は httpx async）、CPUバウンド（Embedding・rerank）はイベントループ外へ（`asyncio.to_thread` / `concurrent.futures`）。GILで計算はスレッド並列化されない。
- **推測でなく計測**：`cProfile` でホットスポット特定 → 改善 → 再計測。性能キューは `deque`、ソート済み探索は `bisect`。

## 8. 運用・品質
- **テストは pytest のフィクスチャ**で前提を整え、依存（Scryfall・ChromaDB）をモック分離。`repr` でデバッグ出力を明確に。
  - 本プロジェクト固有：検索品質の回帰（`tests/test_search.py`）と裁定品質の評価（`evaluation/`）は**別物**として扱う（→ [EVALUATION.md](../../docs/EVALUATION.md)）。
  - 日本語の罠（全角半角・カード名表記ゆれ・PDF抽出ゴミ）は専用テストを最初から置く。
- **docstring を各関数・クラス・モジュールに**。`__all__` で公開APIを明示。非推奨化は警告を出して段階的に。
- **ログを小規模でも入れる**（どのクエリで・何件返し・何msかかったか）。標準 `logging` を使う（§5）。
- **CI でリント・型チェック・テストを必須化**（基準未達はマージ不可）。依存脆弱性は `uv audit`。SemVer。

## 9. 一次情報
- uv: https://docs.astral.sh/uv/ ／ Ruff: https://github.com/astral-sh/ruff ／ basedpyright: https://docs.basedpyright.com/ ／ pyright: https://microsoft.github.io/pyright/
- FastMCP: https://gofastmcp.com/ ／ MCP仕様: https://modelcontextprotocol.io/
- Real Python（Best Practices/Layout）: https://realpython.com/tutorials/best-practices/ ／ Modern Good Practices (Stuart Ellis): https://www.stuartellis.name/articles/python-modern-practices/
- PEP 484 / PEP 526 ／ Effective Python 3rd Edition: https://effectivepython.com/
