#!/usr/bin/env python3
import re, ast, sys
from statistics import mean

def parse_text(text: str):
    data = {}

    # --- Categories by ORDER of appearance (ignore the printed category number) ---
    cat_lines = [float(m.group(1)) for m in re.finditer(
        r"Category:\s*\d+\s+Percentage:\s*([0-9]+(?:\.[0-9]+)?)", text)]
    if cat_lines:
        data['category_percentages'] = cat_lines
    else:
        m = re.search(r"Category percentages:\s*\[([^\]]+)\]", text)
        data['category_percentages'] = [float(x.strip()) for x in m.group(1).split(",")] if m else []

    # Total URLs (may be absent)
    m = re.search(r"Total number of URLs:\s*([0-9,]+)", text)
    data['total_urls'] = int(m.group(1).replace(",", "")) if m else None

    # Intersection set
    m = re.search(r"Intersection of the associated system call numbers.*:\s*({[^}]+})", text)
    if m:
        try:
            data['intersection'] = ast.literal_eval(m.group(1))
        except Exception:
            data['intersection'] = set(int(x) for x in re.findall(r"\d+", m.group(1)))
    else:
        data['intersection'] = None

    # Overall SP/SN (fallbacks)
    m_sp = re.search(r"SP%[:\s]+([0-9]+(?:\.[0-9]+)?)", text)
    m_sn = re.search(r"SN%[:\s]+([0-9]+(?:\.[0-9]+)?)", text)
    data['overall_SP'] = float(m_sp.group(1)) if m_sp else None
    data['overall_SN'] = float(m_sn.group(1)) if m_sn else None

    # Clusters (SP/SN/deltas + url counts if present)
    clusters = {}
    for m in re.finditer(r"Cluster\s+(\d+):\s+([0-9,]+)\s+urls", text):
        cid = int(m.group(1))
        clusters.setdefault(cid, {})['urls'] = int(m.group(2).replace(",", ""))

    for m in re.finditer(r"Cluster\s+(\d+)\s*SP%:\s*([0-9.]+)", text):
        clusters.setdefault(int(m.group(1)), {})['SP'] = float(m.group(2))

    for m in re.finditer(r"Security Metric for Cluster\s+(\d+)\(SN%\):\s*([0-9.]+)", text):
        clusters.setdefault(int(m.group(1)), {})['SN'] = float(m.group(2))

    for m in re.finditer(
        r"Cluster\s+(\d+):.*Max syscalls to add to any set:\s*([0-9.]+)%.*Max of sensitive syscalls:\s*([0-9.]+)%",
        text):
        cid = int(m.group(1))
        clusters.setdefault(cid, {})['delta_SP'] = float(m.group(2))
        clusters.setdefault(cid, {})['delta_SN'] = float(m.group(3))

    data['clusters'] = clusters
    data['cluster_count'] = len(clusters)
    if data['total_urls'] is None:
        total = sum(v.get('urls', 0) for v in clusters.values())
        data['total_urls'] = total if total > 0 else None

    # --- NEW: Ordered URL % list from "Cluster URL Percentage: X" lines (ignore preceding 'Cluster: n') ---
    data['cluster_url_pct_by_index'] = [
        float(m.group(1)) for m in re.finditer(r"Cluster\s*URL\s*Percentage:\s*([0-9]+(?:\.[0-9]+)?)", text)
    ]

    return data

