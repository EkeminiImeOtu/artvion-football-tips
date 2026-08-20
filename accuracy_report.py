"""
Prints a plain-terminal accuracy report straight from predictions.db.
No server needs to be running for this -- it reads the SQLite file directly.

Usage: python accuracy_report.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import build_stats, DB_PATH


def bar(pct, width=20):
    if pct is None:
        return '-' * width
    filled = round(width * pct / 100)
    return '#' * filled + '-' * (width - filled)


def print_section(title, groups):
    print(f"\n{title}")
    print("-" * len(title))
    if not groups:
        print("  (no data yet)")
        return
    for name, s in groups.items():
        wr = f"{s['win_rate']}%" if s['win_rate'] is not None else "n/a"
        print(f"  {name[:38]:<38} {s['total']:>4} picks  W{s['won']:>3} L{s['lost']:>3} P{s['pending']:>3}  {wr:>7}  [{bar(s['win_rate'])}]")


def main():
    if not os.path.exists(DB_PATH):
        print("No predictions.db found yet.")
        print("Run 'python server.py', open the app, and run a scan first -- picks get logged automatically.")
        return

    stats = build_stats()
    o = stats['overall']

    print("=" * 62)
    print("  SPORTYBET SCOUT -- ACCURACY REPORT")
    print("=" * 62)
    print(f"  Total picks logged : {o['total']}")
    print(f"  Resolved (W/L)     : {o['resolved']}  (Won {o['won']} / Lost {o['lost']})")
    print(f"  Pending            : {o['pending']}")
    win_rate_str = f"{o['win_rate']}%" if o['win_rate'] is not None else "n/a (nothing resolved yet)"
    print(f"  Win rate           : {win_rate_str}")
    roi_str = (f"{o['roi_pct']}% (on {o['staked_count']} priced picks)"
               if o['roi_pct'] is not None else "n/a (no priced picks resolved)")
    print(f"  ROI, flat 1u stake : {roi_str}")

    if o['resolved'] < 30:
        print(f"\n  Note: only {o['resolved']} resolved picks so far. Win rate / ROI at this")
        print(f"  sample size is noisy -- treat it as an early trend, not a verdict,")
        print(f"  until you have 50-100+ resolved picks.")

    print_section("BY MARKET", stats['by_market'])
    print_section("BY CONFIDENCE", stats['by_confidence'])
    print_section("BY LEAGUE (top 10)", dict(list(stats['by_league'].items())[:10]))
    print()
    print("Tip: pending picks only get resolved when you either re-scan their date range,")
    print("or click 'Resolve Pending Results' in the app's Track Record tab.")


if __name__ == '__main__':
    main()
