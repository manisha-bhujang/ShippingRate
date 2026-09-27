# 🚚 Shipping Cost Comparison Tool

A Streamlit app that compares shipping costs across carriers and modes (truck, rail, intermodal, air) for a chosen route, shipment weight, and fuel surcharge.

## Files

| File | What it is |
|---|---|
| `app.py` | The Streamlit app |
| `shipping_rates.csv` | Sample dataset: 7 US cities, 42 routes, 6 carriers (252 rows) |
| `requirements.txt` | Libraries Streamlit Community Cloud installs when you deploy |

## Dataset columns

| Column | Meaning |
|---|---|
| `origin`, `destination` | Route endpoints |
| `distance_miles` | Route distance |
| `carrier`, `mode` | Carrier name and mode (Truck, Rail, Intermodal, Air) |
| `base_fee_usd` | Flat fee per shipment |
| `rate_per_lb_per_100mi` | Price per pound per 100 miles |
| `fuel_sensitivity` | How strongly the fuel surcharge hits this mode (air 1.5–1.6, truck 1.0, rail 0.4) |
| `min_weight_lbs` | Minimum shipment the carrier accepts (rail 500, intermodal 300) |
| `transit_days` | Delivery time |
| `on_time_pct` | Historical on-time rate |

Carrier names and rates are fictional, generated for teaching.

**Cost formula**

```
linehaul = rate_per_lb_per_100mi × weight × distance / 100
fuel     = linehaul × fuel_surcharge% × fuel_sensitivity
total    = base_fee + linehaul + fuel
```

## Run locally in VS Code

1. Open this folder in VS Code (**File → Open Folder**).
2. Open a terminal (**Terminal → New Terminal**) and create a virtual environment:
   ```bash
   python -m venv .venv
   # Windows:   .venv\Scripts\activate
   # Mac/Linux: source .venv/bin/activate
   ```
3. Install the libraries:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the app:
   ```bash
   streamlit run app.py
   ```
   Your browser opens at `http://localhost:8501`. Edit `app.py`, save, and the app reloads.

## Deploy to Streamlit Community Cloud

1. Create a new public GitHub repository and upload `app.py`, `shipping_rates.csv`, and `requirements.txt` (don't upload `.venv`).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, and click **Create app**.
3. Pick your repository, branch `main`, main file `app.py`, then **Deploy**.
4. You get a public link to share. Every push to GitHub updates the live app.
