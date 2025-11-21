# scripts/inspect_cases.py
import os
import sys
import json
import argparse
from pathlib import Path
from core.db import init_db, seed_warehouses, save_case_runs, save_decision_result

# --- ทำให้ import โมดูลในโปรเจกต์ได้ ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


def load_env(env_file: str | None):
    """
    โหลดตัวแปรจาก .env ถ้าระบุไฟล์มา
    ถ้าไม่ระบุ จะพยายามโหลดจาก ROOT/.env อัตโนมัติ
    """
    try:
        from dotenv import load_dotenv
    except Exception:
        print("[WARN] python-dotenv not installed; skip .env loading")
        return

    if env_file:
        ok = load_dotenv(env_file)
        print(f"[INFO] .env loaded from: {env_file}" if ok else f"[WARN] failed to load {env_file}")
    else:
        default_env = ROOT / ".env"
        if default_env.exists():
            ok = load_dotenv(default_env)
            print(f"[INFO] .env loaded from: {default_env}" if ok else f"[WARN] failed to load {default_env}")
        else:
            print("[WARN] no --env-file and ROOT/.env not found; location tools may fail")


def load_cases(module_path: str):
    """
    module_path เช่น 'tests.my_cases.test_generated_cases'
    โมดูลต้องมีตัวแปร CASES = List[Tuple[offer_dict, expected_dict]]
    """
    mod = __import__(module_path, fromlist=['CASES'])
    if not hasattr(mod, "CASES"):
        raise RuntimeError(f"{module_path} ไม่มีตัวแปร CASES")
    return getattr(mod, "CASES")


def run_case(run_fn, offer: dict) -> dict:
    """
    ครอบการตัดสินใจให้ไม่ล้มทั้งสคริปต์
    - ถ้า agent โยน exception จะได้ผลลัพธ์มาตรฐานกลับไป
    """
    try:
        return run_fn(offer)
    except Exception as e:
        return {
            "accept": False,
            "chosen_warehouse": None,
            "reason": f"error: {e}",
            "priced_amount": None,
            "candidates": [],
        }


