# scripts/ingest_external_tests.py
import argparse, os, sys, zipfile, pathlib, json, csv, shutil, subprocess

try:
    import yaml
except Exception:
    yaml = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST_DIR = ROOT / "tests" / "my_cases"
CACHE_DIR = DEST_DIR / "_cache"
JS_READER = ROOT / "scripts" / "read-js-cases.cjs"

def _ensure_dirs():
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _extract_zip(zip_path: str):
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(CACHE_DIR)
    # สร้าง dummy config.json ที่ระดับ _cache/ ถ้าไม่มี
    cfg = CACHE_DIR / "config.json"
    if not cfg.exists():
        cfg.write_text("{}", encoding="utf-8")

def _is_case_like(fp: pathlib.Path) -> bool:
    if "__MACOSX" in fp.parts:  # ข้ามขยะจาก macOS
        return False
    return fp.suffix.lower() in [".json", ".yaml", ".yml", ".csv", ".js"]

def _scan_case_files():
    files = []
    for p in CACHE_DIR.rglob("*"):
        if p.is_file() and _is_case_like(p):
            files.append(p)
    return files

def _load_cases_from_json(p: pathlib.Path):
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "cases" in data and isinstance(data["cases"], list):
            return data["cases"]
        return [data]
    if isinstance(data, list):
        return data
    return []

def _load_cases_from_yaml(p: pathlib.Path):
    if yaml is None:
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "cases" in data and isinstance(data["cases"], list):
            return data["cases"]
        return [data]
    if isinstance(data, list):
        return data
    return []

def _load_cases_from_csv(p: pathlib.Path):
    out = []
    with p.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(dict(row))
    return out

def _load_cases_from_js(p: pathlib.Path):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("ไม่พบ 'node' — ติดตั้ง Node.js ก่อน")
    cmd = [node, str(JS_READER), str(p)]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"อ่านไฟล์ JS ไม่ได้: {p}\n{res.stderr}")
    data = json.loads(res.stdout)
    if isinstance(data, dict):
        if "cases" in data and isinstance(data["cases"], list):
            return data["cases"]
        return [data]
    if isinstance(data, list):
        return data
    return []

def _load_cases(fp: pathlib.Path):
    s = fp.suffix.lower()
    if s == ".json":
        return _load_cases_from_json(fp)
    if s in [".yaml", ".yml"]:
        return _load_cases_from_yaml(fp)
    if s == ".csv":
        return _load_cases_from_csv(fp)
    if s == ".js":
        return _load_cases_from_js(fp)
    return []

def _to_offer(case: dict, idx: int) -> dict:
    offer = {
        "offer_id": case.get("offer_id", f"CASE-{idx:04d}"),
        "customer_id": case.get("customer_id", "C1"),
        "origin_address": case.get("origin_address") or case.get("address") or "Bangkok, Thailand",
        "volume_cbm": float(case.get("volume_cbm", case.get("volume", 120))),
        "duration_days": int(case.get("duration_days", case.get("days", 30))),
        "sla": case.get("sla", {"latest_dropoff_hour": 18, "weekday_only": True}),
    }
    if "origin_lat" in case and "origin_lng" in case:
        offer["origin_lat"] = float(case["origin_lat"])
        offer["origin_lng"] = float(case["origin_lng"])
    return offer

def _to_expected(case: dict) -> dict:
    exp = case.get("expected", {})
    return {
        "accept": exp.get("accept"),
        "chosen_warehouse": exp.get("chosen_warehouse"),
        "min_candidates": exp.get("min_candidates", 1),
    }

def _gen_pytest_file(cases):
    target = DEST_DIR / "test_generated_cases.py"
    lines = []
    lines.append("import json, uuid")
    lines.append("from agents.dispatcher_agent import run")
    lines.append("")
    lines.append("CASES = []")
    for i, c in enumerate(cases):
        offer = _to_offer(c, i)
        expected = _to_expected(c)
        offer_json = json.dumps(offer, ensure_ascii=False)
        expected_json = json.dumps(expected, ensure_ascii=False)
        lines.append("CASES.append((")
        lines.append(f"json.loads(r'''{offer_json}''')")
        lines.append(",")
        lines.append(f"json.loads(r'''{expected_json}''')")
        lines.append("))")
    lines.append("")
    lines.append("def _check_expected(res, expected):")
    lines.append("    if expected.get('accept') is not None:")
    lines.append("        assert bool(res.get('accept')) == bool(expected['accept'])")
    lines.append("    if expected.get('chosen_warehouse') is not None:")
    lines.append("        assert res.get('chosen_warehouse') == expected['chosen_warehouse']")
    lines.append("    min_c = int(expected.get('min_candidates', 0))")
    lines.append("    assert len(res.get('candidates', [])) >= min_c")
    lines.append("")
    lines.append("def test_external_cases_param():")
    lines.append("    assert len(CASES) > 0, 'No cases imported'")
    lines.append("    for i, (offer, expected) in enumerate(CASES):")
    lines.append("        res = run(offer)")
    lines.append("        assert isinstance(res, dict)")
    lines.append("        _check_expected(res, expected)")
    target.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote: {target}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', required=True, help='path to test.zip')
    args = ap.parse_args()

    _ensure_dirs()
    _extract_zip(args.zip)

    files = _scan_case_files()
    if not files:
        print("[WARN] ไม่พบไฟล์ .json/.yaml/.yml/.csv/.js ใน zip")
        sys.exit(1)

    all_cases = []
    for fp in files:
        try:
            all_cases.extend(_load_cases(fp))
        except Exception as e:
            print(f"[SKIP] {fp}: {e}")

    if not all_cases:
        print("[WARN] zip มีไฟล์ แต่แปลงเป็น case ไม่ได้ — โยนตัวอย่างไฟล์มาให้ดูได้")
        sys.exit(1)

    _gen_pytest_file(all_cases)
    print(f"[INFO] Imported {len(all_cases)} case(s) from {len(files)} file(s).")

if __name__ == "__main__":
    main()
