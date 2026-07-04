# レビュー: リリースノート由来 FAQ 拡充候補（15問・人間承認前）

このファイルは `evaluation/dataset-candidates-faq.jsonl`（15問）の人間レビュー用サマリ。
承認されたら本体 `evaluation/dataset.jsonl` へ手動反映する。**dataset 本体には未反映**。

## 方針と前提
- **手薄カテゴリを厚く**: layers 5 / replacement_effects 4 / combat 6（basic_rules は追加なし）。
- **既出セットを回避**: 既存 FAQ 10問はすべて『Marvel Super Heroes』由来。今回は**別セット**の公式リリースノートを使用。
  - 『Edge of Eternities』(EOE): https://magic.wizards.com/en/news/feature/edge-of-eternities-release-notes
  - 『FINAL FANTASY』(FIN): https://magic.wizards.com/en/news/feature/final-fantasy-release-notes
- **Fan Content Policy**: リリースノート本文は逐語コピーせず日本語に言い換え。出典（セット名＋URL）を各問 notes に記録。裁定の根拠は必ず CR 2026-06-19 (en)（`data/comprehensive_rules_en.json`）で照合。
- **番号照合**: rules_cited / retrieval_relevant_rules / must_cite_rules をすべて CR 2026-06-19 (en) で実在・妥当性確認済み。
- **機械検証**: `uv run python scripts/validate_dataset.py evaluation/dataset-candidates-faq.jsonl` → PASS（15問）。本体との ID/設問衝突なし。ID は各カテゴリの連番の続き（layers-007〜011 / replacement_effects-006〜009 / combat-018〜023）。

## 各問の要点（ID / 出典セット / 主根拠 / 論点）

### layers（5問）
- **layers-007**（EOE: Genemorph Imago/Labship, 同趣旨 FIN: Eye of Nidhogg/Wrecking Ball Arm）— 613.4b, 613.4c
  P/Tを設定する効果が複数あるとき、後発の設定効果が先発を上書き（7bのタイムスタンプ）。修整・カウンター（7c）は生じた時点に関わらず反映。既存 layers-002（設定 vs 修整の順序）とは別論点（設定効果同士の上書き）。
- **layers-008**（EOE: Cosmogoyf/Harmonious Grovestrider）— 604.3
  P/Tを定義する特性定義能力は全ゾーンで機能。追放領域等でも自分自身を数に含める。
- **layers-009**（EOE: Adagia, 同趣旨 FIN: The Fire Crystal）— 707.2
  コピー元がさらに別を模倣中／トークンのとき、印刷値でなく現在のコピー可能値を得る。既存 layers-006（カウンター等はコピーされない）の裏側の論点。
- **layers-010**（FIN: Aettir and Priwen）— 613.4a, 704.5g
  ライフ総量で決まるP/T（特性定義能力）は継続更新。ライフ減→タフネス減で、記録済みの非致死ダメージが致死化しSBAで破壊。
- **layers-011**（EOE: ビークルを0/0にする効果）— 704.5f, 613.4b
  基本P/Tを0/0に設定→タフネス0でSBAにより墓地。破壊ではないので破壊不能・再生で防げない。

### replacement_effects（4問）
- **replacement_effects-006**（EOE: Loading Zone, 同趣旨 FIN: The Earth Crystal）— 614.16, 616.1
  カウンター2倍化を2つ→4個（掛け算・足し算でない）。614.16「他の置換の結果にも適用」が根拠。
- **replacement_effects-007**（FIN: Suplex / finality counter）— 614.1a, 614.6
  「死亡するなら代わりに追放」は死亡を置換。墓地を経由せず死亡誘発も起きない。致死ダメージ以外の死因にも適用。
- **replacement_effects-008**（FIN: shield counter）— 122.1c
  シールドカウンターは破壊・被ダメージを置換／軽減するが、生け贄（=戦場から直接墓地に移す、破壊でない）は防げない。**CR 2026-06-19でシールドカウンターは122.1cに定義済み**（前回メモで保留にしていたが解消）。
- **replacement_effects-009**（EOE: Exalted Sunborn）— 614.16, 111.3
  追加トークン生成の置換効果は、元の効果が指定した特性・状態（例「タップ状態で攻撃」）を追加トークンにも及ぼす。

### combat（6問）
- **combat-018**（EOE: Orbital Plunge / Cryoshatter）— 702.19b
  トランプルの致死判定は記録済みダメージ・同ステップの他ダメージを考慮（＝負傷済みブロッカーには少なくて済む）。
- **combat-019**（FIN: Diamond Weapon）— 702.19b
  トランプルの割り振り判定では軽減・防止・保護を考慮しない。致死量を割り振らないと防御プレイヤーへ通せない。combat-018と同じ702.19bだが別の条文句（「実際に与えられる量を変える効果は考慮しない」）を検証。
- **combat-020**（EOE: Meltstrider's Resolve + 威迫）— 702.111b, 509.1b
  「2体以上でしかブロック不可（威迫）」と「1体を超えてブロック不可」が両立不能→まったくブロックされない。既存 combat-003（威迫の基本）とは別論点（制限の衝突）。
- **combat-021**（EOE: Frenzied Baloth）— 702.16e
  保護はそのクオリティの発生源からの戦闘ダメージも軽減する。「軽減されない」と明示する効果があれば上書きされる。
- **combat-022**（EOE: Orbital Plunge の超過ダメージ）— 120.10
  超過ダメージの定義：与ダメージ合計が致死量を超えた差分。致死量は記録済みダメージで減る。ダメージ後に判定。
- **combat-023**（FIN: Sphere Grid）— 509.1b, 509.1h
  ブロック適正はブロック指定時のみチェック。指定後に到達等の能力を失っても戦闘から取り除かれない。既存 combat-017（タップされても戦闘に残る）と近縁だが別論点（能力喪失）。

## 要人間確認事項
1. **combat-018 / combat-019 が同一 must_cite（702.19b）**: 意図的に同ルールの別条文句を分けて検証している。過度な集中と見なすなら一方を保留可。判断を仰ぐ。
2. **replacement_effects-009 の根拠強度**: 「追加トークンが同じ状態を得る」の直接条文は薄く、614.16（適用対象）＋111.3（トークン特性は生成効果が定義）からの合成。裁定自体は公式リリースノートで明言。必要なら保留候補。
3. **combat-021 のクオリティ例**: 「赤への保護」を例示に用いたが、結論は色に限らず全クオリティに一般化（notesに明記済み）。設問の一般化度が十分か確認。
4. **layers-009**: 既存 layers-006（コピーはコピー可能値のみ）と主根拠が同じ707.2。論点（コピー元がさらに模倣中／トークンの扱い）は別だが、近さが気になる場合は要調整。
5. **セット配分**: EOE 9問 / FIN 6問。片寄りが問題なら次回で調整。

## 承認記録欄
- [ ] 出典・言い換えの妥当性を確認した（Fan Content Policy 範囲内）
- [ ] rules_cited / must_cite / retrieval_relevant の妥当性を確認した
- [ ] 結論が現行CRで正しいことを確認した
- [ ] 本体 `evaluation/dataset.jsonl` へ反映してよい

承認者: __________  日付: __________  コメント: __________
