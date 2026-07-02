---
name: mcp-smoke
description: AIzorius Judge MCPサーバーのスモークテスト。「スモークテスト」「MCPの動作確認」「サーバー動く？」で起動、またはserver.py/tools/を変更した仕上げに積極的に使う。3ツール(search_rules/lookup_card/get_card_rulings)を代表入力で呼び、応答・該当なしメッセージ・日本語対応を確認してPASS/FAILで報告する。
model: sonnet
allowed-tools: Bash(uv run:*), Bash(npx:*), Read, Grep
---

# /mcp-smoke — MCPサーバー スモークテスト

実装後のサーバーが「Claude Desktop から使える状態か」を最短で確認する。pytest の単体テストとは別に、
**MCPプロトコル越しの実挙動**を見る。

## 前提
- Phase 1 完了後に有効。`src/aizorius_judge/server.py` が無ければ「未実装のためスキップ」と報告して終了。
- 本セッションに dev サーバーが接続済み（`.mcp.json` に登録済みで `mcp__aizorius-judge__*` ツールが見える）なら
  それを直接呼ぶ。未接続なら `uv run python` で in-process クライアント（fastmcp の Client）から呼ぶ。

## テストケース（代表入力）
| # | 呼び出し | 期待 |
|---|---|---|
| 1 | `search_rules("飛行 ブロック")` | CR 702.9系（飛行）が上位に含まれる |
| 2 | `search_rules("702.9b")` | ルール番号直接指定でそのルールtextが返る |
| 3 | `search_rules("到達", section="702")` | section絞り込みが機能する |
| 4 | `lookup_card("Lightning Bolt")` | カード情報が返る |
| 5 | `lookup_card("稲妻")` | 日本語カード名の fuzzy が機能する |
| 6 | `lookup_card("zzz_not_a_card_zzz")` | **エラーでなく**「見つからない」旨の分かりやすいメッセージ |
| 7 | `get_card_rulings("Oko, Thief of Crowns")` | 公式裁定リストが返る |

- Scryfall を叩くケース（4〜7）は連続実行せず、レート制限（50–100ms sleep）が実装で守られていることを
  ログ/実装で確認する。ネットワーク不通時は SKIP と報告。
- 対話デバッグが必要なら MCP Inspector を案内する：`npx @modelcontextprotocol/inspector uv run aizorius-judge`

## 出力
ケースごとに PASS / FAIL / SKIP の表。FAIL は再現コマンドと原因の当たり（1行）を添える。
最後に「Claude Desktop 登録可否」の判定を一言で述べる。
