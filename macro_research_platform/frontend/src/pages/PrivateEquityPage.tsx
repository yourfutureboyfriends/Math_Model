/**
 * PE — the private-equity area (top-bar mode 'pe'). Home of the LBO deal workbench: a buyout model for a listed
 * company (inputs filled from its filings) or a private one (typed in) — financing at live SOFR and high-yield
 * spreads, base / upside / downside cases, debt paydown, exit, IRR and money multiple, and the highest price that
 * still clears the hurdle. Modelled returns are analysis, never a track record.
 */
import { Briefcase, Calculator, FileSpreadsheet, Landmark, LineChart, Target } from 'lucide-react';

const PLAN = [
  { icon: Target, title: 'Target', text: 'Any listed company fills in its revenue, EBITDA, margins, capex, working capital, tax and net debt; a private one is typed in. Entry at a take-private premium, shown as an EBITDA multiple.' },
  { icon: Landmark, title: 'Financing', text: 'Senior loan at live SOFR plus a market spread, high-yield notes off the live high-yield index, equity for the rest. Leverage capped by interest cover.' },
  { icon: LineChart, title: 'Operating cases', text: 'Base, upside and downside: revenue growth, margins and capex. Free cash flow pays the debt down each year.' },
  { icon: Calculator, title: 'Returns', text: 'IRR and money multiple per case, the value-creation bridge (earnings growth, multiple, deleveraging), leverage and cover checks — and the highest price that still clears the hurdle.' },
  { icon: FileSpreadsheet, title: 'Outputs', text: 'Saved deals in the fund’s database and an Excel model for an investment-committee memo.' },
];

export function PrivateEquityPage() {
  return (
    <div className="p-4 space-y-3 max-w-5xl">
      <div className="terminal-section">
        <div className="section-header">
          <div className="section-header-left">
            <span className="section-tag"><Briefcase className="w-3 h-3" /></span>
            <h2 className="section-title">Private equity</h2>
            <span className="section-meta">LBO deal workbench</span>
          </div>
        </div>
        <div className="p-4">
          <p className="text-sm text-text-secondary max-w-3xl leading-relaxed">
            Evaluate a buyout: what it costs, how it is financed, what it returns under different cases, and the most you
            could pay and still clear the hurdle. Free data only — company filings, Yahoo Finance and FRED.
          </p>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {PLAN.map(({ icon: Icon, title, text }) => (
              <div key={title} className="p-4 bg-surface-1 border border-border rounded-xl">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-bloomberg/10 text-bloomberg"><Icon className="w-3.5 h-3.5" /></span>
                  <span className="text-[13px] font-semibold text-text-primary">{title}</span>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed">{text}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 text-[11px] text-text-tertiary">
            The workbench is being built here. Modelled deal returns are analysis — never a fund track record.
          </div>
        </div>
      </div>
    </div>
  );
}
