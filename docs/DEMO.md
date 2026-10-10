# DEMO — 3-minute walkthrough (synthetic mini city)

Setup: `uv run poe pipeline-mini`, `uv run poe api`, `npm run dev`. Open http://localhost:3000.

| Time | Show | Say |
|---|---|---|
| 0:00 | Heat map, legend, LST note | Problem: cities don't know which roofs to cool first; households can't tell if solar pays. Landsat surface temperature, ΔLST vs rural reference. |
| 0:25 | Click the top ward (W07) | Rank with a **rank range** from 1,000 weight draws, hover a number → source/date/resolution badge. |
| 0:50 | Heat type + brief, recommendations | Rule-based types, each recommendation cites evidence and its grade; "not evaluated" lists missing data. |
| 1:10 | Top roofs, "cost not available" | We refuse to invent coating cost; benefit ranges (people protected) are shown. Heat-dome signal banner = *forecast signal, not an official warning*. |
| 1:35 | Rooftop solar tab → Check | 70 m², 400 units, ₹1.8 lakh → 3 kW, **₹78,000** subsidy (policy version + hash), payback **range**, synthetic-tariff warning. |
| 2:00 | Switch to हिं, open Assistant | Ask in Hindi; the answer's numbers are grounded in tool results; asking to "submit" or for medical advice is refused. |
| 2:25 | Download PDF | Bilingual PDF: "assistance summary — not the official application". |
| 2:40 | AWS slide | Strands Agents + Bedrock (agent), Lambda + API Gateway, S3 + DynamoDB (data), CDK. Local-first: same code, `RUNTIME=aws`. |

Declare: coefficients and cost are placeholders; the tariff is synthetic; nothing is validated against ground truth.
