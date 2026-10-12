"""
Bike Store Sales Dashboard
Run:  streamlit run app.py
"""
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

st.set_page_config(page_title="Bike Store Dashboard", page_icon="🚲", layout="wide")


def get_config(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


DB_USER = get_config("DB_USER", "root")
DB_PASSWORD = get_config("DB_PASSWORD")
DB_HOST = get_config("DB_HOST", "localhost")
DB_PORT = get_config("DB_PORT", "3306")
DB_NAME = get_config("DB_NAME", "bike_store_db")


@st.cache_resource
def get_engine():
    url = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=int(DB_PORT),
        database=DB_NAME,
    )
    return create_engine(url, pool_pre_ping=True)


FACT_QUERY = """
SELECT
    o.order_id,
    o.order_date,
    p.product_id,
    p.product_name,
    b.brand_name,
    c.category_name,
    oi.quantity,
    oi.list_price,
    oi.discount,
    oi.quantity * oi.list_price                    AS sales_before_discount,
    oi.quantity * oi.list_price * (1 - oi.discount) AS net_sales
FROM order_items AS oi
INNER JOIN orders     AS o ON oi.order_id   = o.order_id
INNER JOIN products   AS p ON oi.product_id = p.product_id
INNER JOIN brands     AS b ON p.brand_id    = b.brand_id
INNER JOIN categories AS c ON p.category_id = c.category_id
"""

PRODUCTS_QUERY = """
SELECT p.product_id, p.product_name, b.brand_name, c.category_name,
       p.model_year, p.list_price
FROM products AS p
INNER JOIN brands AS b ON p.brand_id = b.brand_id
INNER JOIN categories AS c ON p.category_id = c.category_id
"""

TABLES = ["brands", "categories", "customers", "order_items", "orders",
          "products", "staffs", "stocks", "stores"]


@st.cache_data(ttl=600)
def load_sales() -> pd.DataFrame:
    df = pd.read_sql(text(FACT_QUERY), get_engine())
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["year"] = df["order_date"].dt.year
    df["month"] = df["order_date"].dt.to_period("M").dt.to_timestamp()
    for col in ["quantity", "list_price", "discount", "sales_before_discount", "net_sales"]:
        df[col] = pd.to_numeric(df[col])
    return df


@st.cache_data(ttl=600)
def load_products() -> pd.DataFrame:
    return pd.read_sql(text(PRODUCTS_QUERY), get_engine())


@st.cache_data(ttl=600)
def load_table_counts() -> pd.DataFrame:
    engine = get_engine()
    rows = []
    with engine.connect() as conn:
        for t in TABLES:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            rows.append({"table_name": t, "total_rows": n})
    return pd.DataFrame(rows)


try:
    sales = load_sales()
    products = load_products()
except Exception as e:
    st.error(f"Could not connect to the database: {e}")
    st.info("Check DB_USER / DB_PASSWORD / DB_HOST / DB_NAME at the top of app.py.")
    st.stop()


st.sidebar.title("🚲 Filters")
years = sorted(sales["year"].unique())
sel_years = st.sidebar.multiselect("Year", years, default=years)
brands = sorted(sales["brand_name"].unique())
sel_brands = st.sidebar.multiselect("Brand", brands, default=brands)
cats = sorted(sales["category_name"].unique())
sel_cats = st.sidebar.multiselect("Category", cats, default=cats)

df = sales[
    sales["year"].isin(sel_years)
    & sales["brand_name"].isin(sel_brands)
    & sales["category_name"].isin(sel_cats)
]

if df.empty:
    st.warning("No data for the selected filters.")
    st.stop()


# Header + KPIs

st.title("Bike Store Sales Dashboard")
st.caption("Source: MySQL · bike_store_db · net sales = quantity × list price × (1 − discount)")

total_orders = df["order_id"].nunique()
total_units = int(df["quantity"].sum())
gross = df["sales_before_discount"].sum()
net = df["net_sales"].sum()
discount_given = gross - net

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Net Sales", f"${net:,.0f}")
k2.metric("Orders", f"{total_orders:,}")
k3.metric("Units Sold", f"{total_units:,}")
k4.metric("Avg Order Value", f"${net / total_orders:,.0f}")
k5.metric("Discounts Given", f"${discount_given:,.0f}", f"{discount_given / gross:.1%} of gross", delta_color="off")

st.divider()


# Tabs

tab_trend, tab_brand, tab_product, tab_catalog, tab_data = st.tabs(
    ["📈 Sales Trends", "🏷️ Brands & Categories", "🏆 Top Products", "📦 Catalog Pricing", "🗄️ Data Overview"]
)

