# TODO Step2（座標系・割り出し対応フェーズ）

## 0. Step2 のゴール

Phase1 で実装した「直交座標＋固定 Workplane ベース」の加工パイプラインを拡張し、

- **座標系（CSYS）／Workplane の明示的な管理**
- **3+2 割り出し（A/B/C 回転によるワーク姿勢変更）**
- 将来の 5 軸工具方向指定（スワーフ加工など）への足がかり

を作る。

> ※ 連続 5 軸（工具方向が常時変化するパス）は Phase3 以降とし、  
> Step2 では「割り出し 5 軸（3+2）」までをスコープとする。

---

## 1. 仕様・設計タスク

### 1-1. API / YAML 仕様の拡張

- Case4 `spec_api.yaml` に **座標系・姿勢** に関する項目を追加
  - Case4 各 `operation` に対して、任意の CSYS を参照できるようにする
    - 例: `csys_ref: "CSYS1"`
  - Case4 パイプライン全体に定義する CSYS 一覧
    - 例: `csys_list[]` に、原点・姿勢（回転）を定義  
      - world 基準: 平行移動 + オイラー角 or ロール/ピッチ/ヨー
      - CadQuery の `Workplane.transformed()` に対応付けできる形式
- Case4 「ワーク割り出し専用オペレーション」の設計
  - Case4 例: `op: "setup:index"` のような仮想 op を設け、以降の op の基準 CSYS を切り替える
  - Case4 実際には形状を削らないが、ログとステップ番号は進める

### 1-2. Cadモデリング観点での CSYS ルール整理

- Case4 `spec_python.md` に CadQuery での CSYS/Workplane の扱いを追記
  - Case4 world 座標 vs Workplane ローカル座標の関係
  - Case4 `Workplane.transformed()` / `cq.CQ().newObject([...])` 等の利用方針
- Case4 「どの段階でどの CSYS が有効か」を明示するルールを書く
  - Case4 デフォルト CSYS（world）
  - Case4 `setup:index` 実行後のアクティブ CSYS
  - Case4 1 ステップ内での複数 Workplane 利用の可否（Step2 では 1 op = 1 CSYS と割り切る）

---

## 2. Python / パイプライン実装タスク

### 2-1. CSYS 管理基盤

- Case4 `cad_ops.py`（または専用モジュール）に CSYS 管理クラスを追加
  - Case4 CSYS 定義の読み込み（JSON / YAML → Python オブジェクト）
  - Case4 アクティブ CSYS の切り替え
  - Case4 CadQuery の Workplane を生成するユーティリティ
    - 例: `get_workplane(csys_name: str) -> cq.Workplane`
- Case4 パイプライン実行時の状態管理
  - Case4 現在の solid / removed に加え、「現在の CSYS 名」を状態として保持
  - Case4 ログに「姿勢（CSYS）」を出力

### 2-2. 割り出しオペレーションの実装

- Case4 `op: "setup:index"`（仮称）の実装
  - Case4 指定された `csys_ref` にアクティブ CSYS を切り替える
  - Case4 solid を回転させるのではなく、Workplane の基準を切り替える方針か、
        solid 自体を回転させる方針かを決定する（※要設計）
  - Case4 ログ・ステップ出力（例: `step_01_IndexToA90` のような STL 出力）を行うかどうかを決定

### 2-3. 既存オペレーションへの CSYS 適用

- Case4 `mill:face` / `mill:profile` / `lathe:face` / `lathe:turn_od_profile` など既存 op を
      CSYS 対応にリファクタリング
  - Case4 Workplane の生成箇所を一元化し、常に「現在の CSYS」から Workplane を作る
  - Case4 既存の Case1 / Case2 は `csys_ref` を指定しなくても動く（後方互換）

---

## 3. サンプルケース＆テスト

### 3-1. 新ケース定義

- Case4 `Case4 (Indexing 3+2 Milling)` の追加
  - Case4 例: 直方体ブロックを複数回割り出して、各面にポケット or 穴加工
  - Case4 JSON / YAML のサンプルを `data/input/Case4_indexing.json` 等で追加
- Case4 `Case5 (Lathe + 割り出し)` が必要なら別途定義

### 3-2. 出力・検証

- Case4 各割り出しステップごとに STL を出力
  - Case4 `step_00_Stock` / `step_01_IndexA90` / `step_02_Pocket` ... のような命名
- Case4 手動検証
  - Case4 Blender などで STL を読み込み、姿勢が正しく変化していることを目視確認
- Case4 自動テスト
  - Case4 pytest 等で Case4 のパイプラインを実行し、
        - ステップ数
        - 出力ファイルの存在
        をチェックするテストを追加

---

## 4. C# クライアント拡張

- Case4 `spec_csharp.md` に CSYS / 割り出しパラメータのマッピングを追記
- Case4 C# DTO の更新
  - Case4 `CsysDefinition` クラス
  - Case4 `Operation.csys_ref` プロパティ
- Case4 新しい Case4 を投げるサンプルコード追加
  - Case4 JSON or YAML をロードし、そのまま API に POST するサンプル
- Case4 将来の UI 連携を見据えたインタフェース整理
  - Case4 画面側から「姿勢プリセット」を選ぶだけで JSON が組み立てられる構造かどうか確認

---

## 5. ログ・トレース・運用面

- Case4 ログ形式の拡張
  - Case4 各ステップに「csys_name」「回転角（A/B/C）」等を追記
- Case4 エラー時の改善
  - Case4 未定義 CSYS 名が指定された場合のエラーメッセージ
  - Case4 CSYS 関連のパラメータ不足（角度未指定など）の検出
- Case4 SETUP_ENVIRONMENT.md への追記
  - Case4 Step2 用のケース（Case4）の実行手順
  - Case4 「どれが Phase1 完了分で、どれが Step2 追加分か」を明示するコメント
