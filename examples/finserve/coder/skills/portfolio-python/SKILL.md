---
name: portfolio-python
description: Load tenant portfolio rows then run pandas/numpy in execute().
---

# Portfolio Python

1. Query `portfolios` for the authenticated tenant. `holdings` is JSONB `{ticker: weight}`. `balance` is the account value.
2. Copy those numbers into the `execute()` script. Files written with `write_file` are in-memory on the agent and are not visible to `execute()`.
3. Workers have `pandas` and `numpy`. Example:

```python
execute(command="""python - <<'PY'
import pandas as pd
rows = [
    {"account": "ACC-ALPHA-001", "balance": 250000.0, "holdings": {"AAPL": 40, "MSFT": 30, "GOOGL": 30}},
]
df = pd.DataFrame(rows)
print(df["balance"].sum())
PY""")
```

Replace the example rows with the SQL result. Never paste another tenant's accounts.
