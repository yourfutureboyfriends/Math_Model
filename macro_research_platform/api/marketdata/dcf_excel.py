"""
DCF → Excel: the same FCFF model as dcf.value(), written as live formulas so the user can
change any input in Excel and watch the value update. Inputs (blue) on one sheet, the
projection, terminal value and equity bridge as formulas on the other.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

BLUE = Font(color="1F4E9E")
BOLD = Font(bold=True)
HEAD = PatternFill("solid", fgColor="1F1F1F")
HEAD_FONT = Font(bold=True, color="FFA028")
PCT, NUM, X = "0.00%", "#,##0", "0.00"


def build(inp: Dict[str, Any], val: Dict[str, Any]) -> Tuple[bytes, Dict[str, str]]:
    """Returns the .xlsx bytes and a map {name: formula} for the key outputs (used in tests)."""
    a, w = val["assumptions"], val["wacc"]
    N, hg = int(a["years"]), int(a["high_growth_years"])
    half = "0.5" if a.get("mid_year", True) else "1"          # mid-year or end-of-year discounting
    wb = Workbook()
    ws = wb.active
    ws.title = "Inputs"
    ws["A1"], ws["A1"].font = f"DCF — {inp.get('name') or inp['symbol']} ({inp['symbol']})", Font(bold=True, size=13)
    ws["A2"] = f"Reporting currency {inp.get('currency')} · values in units of that currency · blue cells are inputs"
    rows: List[Tuple[str, str, Any, str]] = [
        # key, label, value, number format
        ("rev0", "Revenue, last 12 months", inp["revenue"], NUM),
        ("m0", "Operating margin today", a["margin_now"], PCT),
        ("mT", "Target operating margin (year N)", a["target_margin"], PCT),
        ("g1", "Revenue growth, year 1", a["growth_y1"], PCT),
        ("g0", f"Revenue growth, years 2–{hg}", a["growth"], PCT),
        ("gT", "Terminal growth", a["terminal_growth"], PCT),
        ("t0", "Tax rate today", a["tax_now"], PCT),
        ("tT", "Tax rate, terminal", a["tax_terminal"], PCT),
        ("stc", "Sales-to-capital", a["sales_to_capital"], X),
        ("ronic", "Return on new capital (terminal)", a["ronic"], PCT),
        ("r", "WACC today", a["discount"], PCT),
        ("rT", "WACC in stable growth", a["discount_terminal"], PCT),
        ("debt", "Debt" + (" incl. leases" if a.get("include_leases") else ""), -val["bridge"]["debt"], NUM),
        ("cash", "Cash & short-term investments", val["bridge"]["cash"], NUM),
        ("inv", "Stakes in other companies", val["bridge"]["investments"], NUM),
        ("mi", "Minority interest", -val["bridge"]["minority_interest"], NUM),
        ("shares", "Diluted shares", inp["shares"], NUM),
        ("price", f"Share price ({inp.get('price_currency')})", inp.get("price"), "#,##0.00"),
    ]
    ref: Dict[str, str] = {}
    for i, (k, label, v, fmt) in enumerate(rows, start=4):
        ws.cell(i, 1, label)
        c = ws.cell(i, 2, v)
        c.font, c.number_format = BLUE, fmt
        ref[k] = f"Inputs!$B${i}"
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 38, 18
    note = 4 + len(rows) + 1
    ws.cell(note, 1, "Sources and method").font = BOLD
    for j, line in enumerate([
        f"Financials: {inp.get('source')}", f"Risk-free: {inp.get('risk_free_source')}", f"ERP: {inp.get('erp_source')}",
        f"Beta: {inp.get('beta_source')}", "FCFF = NOPAT − reinvestment (Δrevenue ÷ sales-to-capital), mid-year discounting.",
        "Terminal value = NOPAT(N+1) × (1 − g ÷ RONIC) ÷ (WACC_stable − g) (value-driver formula).",
        "Growth: year 1, then years 2–%d at the second rate, then a linear fade to terminal growth by year %d." % (hg, N),
        "WACC moves linearly from today's to the stable-growth rate over the fade years."]):
        ws.cell(note + 1 + j, 1, line)

    m = wb.create_sheet("Model")
    m["A1"], m["A1"].font = "Projection (formulas — edit the Inputs sheet)", Font(bold=True, size=13)
    labels = ["Year", "Revenue growth", "Revenue", "Operating margin", "EBIT", "Tax rate", "NOPAT", "Reinvestment",
              "FCFF", "Discount rate", "Discount factor (end of year)", "Discount factor (mid-year)", "PV of FCFF"]
    R = {lab: 3 + i for i, lab in enumerate(labels)}
    for lab, row in R.items():
        m.cell(row, 1, lab).font = BOLD if lab in ("Year", "FCFF", "PV of FCFF") else Font()
    m.cell(R["Year"], 2, 0)
    m.cell(R["Revenue"], 2, f"={ref['rev0']}")
    m.cell(R["Discount factor (end of year)"], 2, 1)
    for y in range(1, N + 1):
        col, prev = get_column_letter(2 + y), get_column_letter(1 + y)
        c = lambda lab: f"{col}{R[lab]}"
        p = lambda lab: f"{prev}{R[lab]}"
        if y == 1:
            g = f"={ref['g1']}"
        elif y <= hg:
            g = f"={ref['g0']}"
        else:
            g = f"={ref['g0']}+({ref['gT']}-{ref['g0']})*{y - hg}/{N - hg}"
        r_y = f"={ref['r']}" if y <= hg else f"={ref['r']}+({ref['rT']}-{ref['r']})*{y - hg}/{N - hg}"
        cells = {
            "Year": y, "Revenue growth": g, "Revenue": f"={p('Revenue')}*(1+{c('Revenue growth')})",
            "Operating margin": f"={ref['m0']}+({ref['mT']}-{ref['m0']})*{y}/{N}",
            "EBIT": f"={c('Revenue')}*{c('Operating margin')}",
            "Tax rate": f"={ref['t0']}+({ref['tT']}-{ref['t0']})*{y}/{N}",
            # no tax shield on operating losses, as in the app's model
            "NOPAT": f"=IF({c('EBIT')}>0,{c('EBIT')}*(1-{c('Tax rate')}),{c('EBIT')})",
            "Reinvestment": f"=({c('Revenue')}-{p('Revenue')})/{ref['stc']}",
            "FCFF": f"={c('NOPAT')}-{c('Reinvestment')}",
            "Discount rate": r_y,
            "Discount factor (end of year)": f"={p('Discount factor (end of year)')}/(1+{c('Discount rate')})",
            "Discount factor (mid-year)": f"={p('Discount factor (end of year)')}/(1+{c('Discount rate')})^{half}",
            "PV of FCFF": f"={c('FCFF')}*{c('Discount factor (mid-year)')}",
        }
        for lab, v in cells.items():
            cell = m.cell(R[lab], 2 + y, v)
            cell.number_format = PCT if lab in ("Revenue growth", "Operating margin", "Tax rate", "Discount rate") else \
                ("0.0000" if lab.startswith("Discount factor") else ("0" if lab == "Year" else NUM))
    last = get_column_letter(2 + N)
    first = get_column_letter(3)
    out_row = R["PV of FCFF"] + 2
    outs = [
        ("PV of explicit cash flows", f"=SUM({first}{R['PV of FCFF']}:{last}{R['PV of FCFF']})", NUM),
        ("NOPAT in year N+1", f"={last}{R['Revenue']}*(1+{ref['gT']})*{ref['mT']}*(1-{ref['tT']})", NUM),
        ("Terminal FCFF (after reinvestment g ÷ RONIC)", None, NUM),
        ("Terminal value at year N", None, NUM),
        ("PV of terminal value", None, NUM),
        ("Enterprise value", None, NUM),
        ("Equity value", None, NUM),
        ("Value per share (reporting currency)", None, "#,##0.00"),
        ("Upside vs price (same currency only)", None, PCT),
    ]
    rr = {lab: out_row + i for i, (lab, _, _) in enumerate(outs)}
    B = lambda lab: f"B{rr[lab]}"
    formulas = {
        "PV of explicit cash flows": outs[0][1], "NOPAT in year N+1": outs[1][1],
        "Terminal FCFF (after reinvestment g ÷ RONIC)": f"={B('NOPAT in year N+1')}*(1-{ref['gT']}/{ref['ronic']})",
        "Terminal value at year N": f"={B('Terminal FCFF (after reinvestment g ÷ RONIC)')}/({ref['rT']}-{ref['gT']})",
        "PV of terminal value": f"={B('Terminal value at year N')}*{last}{R['Discount factor (end of year)']}*(1+{ref['rT']})^{'0.5' if half == '0.5' else '0'}",
        "Enterprise value": f"={B('PV of explicit cash flows')}+{B('PV of terminal value')}",
        "Equity value": f"=MAX(0,{B('Enterprise value')}-{ref['debt']}+{ref['cash']}+{ref['inv']}-{ref['mi']})",
        "Value per share (reporting currency)": f"={B('Equity value')}/{ref['shares']}",
        "Upside vs price (same currency only)": f"={B('Value per share (reporting currency)')}/{ref['price']}-1",
    }
    for lab, _, fmt in outs:
        m.cell(rr[lab], 1, lab).font = BOLD if lab in ("Enterprise value", "Equity value", "Value per share (reporting currency)") else Font()
        cell = m.cell(rr[lab], 2, formulas[lab])
        cell.number_format = fmt
    if inp.get("currency") != inp.get("price_currency"):
        m.cell(rr["Upside vs price (same currency only)"] + 1, 1,
               f"Note: financials are in {inp.get('currency')} but the shares trade in {inp.get('price_currency')} — convert before comparing.")
    m.column_dimensions["A"].width = 44
    for y in range(0, N + 2):
        m.column_dimensions[get_column_letter(2 + y)].width = 14
    for sheet in (ws, m):
        sheet.freeze_panes = "B4" if sheet is m else None
    m["A2"] = "Same model as the terminal's DCF screen; the numbers recalculate when Inputs change."
    m["A2"].alignment = Alignment(wrap_text=False)
    buf = io.BytesIO()
    wb.save(buf)
    key_cells = {"per_share": f"Model!B{rr['Value per share (reporting currency)']}", "ev": f"Model!B{rr['Enterprise value']}"}
    return buf.getvalue(), key_cells
