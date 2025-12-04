// ============================================================
// Three.js ESM Import
// ============================================================

import * as THREE from "https://unpkg.com/three@0.160.0/build/three.module.js";
import { OrbitControls } from "https://unpkg.com/three@0.160.0/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "https://unpkg.com/three@0.160.0/examples/jsm/loaders/STLLoader.js";

// ============================================================
// API base
// ============================================================

const API_BASE = "http://localhost:8000";

// ============================================================
// FeatureGraph 状態
// ============================================================

let featureGraph = {
  units: "mm",
  origin: "world",
  stock: null,
  operations: []
};

// DOM
const fgJsonEl = document.getElementById("fgJson");
const logEl = document.getElementById("log");
const inputTextEl = document.getElementById("inputText");

// ボタン
document.getElementById("btnStock").onclick = onSetStock;
document.getElementById("btnFeature").onclick = onAddFeature;
document.getElementById("btnRun").onclick = onRunPipeline;
document.getElementById("btnReset").onclick = onReset;

// ============================================================
// 便利関数
// ============================================================

function appendLog(msg) {
  const t = new Date().toLocaleTimeString();
  logEl.textContent += `[${t}] ${msg}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

function updateView() {
  fgJsonEl.textContent = JSON.stringify(featureGraph, null, 2);
}

async function postJson(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

// ============================================================
// /nl/stock
// ============================================================

async function onSetStock() {
  const text = inputTextEl.value.trim();
  if (!text) return alert("素材命令を入力");

  appendLog("素材抽出…");

  try {
    const resp = await postJson("/nl/stock", { text, language: "ja" });
    featureGraph.stock = resp.stock;
    featureGraph.operations = [];
    updateView();
    appendLog("素材 OK");
  } catch (e) {
    appendLog("素材抽出エラー: " + e.message);
  }
}

// ============================================================
// /nl/feature
// ============================================================

async function onAddFeature() {
  const text = inputTextEl.value.trim();
  if (!text) return alert("フィーチャ命令を入力");
  if (!featureGraph.stock) return alert("先に素材を設定してください");

  appendLog("フィーチャ抽出…");

  try {
    const resp = await postJson("/nl/feature", { text, language: "ja" });
    featureGraph.operations.push(resp.op);
    updateView();
    appendLog("フィーチャ OK");
  } catch (e) {
    appendLog("フィーチャ抽出エラー: " + e.message);
  }
}

// ============================================================
// /pipeline/run → STL 表示
// ============================================================

async function onRunPipeline() {
  if (!featureGraph.stock) return alert("素材がありません");

  appendLog("パイプライン実行…");

  const req = {
    units: featureGraph.units,
    origin: featureGraph.origin,
    stock: featureGraph.stock,
    operations: featureGraph.operations,
    output_mode: "stl",
    file_template_solid: "web_solid_{step}_{name}.stl",
    file_template_removed: "web_removed_{step}_{name}.stl",
    dry_run: false
  };

  try {
    const resp = await postJson("/pipeline/run", req);
    if (resp.status !== "ok") {
      appendLog("実行エラー: " + resp.message);
      return;
    }

    const last = resp.steps[resp.steps.length - 1];
    if (!last.solid) {
      appendLog("solid がありません");
      return;
    }

    const url = toStlUrl(last.solid);
    appendLog("STL ロード: " + url);
    loadStl(url);

  } catch (e) {
    appendLog("パイプラインエラー: " + e.message);
  }
}

// バックエンドのファイルパス → URL
function toStlUrl(path) {
  const filename = path.split(/[\\/]/).pop();
  return API_BASE + "/output/" + filename; // FastAPI 側 StaticFiles("/output")
}

// ============================================================
// Three.js シーン
// ============================================================

let scene, camera, renderer, controls;
let currentMesh = null;

function initThree() {
  const container = document.getElementById("viewer");

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x111111);

  const w = container.clientWidth;
  const h = container.clientHeight;

  camera = new THREE.PerspectiveCamera(45, w / h, 1, 1000);
  camera.position.set(150, 100, 150);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(w, h);
  container.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const dl = new THREE.DirectionalLight(0xffffff, 0.8);
  dl.position.set(100, 200, 100);
  scene.add(dl);

  window.addEventListener("resize", onResize);
  animate();
}

function onResize() {
  const container = document.getElementById("viewer");
  const w = container.clientWidth;
  const h = container.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

function loadStl(url) {
  const loader = new STLLoader();
  loader.load(
    url,
    geometry => {
      if (currentMesh) {
        scene.remove(currentMesh);
        currentMesh.geometry.dispose();
      }
      geometry.computeVertexNormals();
      const material = new THREE.MeshPhongMaterial({ color: 0xcccccc });
      const mesh = new THREE.Mesh(geometry, material);

      geometry.center();
      mesh.rotation.x = -Math.PI / 2;

      scene.add(mesh);
      currentMesh = mesh;

      // Auto-frame
      const box = new THREE.Box3().setFromObject(mesh);
      const size = box.getSize(new THREE.Vector3()).length();
      const center = box.getCenter(new THREE.Vector3());

      controls.target.copy(center);
      camera.position.set(
        center.x + size,
        center.y + size,
        center.z + size
      );
      camera.lookAt(center);
    },
    undefined,
    err => {
      appendLog("STL load error: " + err.message);
    }
  );
}

// ============================================================
// リセット
// ============================================================

function onReset() {
  featureGraph = {
    units: "mm",
    origin: "world",
    stock: null,
    operations: []
  };
  updateView();
  appendLog("リセット完了");
}

// init
updateView();
appendLog("Three.js 初期化");
initThree();
