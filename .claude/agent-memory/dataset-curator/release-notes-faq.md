---
name: release-notes-faq
description: 公式リリースノート（ジャッジFAQ）由来の出題の作り方と、そこで検証済みのCR番号
metadata:
  type: reference
---

人間レビュアー要望で、LLM起案でなく公式リリースノートのQ&Aに根ざした問題を追加した（2026-07-02、10問→dataset計110問）。See [[cr-version]]。

## ソースと方針
- 一次ソース: magic.wizards.com のセット別 Release Notes（General Notes ＋ カード別Q&A）。WebFetchで取得可。
  - Marvel Super Heroes: https://magic.wizards.com/en/news/feature/marvel-super-heroes-release-notes （2026-06、多くの汎化裁定の宝庫）
  - 他: Secrets of Strixhaven, Lorwyn Eclipsed, FINAL FANTASY, TMNT, Avatar なども2026年に存在。
- **選定**: 一般ルールに汎化するQ&Aのみ採用（カードテキスト解釈で完結するもの・セット固有特殊ルールは不可）。
  結論は必ず CR 2026-06-19 (en) の条文で裏取り。リリースノートは「出題の種」、正解の根拠はCR。
- **Fan Content Policy**: 本文を逐語コピーしない。内容を自分の言葉で日本語に言い換え、notesにセット名＋URLを記す。
  source欄は "CR 2026-06-19 (en) + 『<セット名>』リリースノート"。
- lookup_card は「特定カードを例にする問」のみに付ける（結論はカードの固定属性＋CRで導ける範囲に限定）。

## この回で採用した10問と根拠番号（すべてCR 2026-06-19実在確認済み）
- stack_priority-016 誘発は原因呪文より先に解決/原因を打ち消しても誘発は残る: 603.3, 405.2 (+603.3b,608.1)
- stack_priority-017 解決時に全対象不適正→解決されず効果なし(ドローもなし): 608.2b (+608.2,608.2c)
- stack_priority-018 能力のコピーはスタックに置かれ「起動」でない/元より先に解決: 707.10, 405.2 (+707.2,608.1)
- stack_priority-019 反射誘発型能力（支払い後に対象を選ぶ）: 603.12 (+603.12a,603.7)
- combat-016 「戦場に出しつつ攻撃」は攻撃指定でない→攻撃/被攻撃誘発しない: 508.4, 508.3a (+508.3b,508.1)
- combat-017 攻撃/ブロック中をタップしても戦闘から取り除かれない: 506.4, 506.4a (+508.1)
- keywords-016 破壊不能でもダメージは記録/失えばSBAで破壊: 702.12b, 120.6 (+704.5g)
- layers-006 コピーはコピー可能値のみ（カウンター/装備/タップ/他効果は非コピー）: 707.2 (+707.2a,707.3)
- basic_rules-021 タップ済みは再タップ不可/「becomes tapped」誘発しない: 701.26a, 603.2e
- basic_rules-022 両面カードのゾーン別特性（他ゾーン=表面/スタック・戦場=上向きの面）: 712.8a, 712.8f (+712.8d)

## 第2回（2026-07-04）: EOE/FIN リリースノートから15問（layers/replacement/combat 厚め、承認前候補）
候補=`evaluation/dataset-candidates-faq.jsonl` + `evaluation/REVIEW-faq.md`。**別セット**（『Edge of Eternities』/『FINAL FANTASY』）を使用（第1回のMarvel回避）。
すべてCR 2026-06-19実在確認済み。ID連番: layers-007〜011 / replacement_effects-006〜009 / combat-018〜023。
- layers-007 設定P/T同士は後発が先発を上書き(7bタイムスタンプ)/修整・カウンターは7cで反映: 613.4b,613.4c(+613.7)
- layers-008 P/T定義の特性定義能力は全ゾーンで機能・自分を数える: 604.3(+613.4a)
- layers-009 コピー元が模倣中/トークン→現在のコピー可能値を得る(707.2の裏側,layers-006と別論点): 707.2(+707.3)
- layers-010 ライフ総量P/T(CDA)は継続更新→記録済み非致死ダメージが致死化しSBA: 613.4a,704.5g(+120.6)
- layers-011 基本P/Tを0/0設定→タフネス0でSBA墓地(破壊でない=破壊不能/再生不可): 704.5f,613.4b
- replacement_effects-006 カウンター2倍化2つ=4個(掛け算): 614.16,616.1(+614.5)
- replacement_effects-007 「死亡するなら追放」は死亡置換・墓地経由せず死亡誘発なし: 614.1a,614.6(+700.4)
- replacement_effects-008 シールドカウンターは破壊/被ダメージ置換だが生け贄は防げない: 122.1c(+701.21a)
- replacement_effects-009 追加トークン生成は元の指定(タップ/攻撃)を追加分にも及ぼす: 614.16,111.3
- combat-018 トランプル致死判定は記録済みダメージ考慮: 702.19b(+510.1c)
- combat-019 トランプル割り振り判定は軽減/防止/保護を考慮しない(018と同702.19bの別条文句): 702.19b(+702.19d)
- combat-020 威迫+「1体までブロック」=両立不能でブロック不可: 702.111b,509.1b
- combat-021 保護はそのクオリティ発生源の戦闘ダメージも軽減/「軽減されない」で上書き: 702.16e(+702.16f)
- combat-022 超過ダメージ=与ダメ合計が致死量超過分・記録済みで致死量減: 120.10
- combat-023 ブロック適正は指定時のみ判定・後で到達喪失しても戦闘に残る(combat-017の近縁別論点): 509.1b,509.1h(+702.9b)

### 検証で解消した過去の保留
- **シールドカウンターはCR 2026-06-19で122.1cに定義済み**（第1回で「CR定義薄く保留」としたが解消）。単一の置換効果＋単一の軽減効果を作り、破壊/被ダメージを「代わりにカウンター除去」で置換。生け贄(701.21a=戦場から直接墓地、破壊でない)は防げない。

### PDF全文の取得手順（feature版が要約truncされる場合）
- media.wizards.com の Release Notes PDF を WebFetch→ローカル保存(binary)→`uv run --with pypdf python`でextract_text→/tmpに.txt化して grep/python検索。EOE=69p, FIN=136p。feature版web要約より網羅的。

## 見送ったFAQ題材（CR裏取り困難 or セット固有）
- Power-up の「対象不適正でも起動済み・再使用不可」: MSH固有キーワードの特殊挙動。
- Plan(エンチャント・タイプ、ルール上の意味なし)/Vibranium/∞(harnessed): セット固有。
- Shield/Stun counter が生け贄を妨げない: shield counter がCRに定義薄く保留（stun=122系だが確信不足）。
- Prepare/Increment/Paradigm(Strixhaven)本体の挙動: セット固有。ただしincrementの「誘発が呪文より先/打ち消されても解決」は汎化してstack_priority-016に流用。
- Saga lore counter の再誘発なし(FF): 714系Saga固有寄りで今回保留。
- 「gains life は1イベント1回誘発、0ライフなら誘発せず」(Heroic Feast/119.9): 良問候補だが今回は10問枠から外した（次回候補）。