def main():
    ap = argparse.ArgumentParser(description="Inspect external test cases and summarize decisions.")
    ap.add_argument(
        "--module",
        default="tests.my_cases.test_generated_cases",
        help="โมดูลที่มีตัวแปร CASES (ค่าเริ่มต้นคือ tests.my_cases.test_generated_cases)",
    )
    ap.add_argument("--env-file", default=None, help="ชี้ไฟล์ .env (ถ้าต้องการ)")
    ap.add_argument("--json-out", default=None, help="บันทึกผลเป็น JSON (summary rows)")
    ap.add_argument("--csv-out", default=None, help="บันทึกผลเป็น CSV (summary rows)")
    ap.add_argument("--verbose", action="store_true", help="พิมพ์รายละเอียด candidates")

    # เลือก engine: dispatcher ตรง ๆ หรือผ่าน LangGraph เหมือน app.py
    ap.add_argument(
        "--engine",
        choices=["dispatcher", "graph"],
        default="dispatcher",
        help="เลือก engine ในการรันเคส: dispatcher (ตรง) หรือ graph (LangGraph app.invoke) [default: dispatcher]",
    )

    # ตัวเลือกบันทึกลง Mongo (ต้องตั้ง DB_BACKEND=mongo + MONGO_URI ใน .env)
    ap.add_argument("--persist-cases", action="store_true",
                    help="บันทึกสรุปรวม (rows) ลง MongoDB.case_runs")
    ap.add_argument("--persist-decisions", action="store_true",
                    help="บันทึกแต่ละ decision ลง MongoDB.decision_runs")
    args = ap.parse_args()

    # 1) โหลด .env ก่อน import core/*
    load_env(args.env_file)

    # 2) เตรียม DB + seed
    from core.db import init_db, seed_warehouses, save_case_runs, save_decision_result
    init_db()
    seed_warehouses()

    # 3) โหลดเคส
    CASES = load_cases(args.module)

    # 3.1 เลือก engine ที่จะใช้ตัดสินใจ
    if args.engine == "graph":
        # ใช้กราฟ LangGraph เหมือนใน app.py
        from app import build
        from core.schema import Offer

        app = build()

        def decide(offer: dict) -> dict:
            # สร้าง Offer model จาก dict แล้วส่งเข้า graph
            offer_model = Offer(**offer)
            state = app.invoke({"offer": offer_model})
            # graph ของเราบันทึก decision อยู่ใน state["decision"]
            return state.get("decision") or {}
    else:
        # ใช้ dispatcher_agent.run แบบเดิม
        from agents.dispatcher_agent import run as _decide

        def decide(offer: dict) -> dict:
            return _decide(offer)

    rows = []
    accepted = []

    for i, (offer, expected) in enumerate(CASES, 1):
        res = run_case(decide, offer)

        # หา candidate ผู้ชนะตาม chosen_warehouse
        chosen_id = res.get("chosen_warehouse")
        chosen_cand = None
        for c in res.get("candidates", []):
            if c.get("warehouse_id") == chosen_id:
                chosen_cand = c
                break

        # ระบุ origin ให้ชัด: address หรือ lat,lng
        origin_repr = offer.get("origin_address")
        if not origin_repr:
            olat, olng = offer.get("origin_lat"), offer.get("origin_lng")
            if olat is not None and olng is not None:
                origin_repr = f"{olat},{olng}"
            else:
                origin_repr = None

        # สร้างแถวสรุป (มักใช้วิเคราะห์ผลรวดเร็ว)
        row = {
            "idx": i,
            "offer_id": offer.get("offer_id"),
            "origin": origin_repr,
            "vol": offer.get("volume_cbm"),
            "exp_accept": expected.get("accept"),
            "exp_chosen": expected.get("chosen_warehouse"),
            "exp_min_candidates": expected.get("min_candidates"),
            "act_accept": res.get("accept"),
            "chosen": res.get("chosen_warehouse"),
            "price": res.get("priced_amount"),
            "cost": (chosen_cand or {}).get("cost"),
            "profit": (chosen_cand or {}).get("profit"),
            "margin": (chosen_cand or {}).get("margin"),
            "cands": len(res.get("candidates", [])),
            "reason": res.get("reason"),
        }
        rows.append(row)

        if res.get("accept"):
            accepted.append(offer.get("offer_id"))

        # แสดงผลรายเคสแบบย่อ
        reason = res.get("reason") or {}
        if isinstance(reason, dict):
            reason_type = reason.get("type")
        else:
            reason_type = None

        mark = "OK " if (expected.get("accept") is None or expected.get("accept") == res.get("accept")) else "MISMATCH"
        print(
            f"[{row['idx']:02}] {mark} "
            f"offer={row['offer_id']} chosen={row['chosen']} "
            f"price={row['price']} profit={row['profit']} cost={row['cost']} "
            f"cands={row['cands']} reason_type={reason_type}"
        )

        # รายละเอียดผู้สมัคร (ถ้า --verbose)
        if args.verbose:
            for c in res.get("candidates", []):
                rt = c.get("route") or {}
                print(
                    "   -",
                    c.get("warehouse_id"),
                    f"km={rt.get('km')}",
                    f"min={rt.get('minutes')}",
                    f"score={round(c.get('score', 0), 3)}",
                    f"price={c.get('price_amount')}",
                    f"cost={c.get('cost')}",
                    f"profit={c.get('profit')}",
                    f"margin={c.get('margin')}",
                    f"util={c.get('utilization')}",
                )

        # (ออปชัน) Persist decision รายเคส → Mongo
        if args.persist_decisions:
            try:
                meta = {
                    "source": "inspect_cases",
                    "module": args.module,
                    "idx": i,
                    "engine": args.engine,
                }
                save_decision_result(offer, res, meta=meta)
            except Exception as e:
                print(f"[WARN] save_decision_result failed: {e}")

    # 4) สรุปรวม
    print("\n=== SUMMARY ===")
    print(f"Accepted {len(accepted)}/{len(rows)}:", accepted)

    # 5) ออกรายงาน JSON
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"[OK] wrote JSON: {args.json_out}")

    # 6) ออกรายงาน CSV
    if args.csv_out:
        import csv
        Path(args.csv_out).parent.mkdir(parents=True, exist_ok=True)
        # รวมคีย์ทั้งหมดเพื่อกันบางคอลัมน์หาย
        fieldnames = set()
        for r in rows:
            fieldnames.update(r.keys())
        fieldnames = list(fieldnames) if fieldnames else [
            "idx","offer_id","origin","vol","exp_accept","act_accept",
            "chosen","price","cost","profit","margin","cands","reason"
        ]
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"[OK] wrote CSV: {args.csv_out}")

    # 7) (ออปชัน) Persist summary rows → Mongo
    if args.persist_cases:
        try:
            from core.db import save_case_runs  # re-import เผื่อ users แยกไฟล์
            meta = {
                "source": "inspect_cases",
                "module": args.module,
                "n_rows": len(rows),
                "engine": args.engine,
            }
            save_case_runs(rows, meta=meta)
            print("[OK] saved aggregated rows to Mongo (case_runs)")
        except Exception as e:
            print(f"[WARN] save_case_runs failed: {e}")


if __name__ == "__main__":
    main()
