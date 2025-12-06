# C#側仕様書（FastAPI連携） v3.1 完全版

## 1. 概要
C#クライアントは任意パイプラインを JSON で投稿し、加工ステップ結果（solid/removed）を取得します。

## 2. POST例
```csharp
var payload = new {
  units = "mm",
  origin = "world",
  stock = new { type = "block", params = new { w=50, h=30, d=20 } },
  operations = new object[] {
    new { op="mill:face", name="FaceMill", selector=">Z", workplane="XY", params=new { depth=2 } },
    new { op="mill:profile", name="EndMillOuter", selector="|Y", params=new { rect_w=45, rect_h=25, depth=5 } },
    new { op="drill:hole", name="Hole", selector=">Z", params=new { dia=5, depth=10, x=0, y=0 } }
  },
  output_mode = "stl",
  file_template_solid = "case1_{step:02d}_{name}_solid.stl",
  file_template_removed = "case1_{step:02d}_{name}_removed.stl",
  dry_run = false
};

var json = JsonConvert.SerializeObject(payload);
var res = await client.PostAsync("http://localhost:8000/pipeline/run",
    new StringContent(json, Encoding.UTF8, "application/json"));
```

## 3. レスポンス
```json
{
  "status": "ok",
  "steps": [
    {"step":1,"name":"FaceMill",
     "solid":"data/output/case1_01_FaceMill_solid.stl",
     "removed":"data/output/case1_01_FaceMill_removed.stl"}
  ]
}
```
