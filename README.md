# 除去加工可視化プロジェクト 仕様書（完全版 v3.1）

## 1. 概要
本プロジェクトは、除去加工（切削・旋削等）の工程ごとの形状変化を **段階的に可視化** することを目的とします。  
Phase1では **STLベースのミニマル表示** とし、工程（パイプライン）を任意に定義できる **API駆動構成** を採用します。

- Python（FastAPI + CadQuery）で工程処理
- C# クライアントから REST 経由でジョブ投稿
- 各ステップで「完成形 (solid)」「除去形状 (removed)」の STL を出力

## 2. 特徴とスコープ
| 項目 | 内容 |
|------|------|
| API仕様 | OpenAPI 3.0.3 (.NET互換) |
| 座標系 | workplane / CSYS |
| 面選択 | CadQuery 準拠 selector |
| 5軸対応 | 3+2割り出し (回転はSTEP2で導入) |
| 出力 | STL (solid / removed) |
| 表示 | Python `show()` または外部ビューア |

## 3. ケース例
- **Case1 (Machining)** : Block → FaceMill → EndMill (外周) → Hole  
- **Case2 (Lathe)** : Cylinder → FaceCut → 外径OD → 内径ID

## 4. 開発構成
```
project_root/
 ├─ README.md
 ├─ api/
 │   ├─ main.py
 │   ├─ models.py
 │   └─ cad_ops.py
 ├─ csharp_client/
 │   └─ ApiClient.cs
 ├─ data/
 │   ├─ input/
 │   └─ output/
 └─ docs/
     ├─ spec_api.yaml
     ├─ spec_python.md
     ├─ spec_csharp.md
     ├─ TODO_STEP1.md
     └─ SETUP_ENVIRONMENT.md
```
