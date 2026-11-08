# Fund Classification Architecture & Coverage

## Overview
FolioPilot classifies mutual funds and ETFs imported from AMFI's master feed into canonical asset classes and subcategories. This taxonomy powers asset allocation tracking, portfolio rebalancing, and fund discovery.

## Canonical Classifications
Every classified fund maps to a canonical `(asset_class, sub_category)` tuple defined in `CANONICAL_CLASSIFICATIONS`:

### Asset Classes
- **equity**: `large-cap`, `mid-cap`, `small-cap`, `large-and-mid-cap`, `multi-cap`, `flexi-cap`, `focused`, `value-contra`, `elss`, `dividend-yield`, `sectoral-thematic`, `index`, `equity-etf`, `international`
- **debt**: `overnight`, `liquid`, `ultra-short`, `low-duration`, `money-market`, `short-duration`, `medium-duration`, `medium-to-long`, `long-duration`, `dynamic-bond`, `corporate-bond`, `credit-risk`, `banking-psu`, `gilt`, `gilt-10yr`, `floater`, `index-debt`, `debt-etf`
- **hybrid**: `conservative-hybrid`, `balanced-hybrid`, `aggressive-hybrid`, `dynamic-asset-allocation`, `multi-asset`, `arbitrage`, `equity-savings`
- **gold**: `gold-etf`, `gold-fof`
- **other**: `fof-overseas`, `fof-domestic`, `silver`, `other-etf`, `unknown`

## Ambiguous Category Resolution Rules
For ambiguous AMFI categories (`Other Schemes - Index Funds`, `Other Schemes - Other ETFs`, `Other Schemes - FoF Overseas`, etc.), a strict 4-level precedence is applied to scheme names:
1. **Debt keywords**: Names containing `gilt`, `bond`, `liquid`, `psu`, `sdl`, `treasury`, `constant maturity`, `target maturity`, `nifty g-sec`, `bharat bond`, etc. map to `debt/index-debt` or `debt/debt-etf`.
2. **Precious Metals**: Names containing `gold` map to `gold/gold-etf` (or `gold/gold-fof`); names containing `silver` map to `other/silver`.
3. **International**: Names containing `global`, `world`, `us`, `nasdaq`, `s&p 500`, `international`, `asia`, `china`, `taiwan`, `japan`, `europe`, `emerging markets`, `overseas`, `brazil` map to `equity/international` (or `other/fof-overseas` if FoF).
4. **Equity indices**: Names containing index indicators (`nifty`, `sensex`, `bse`, `index`, `equal weight`, `momentum`, `low volatility`, `alpha`, `quality`, `midcap`, `smallcap`, `microcap`, `top 100`, `next 50`) map to `equity/index` (or `equity/equity-etf`).

### Category Override Guard
AMFI category mapping is authoritative. A scheme classified by a standard category (e.g. `Growth/Equity Schemes`) is never overridden by scheme name keywords. Category-unmapped schemes fallback to `other/unknown` if neither category nor name matches any known pattern (e.g. fund 148558).

## Reclassification Distribution (Real Database Verification)
On the live database of 14,441 mutual fund and ETF schemes:

| Asset Class | Before Reclassification | After Reclassification | Delta |
| :--- | :--- | :--- | :--- |
| **debt** | 8,325 | 8,416 | +91 |
| **equity** | 3,576 | 3,962 | +386 |
| **hybrid** | 1,040 | 1,052 | +12 |
| **other** | 1,474 | 986 | -488 |
| **gold** | 26 | 25 | -1 |
| *Total* | *14,441* | *14,441* | *0* |

### Unknown Reductions
- `other/unknown` dropped from **527 funds** down to **29 funds** (a 94.5% reduction).
- The remaining 29 unclassified schemes represent bespoke, ill-formed, or closed-ended legacy instruments where AMFI metadata provides no recognizable index or asset category.
