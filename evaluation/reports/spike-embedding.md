# Embedding bake-off（Phase 0 スパイク）

- クエリ: golden dataset 110問（日本語）
- コーパス: 英語CR全ルール（en）／英語＋日本語連結（en+ja）、3153件
- 指標: recall@5（retrieval_relevant_rules に対する再現率）・hit@5（1件以上ヒット）
- Vector検索のみの比較。BM25・RRF・rerank は Phase 1 で評価する。

| モデル | コーパス | recall@5 | hit@5 | index時間 |
|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | en | 0.203 | 0.473 | 6.9s |
| paraphrase-multilingual-MiniLM-L12-v2 | en+ja | 0.201 | 0.436 | 9.8s |
| intfloat/multilingual-e5-small | en | 0.248 | 0.536 | 8.4s |
| intfloat/multilingual-e5-small | en+ja | 0.377 | 0.709 | 18.0s |
| intfloat/multilingual-e5-base | en | 0.309 | 0.618 | 20.9s |
| intfloat/multilingual-e5-base | en+ja | 0.401 | 0.773 | 41.5s |