# Trends
with tab_trend:
    c1, c2 = st.columns([2, 1])

    monthly = (
        df.groupby("month")
        .agg(total_orders=("order_id", "nunique"),
             units_sold=("quantity", "sum"),
             total_sales=("net_sales", "sum"))
        .reset_index()
    )
    fig = px.line(monthly, x="month", y="total_sales", markers=True,
                  title="Monthly Net Sales",
                  labels={"month": "Month", "total_sales": "Net Sales ($)"})
    fig.update_layout(hovermode="x unified")
    c1.plotly_chart(fig, use_container_width=True)

    yearly = (
        df.groupby("year")
        .agg(total_orders=("order_id", "nunique"),
             units_sold=("quantity", "sum"),
             total_sales=("net_sales", "sum"))
        .reset_index()
        .sort_values("year")
    )
    
    yearly["growth_pct"] = (yearly["total_sales"].pct_change() * 100).round(2)

    fig = px.bar(yearly, x="year", y="total_sales", text_auto=".3s",
                 title="Yearly Net Sales",
                 labels={"year": "Year", "total_sales": "Net Sales ($)"})
    fig.update_xaxes(type="category")
    c2.plotly_chart(fig, use_container_width=True)

    st.subheader("Year-over-year growth")
    st.dataframe(
        yearly.rename(columns={
            "year": "Year", "total_orders": "Orders", "units_sold": "Units",
            "total_sales": "Net Sales", "growth_pct": "Growth %"})
        .style.format({"Net Sales": "${:,.2f}", "Growth %": "{:.2f}%"}, na_rep="—"),
        use_container_width=True, hide_index=True,
    )
    st.caption("Growth is only meaningful when consecutive years are selected in the sidebar.")

# Brands & categories
with tab_brand:
    c1, c2 = st.columns(2)

    brand_sales = (
        df.groupby("brand_name")
        .agg(units_sold=("quantity", "sum"), total_sales=("net_sales", "sum"))
        .reset_index()
        .sort_values("total_sales", ascending=True)
    )
    fig = px.bar(brand_sales, x="total_sales", y="brand_name", orientation="h",
                 text_auto=".3s", title="Net Sales by Brand",
                 labels={"total_sales": "Net Sales ($)", "brand_name": ""})
    c1.plotly_chart(fig, use_container_width=True)

    cat_sales = (
        df.groupby("category_name")["net_sales"].sum().reset_index()
        .sort_values("net_sales", ascending=True)
    )
    fig = px.bar(cat_sales, x="net_sales", y="category_name", orientation="h",
                 text_auto=".3s", title="Net Sales by Category",
                 labels={"net_sales": "Net Sales ($)", "category_name": ""})
    c2.plotly_chart(fig, use_container_width=True)

    fig = px.treemap(df, path=["brand_name", "category_name"], values="net_sales",
                     title="Sales Mix: Brand → Category")
    st.plotly_chart(fig, use_container_width=True)

# Top products
with tab_product:
    top_n = st.slider("Number of products", 5, 25, 10)
    metric = st.radio("Rank by", ["Units sold", "Net sales"], horizontal=True)
    rank_col = "units_sold" if metric == "Units sold" else "total_sales"

    top = (
        df.groupby(["product_id", "product_name", "brand_name"])
        .agg(units_sold=("quantity", "sum"), total_sales=("net_sales", "sum"))
        .reset_index()
        .sort_values(rank_col, ascending=False)
        .head(top_n)
    )
    fig = px.bar(top.sort_values(rank_col), x=rank_col, y="product_name",
                 color="brand_name", orientation="h", text_auto=".3s",
                 title=f"Top {top_n} Products by {metric}",
                 labels={rank_col: metric, "product_name": ""})
    fig.update_layout(height=max(400, top_n * 35))
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        top.rename(columns={"product_id": "ID", "product_name": "Product",
                            "brand_name": "Brand", "units_sold": "Units",
                            "total_sales": "Net Sales"})
        .style.format({"Net Sales": "${:,.2f}"}),
        use_container_width=True, hide_index=True,
    )

#Catalog pricing
with tab_catalog:
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Total Products", f"{len(products):,}")
    p2.metric("Average Price", f"${products['list_price'].mean():,.2f}")
    p3.metric("Lowest Price", f"${products['list_price'].min():,.2f}")
    p4.metric("Highest Price", f"${products['list_price'].max():,.2f}")

    c1, c2 = st.columns(2)
    brand_price = (
        products.groupby("brand_name")
        .agg(total_products=("product_id", "count"),
             average_price=("list_price", "mean"),
             highest_price=("list_price", "max"))
        .round(2).reset_index()
        .sort_values("average_price", ascending=False)
    )
    fig = px.bar(brand_price, x="brand_name", y="average_price", text_auto=".0f",
                 title="Average List Price by Brand",
                 labels={"brand_name": "", "average_price": "Avg Price ($)"})
    c1.plotly_chart(fig, use_container_width=True)

    fig = px.bar(brand_price.sort_values("total_products", ascending=False),
                 x="brand_name", y="total_products", text_auto=True,
                 title="Number of Products by Brand",
                 labels={"brand_name": "", "total_products": "Products"})
    c2.plotly_chart(fig, use_container_width=True)

    fig = px.box(products, x="category_name", y="list_price",
                 title="Price Distribution by Category",
                 labels={"category_name": "", "list_price": "List Price ($)"})
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top 10 most expensive products")
    st.dataframe(
        products.sort_values("list_price", ascending=False).head(10)
        .style.format({"list_price": "${:,.2f}"}),
        use_container_width=True, hide_index=True,
    )

# Data overview 
with tab_data:
    st.subheader("Row count per table")
    counts = load_table_counts()
    c1, c2 = st.columns([1, 2])
    c1.dataframe(counts, use_container_width=True, hide_index=True)
    fig = px.bar(counts.sort_values("total_rows"), x="total_rows", y="table_name",
                 orientation="h", text_auto=True, labels={"table_name": "", "total_rows": "Rows"})
    c2.plotly_chart(fig, use_container_width=True)
