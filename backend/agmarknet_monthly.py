#!/usr/bin/env python3
"""Backfill district monthly average prices from AGMARKNET.

Source: the public report behind
https://agmarknet.gov.in/districtwholesalemonthanalysis
("District-wise Wholesale Prices Monthly Analysis"), served by

    GET https://api.agmarknet.gov.in/v1/price-trend/wholesale-prices-monthly
        ?report_mode=Districtwise&commodity=<id>&state=<id>&year=YYYY&month=M

One response carries a row per district with **three** average prices:
the requested month, the previous month, and the same month a year earlier.
That is enough to cover two years with twelve calls per state+commodity.

Every number is a real published monthly average (Rs/quintal) — nothing here is
interpolated or invented. Rows land in the `mandi_monthly` table of the price
store, which the forecaster reads when a state has no daily history.

Usage
-----
    # everything the app calls "major crops", all states, 2 years
    python agmarknet_monthly.py --states all --years 2025 2026

    # one state / one crop, very quick smoke test
    python agmarknet_monthly.py --states Maharashtra --commodities Tomato --years 2025

    # see what would be fetched without writing
    python agmarknet_monthly.py --states Goa --years 2025 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as date_cls
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import requests

import price_store

BASE = "https://api.agmarknet.gov.in/v1"
REPORT = f"{BASE}/price-trend/wholesale-prices-monthly"
HERE = Path(__file__).resolve().parent
REF_CACHE = HERE / "data" / "agmarknet_ref.json"

MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]

# Crops the app recommends and prices. Names are matched against the AGMARKNET
# commodity list so ids stay correct if the catalogue shifts.
MAJOR_CROPS: List[str] = [
    "Rice", "Wheat", "Maize", "Onion", "Tomato", "Potato", "Banana",
    "Cotton", "Soyabean", "Groundnut", "Green Chilli", "Brinjal",
    "Coconut", "Mango", "Turmeric", "Ginger", "Garlic", "Cauliflower",
    "Cabbage", "Carrot",
    # Millets and pulses the advisor recommends, under the exact spellings
    # AGMARKNET publishes. Without these, ragi/jowar/bajra/tur have no monthly
    # series and the forecast page has nothing to run on.
    "Ragi(Finger Millet)", "Jowar(Sorghum)", "Bajra(Pearl Millet/Cumbu)",
    "Paddy(Common)", "Red gram/Arhar/Tur(whole)",
    "Bengal Gram(Gram)(Whole)", "Green Gram(Moong)(Whole)",
    "Black Gram(Urd Beans)(Whole)",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "FarmIntel/3.0 (capstone price history backfill)",
    "Accept": "application/json",
    "Referer": "https://agmarknet.gov.in/districtwholesalemonthanalysis",
})


def _get(url: str, params: Optional[dict] = None,
         timeout: float = 25.0, attempts: int = 5) -> Optional[dict]:
    for i in range(attempts):
        try:
            r = SESSION.get(url, params=params or {}, timeout=timeout)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
                return r.json()
            if r.status_code == 400:
                return None            # invalid params — retrying will not help
            if r.status_code == 429:
                # The portal throttles per IP, sometimes for many minutes at a
                # time. Wait it out in growing steps rather than giving up —
                # this job is resumable, so slow is fine and gaps are not.
                retry_after = r.headers.get("Retry-After")
                wait = float(retry_after) if (retry_after or "").isdigit() else 45 * (i + 1)
                time.sleep(min(300.0, wait))
                continue
            if r.status_code in (500, 502, 503, 504):
                time.sleep(5 * (i + 1))
                continue
        except requests.RequestException:
            pass
        time.sleep(2.0 + i)
    return None


# --------------------------------------------------------------------------- #
# Reference data (states, commodities) — fetched once, cached to disk
# --------------------------------------------------------------------------- #

def load_ref(force: bool = False) -> dict:
    if REF_CACHE.exists() and not force:
        try:
            return json.loads(REF_CACHE.read_text())
        except json.JSONDecodeError:
            pass

    states: List[dict] = []
    data = _get(f"{BASE}/location/state", {"page_size": 100})
    if data:
        for s in data.get("states", []):
            states.append({
                "id": s["id"],
                "name": (s.get("state_name") or "").strip(),
                "districts": [{"id": d["id"], "name": (d.get("district_name") or "").strip()}
                              for d in s.get("districts", [])],
            })

    commodities: List[dict] = []
    for page in (1, 2):
        data = _get(f"{BASE}/commodities", {"page": page, "page_size": 500})
        if not data:
            continue
        for c in data.get("data", []):
            commodities.append({
                "id": c["id"],
                "name": (c.get("cmdt_name") or "").strip(),
                "group": c.get("cmdt_group"),
            })
        if not data.get("pagination", {}).get("next_page"):
            break

    if not states or not commodities:
        raise SystemExit("AGMARKNET reference data unavailable — try again later")

    ref = {"states": states, "commodities": commodities, "fetched_at": date_cls.today().isoformat()}
    REF_CACHE.parent.mkdir(parents=True, exist_ok=True)
    REF_CACHE.write_text(json.dumps(ref))
    return ref


def state_id(ref: dict, name: str) -> Optional[int]:
    key = name.strip().lower()
    for s in ref["states"]:
        if s["name"].lower() == key:
            return s["id"]
    # a few spellings differ between the app catalogue and AGMARKNET
    aliases = {"chhattisgarh": "chattisgarh", "delhi": "nct of delhi",
               "andaman and nicobar islands": "andaman and nicobar",
               "dadra and nagar haveli and daman and diu": "dadra and nagar haveli",
               "puducherry": "pondicherry", "uttarakhand": "uttrakhand"}
    want = aliases.get(key, key)
    for s in ref["states"]:
        if s["name"].lower() == want:
            return s["id"]
    return None


# app crop name -> AGMARKNET commodity name, where they differ
CROP_ALIASES = {
    "soybean": "Soyabean", "soya bean": "Soyabean", "corn": "Maize",
    "paddy": "Paddy(Dhan)(Common)", "tur": "Arhar (Tur/Red Gram)(Whole)",
    "arhar": "Arhar (Tur/Red Gram)(Whole)", "arhar/tur": "Arhar (Tur/Red Gram)(Whole)",
    "gram": "Bengal Gram(Gram)(Whole)", "chickpea": "Bengal Gram(Gram)(Whole)",
    "chana": "Bengal Gram(Gram)(Whole)",
    "moong": "Green Gram (Moong)(Whole)",
    "urad": "Black Gram (Urd Beans)(Whole)",
    "green chilli": "Green Chilli", "chilli": "Green Chilli",
    "brinjal": "Brinjal", "eggplant": "Brinjal",
    "lady finger": "Bhindi(Ladies Finger)", "okra": "Bhindi(Ladies Finger)",
    "bottle gourd": "Bottle gourd", "bitter gourd": "Bitter gourd",
    "sugarcane": "Sugarcane", "mustard": "Mustard",
}


def _squash(s: str) -> str:
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def commodity_id(ref: dict, name: str) -> Optional[int]:
    key = name.strip().lower()
    wanted = {key}
    if key in CROP_ALIASES:
        wanted.add(CROP_ALIASES[key].lower())
    for c in ref["commodities"]:
        if c["name"].lower() in wanted:
            return c["id"]
    # tolerate spelling/punctuation drift: "Soyabean" vs "soybean"
    sq = {_squash(w) for w in wanted}
    for c in ref["commodities"]:
        if _squash(c["name"]) in sq:
            return c["id"]
    for c in ref["commodities"]:
        cn = c["name"].lower()
        if any(cn.startswith(w) for w in wanted if len(w) > 4):
            return c["id"]
    return None


# --------------------------------------------------------------------------- #
# Report fetch + parse
# --------------------------------------------------------------------------- #

def fetch_month(state: int, commodity: int, year: int, month: int) -> List[dict]:
    payload = _get(REPORT, {
        "report_mode": "Districtwise",
        "state": state,
        "commodity": commodity,
        "year": year,
        "month": month,
    })
    if not payload or not payload.get("success"):
        return []
    return payload.get("rows") or []


def parse_rows(rows: Iterable[dict], month: int, year: int) -> List[Tuple[str, int, int, float]]:
    """Turn one report response into (district, year, month, price) tuples.

    The report labels its columns per month (`prices_october_2026`), so the
    same response yields the requested month, the previous month and the same
    month a year earlier. All three are kept.
    """
    out: List[Tuple[str, int, int, float]] = []
    for row in rows:
        district = (row.get("district") or "").strip()
        if not district or district.lower() == "average":
            continue
        for m in range(1, 13):
            for y in (year, year - 1):
                value = row.get(f"prices_{MONTHS[m - 1]}_{y}")
                try:
                    price = float(value)
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    out.append((district, y, m, price))
    return out


def ingest(state_name: str, sid: int, crop: str, cid: int, months: Sequence[Tuple[int, int]],
           dry_run: bool = False, delay: float = 0.25,
           skip_present: bool = True) -> int:
    """Fetch the (year, month) pairs for one state+crop and store the averages.

    One response already carries three months (requested, previous, same month
    last year), so a pair of (year, month) is skipped as soon as an earlier
    response covered it. That turns ~13 requests into two years of history.
    """
    covered: set = set()
    if skip_present and not dry_run:
        covered = price_store.monthly_months_present(state_name, crop)
    written = 0
    seen: set = set()
    for year, month in months:
        if (year, month) in covered:
            continue
        rows = fetch_month(sid, cid, year, month)
        if not rows:
            continue
        parsed = parse_rows(rows, month, year)
        covered.update({(y, m) for _d, y, m, _p in parsed})
        payload = []
        for district, y, m, price in parsed:
            key = (district.lower(), y, m)
            if key in seen:
                continue
            seen.add(key)
            payload.append({"state": state_name, "district": district,
                            "commodity": crop, "year": y, "month": m,
                            "price": price, "source": "agmarknet_monthly"})
        if payload and not dry_run:
            written += price_store.monthly_upsert_many(payload)
        elif payload:
            written += len(payload)
        time.sleep(delay)
    return written


def months_window(years: Sequence[int]) -> List[Tuple[int, int]]:
    """(year, month) pairs to request.

    Each request returns three months (this one, the previous one, and the same
    month a year earlier), so one year of requests already yields two years of
    averages. Months that have not happened yet are skipped — AGMARKNET would
    just return an empty table for them.
    """
    today = date_cls.today()
    out: List[Tuple[int, int]] = []
    for year in sorted(years, reverse=True):
        last_month = 12 if year < today.year else today.month
        # newest first: recent months matter most and land in the store first
        for month in range(last_month, 0, -1):
            out.append((year, month))
    if out:
        # Every response returns three months (this one, the previous one, and
        # the same month a year earlier). The only month that never appears is
        # the December just before the earliest requested year, so ask for it
        # explicitly and the window covers a full 24 months.
        first_year = min(y for y, _m in out)
        if (first_year - 1, 12) not in out:
            out.append((first_year - 1, 12))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill AGMARKNET district monthly averages")
    ap.add_argument("--states", default="all", help="'all' or comma-separated state names")
    ap.add_argument("--commodities", default="major", help="'major' or comma-separated crop names")
    ap.add_argument("--years", nargs="+", type=int,
                    default=[date_cls.today().year],
                    help="years to request (default: current year; each response "
                         "also returns the previous month and the same month a "
                         "year earlier, so this already yields 2 years)")
    ap.add_argument("--delay", type=float, default=0.1, help="seconds between requests")
    ap.add_argument("--workers", type=int, default=5,
                    help="concurrent state/crop pairs (politeness: keep it small)")
    ap.add_argument("--refresh", action="store_true", help="refetch months already stored")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-ref", action="store_true", help="refresh the state/commodity cache")
    args = ap.parse_args(argv)

    ref = load_ref(force=args.force_ref)

    if args.states.strip().lower() == "all":
        states = [s["name"] for s in ref["states"]]
    else:
        states = [s.strip() for s in args.states.split(",") if s.strip()]

    crops = MAJOR_CROPS if args.commodities.strip().lower() == "major" \
        else [c.strip() for c in args.commodities.split(",") if c.strip()]

    months = months_window(args.years)
    t0 = time.time()
    lock = threading.Lock()

    jobs: List[Tuple[str, int, str, int]] = []
    for state_name in states:
        sid = state_id(ref, state_name)
        if not sid:
            print(f"skip state (unknown to AGMARKNET): {state_name}", file=sys.stderr)
            continue
        for crop in crops:
            cid = commodity_id(ref, crop)
            if not cid:
                print(f"skip crop (unknown to AGMARKNET): {crop}", file=sys.stderr)
                continue
            jobs.append((state_name, sid, crop, cid))

    total = 0
    pairs = 0
    done = 0

    def run(job: Tuple[str, int, str, int]) -> int:
        state_name, sid, crop, cid = job
        return ingest(state_name, sid, crop, cid, months,
                      dry_run=args.dry_run, delay=args.delay,
                      skip_present=not args.refresh)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(run, j): j for j in jobs}
        for fut in as_completed(futures):
            state_name, _sid, crop, _cid = futures[fut]
            n = fut.result()
            with lock:
                pairs += 1
                done += n
                total += n
                print(f"{state_name:20} {crop:16} {n:5} rows  "
                      f"[{pairs}/{len(jobs)} pairs, {done} rows, {time.time() - t0:.0f}s]",
                      flush=True)

    print(f"\n{'would write' if args.dry_run else 'wrote'} {total} monthly rows "
          f"for {pairs} state/crop pairs")
    print("store coverage:", price_store.monthly_coverage())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