def format_outputs(parsed):
    lines_latex, lines_md, numeric_rows = [], [], []

    cat_perc = parsed.get('category_percentages', [])
    clusters = parsed.get('clusters', {})
    url_pct_seq = parsed.get('cluster_url_pct_by_index', [])
    total_urls = parsed.get('total_urls')

    overall_SP = parsed.get('overall_SP') or 0.0
    overall_SN = parsed.get('overall_SN') or 0.0

    # Cat0/Cat1 SP/SN from Cluster 0/1 (fallback to overall)
    cat0_SP = clusters.get(0, {}).get('SP', overall_SP)
    cat0_SN = clusters.get(0, {}).get('SN', overall_SN)
    cat1_SP = clusters.get(1, {}).get('SP', overall_SP)
    cat1_SN = clusters.get(1, {}).get('SN', overall_SN)

    # Helper: URL % for cluster k by order-of-appearance list (else compute, else 0)
    def pct_for_cluster(k: int) -> float:
        if k < len(url_pct_seq):
            return url_pct_seq[k]
        # fallback to compute from urls
        c = clusters.get(k, {})
        if total_urls and c.get('urls'):
            return 100.0 * c['urls'] / total_urls
        return 0.0

    # Markdown header
    lines_md += [
        "| Script/Cluster | % | SP% | SN% | ΔSP | ΔSN |",
        "|----------------|---|-----|-----|-----|-----|",
    ]

    # Category 0 (use ordered category percentages index 0)
    if len(cat_perc) >= 1:
        perc0 = round(cat_perc[0], 2)
        lines_latex.append(
            rf"\textsf{{Category 0 ({perc0:.2f}\%)}} & \textsf{{{cat0_SP:.2f}}} & \textsf{{{cat0_SN:.2f}}} & \textsf{{0.00}} & \textsf{{0.00}} \\"
        )
        lines_md.append(f"| Category 0 | {perc0:.2f}% | {cat0_SP:.2f} | {cat0_SN:.2f} | 0.00 | 0.00 |")
        numeric_rows.append({"percent": perc0, "sp": cat0_SP, "sn": cat0_SN, "dsp": 0.0, "dsn": 0.0})

    # Category 1 (use ordered category percentages index 1)
    if len(cat_perc) >= 2:
        perc1 = round(cat_perc[1], 2)
        lines_latex.append(
            rf"\textsf{{Category 1 ({perc1:.2f}\%)}} & \textsf{{{cat1_SP:.2f}}} & \textsf{{{cat1_SN:.2f}}} & \textsf{{0.00}} & \textsf{{0.00}} \\"
        )
        lines_md.append(f"| Category 1 | {perc1:.2f}% | {cat1_SP:.2f} | {cat1_SN:.2f} | 0.00 | 0.00 |")
        numeric_rows.append({"percent": perc1, "sp": cat1_SP, "sn": cat1_SN, "dsp": 0.0, "dsn": 0.0})

    # Remaining clusters: skip 0 and 1
    printed_any = False
    for cid in sorted(set(list(clusters.keys()) + list(range(len(url_pct_seq)) ))):
        if cid in (0, 1):
            continue
        c = clusters.get(cid, {})
        pct = pct_for_cluster(cid)
        sp = c.get('SP', overall_SP)
        sn = c.get('SN', overall_SN)
        dsp = c.get('delta_SP', 0.0)
        dsn = c.get('delta_SN', 0.0)

        lines_latex.append(
            rf"\textsf{{Cluster {cid} ({pct:.2f}\%)}} & \textsf{{{sp:.2f}}} & \textsf{{{sn:.2f}}} & \textsf{{{dsp:.2f}}} & \textsf{{{dsn:.2f}}} \\"
        )
        lines_md.append(f"| Cluster {cid} | {pct:.2f}% | {sp:.2f} | {sn:.2f} | {dsp:.2f} | {dsn:.2f} |")
        numeric_rows.append({"percent": pct, "sp": sp, "sn": sn, "dsp": dsp, "dsn": dsn})
        printed_any = True

    # Averages row
    if numeric_rows:
        avg_pct = mean(r["percent"] for r in numeric_rows)
        avg_sp  = mean(r["sp"] for r in numeric_rows)
        avg_sn  = mean(r["sn"] for r in numeric_rows)
        avg_dsp = mean(r["dsp"] for r in numeric_rows)
        avg_dsn = mean(r["dsn"] for r in numeric_rows)
        lines_latex.append(
            rf"\textsf{{Average ({avg_pct:.2f}\%)}} & \textsf{{{avg_sp:.2f}}} & \textsf{{{avg_sn:.2f}}} & \textsf{{{avg_dsp:.2f}}} & \textsf{{{avg_dsn:.2f}}} \\"
        )
        lines_md.append(f"| **Average** | **{avg_pct:.2f}%** | **{avg_sp:.2f}** | **{avg_sn:.2f}** | **{avg_dsp:.2f}** | **{avg_dsn:.2f}** |")

    return lines_latex, lines_md

def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        print("Paste or pipe the analysis text (end with EOF / Ctrl-D):", file=sys.stderr)
        text = sys.stdin.read()

    parsed = parse_text(text)
    latex, md = format_outputs(parsed)

    print("% --- LaTeX Rows ---")
    for r in latex: print(r)
    print("\n% --- Markdown Table ---")
    for r in md: print(r)

    print("\n% --- Extra Info ---")
    inter = parsed.get('intersection')
    if inter is not None:
        inter_sorted = sorted(inter)
        print("% Intersection set:", inter_sorted)
        print("% Intersection length:", len(inter_sorted))
    print("% Total clusters (with metrics seen):", parsed.get('cluster_count', 0))
    print("% Total URLs:", parsed.get('total_urls', 'unknown'))

if __name__ == "__main__":
    main()
