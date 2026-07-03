# 検索チューニング実験（Phase 1）

- dataset 110問（日本語クエリ）/ recall@5・MRR / 候補pool=50

| 構成 | recall@5 | MRR |
|---|---|---|
| vector[combined] | 0.401 | 0.595 |
| vector[en] | 0.309 | 0.470 |
| vector[ja] | 0.423 | 0.591 |
| vector[dual] | 0.423 | 0.591 |
| bm25[combined] | 0.398 | 0.546 |
| bm25[ja] | 0.403 | 0.547 |
| rrf(vector[combined]+bm25[combined]) | 0.402 | 0.591 |
| rrf(vector[dual]+bm25[ja]) | 0.439 | 0.621 |
| rrf(vector[dual]+bm25[combined]) | 0.429 | 0.621 |
| rrf(vector[dual]+vector[combined]+bm25[ja]) | 0.423 | 0.612 |
| rrf(dual+bm25[combined]) + bge-reranker-v2-m3 | 0.519 | 0.757 |

## 追加実験と最終構成（Phase 1 確定）

| 構成 | recall@5 | must_cite@5 | MRR | p50/p95 |
|---|---|---|---|---|
| **既定: rrf(vector[dual]+bm25[combined]) + bge-reranker-v2-m3(pool50)** | **0.519** | **0.805** | 0.753 | 4.6s/9.1s |
| 高速: rrf(vector[dual]+bm25[combined])（rerankなし） | 0.429 | 0.636 | 0.607 | 29ms/50ms |
| bge-m3 pool20/len384（レイテンシ削減案） | 0.502 | 0.764 | — | 3.5s/4.4s |
| bge-m3 pool30/len256（同） | 0.478 | 0.705 | — | 2.0s/2.0s |
| mmarco-mMiniLMv2（軽量多言語reranker） | 0.415 | 0.618 | — | 1.2s/1.3s |
| 候補拡張（兄弟＋参照, 天井0.91）＋rerank | 0.502 | — | 0.730 | — |
| rerank×ベースのRRFアンサンブル | 0.454 | — | 0.655 | — |

- 決定: **品質優先の既定構成**を採用（must_cite recall@5 ≥ 0.8 を達成する唯一の案）。レイテンシ削減はどの案も品質が大きく崩れるため見送り、rerank無効化（高速構成）を設定で提供する。
- 候補拡張は天井（候補内正解率）を0.83→0.91に上げるがrerankがdistractor増に負けるため不採用（rerankerの改善後に再評価の価値あり）。
