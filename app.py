"""
Bike Store Sales Dashboard
Run: streamlit run app.py
iconse been imported from live examples 

"""

import os

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL



# PAGE CONFIGURATION


st.set_page_config(
    page_title="Bike Store Dashboard",
    page_icon="🚲",
    layout="wide",
)



# DATABASE CONFIGURATION


def get_config(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


DB_USER = get_config("DB_USER", "2jiLGJsz9gFrd6S.root")
DB_PASSWORD = get_config("DB_PASSWORD")
DB_HOST = get_config(
    "DB_HOST",
    "gateway01.eu-central-1.prod.aws.tidbcloud.com",
)
DB_PORT = get_config("DB_PORT", "4000")
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

    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "ssl_verify_cert": True,
            "ssl_verify_identity": True,
        },
    )



# SQL QUERIES


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
    oi.quantity * oi.list_price
        AS sales_before_discount,
    oi.quantity * oi.list_price * (1 - oi.discount)
        AS net_sales
FROM order_items AS oi
INNER JOIN orders AS o
    ON oi.order_id = o.order_id
INNER JOIN products AS p
    ON oi.product_id = p.product_id
INNER JOIN brands AS b
    ON p.brand_id = b.brand_id
INNER JOIN categories AS c
    ON p.category_id = c.category_id
"""

PRODUCTS_QUERY = """
SELECT
    p.product_id,
    p.product_name,
    b.brand_name,
    c.category_name,
    p.model_year,
    p.list_price
FROM products AS p
INNER JOIN brands AS b
    ON p.brand_id = b.brand_id
INNER JOIN categories AS c
    ON p.category_id = c.category_id
"""

TABLES = [
    "brands",
    "categories",
    "customers",
    "order_items",
    "orders",
    "products",
    "staffs",
    "stocks",
    "stores",
]



# DATA LOADING multiple df funtion :) 


@st.cache_data(ttl=600)
def load_sales() -> pd.DataFrame:
    df = pd.read_sql(text(FACT_QUERY), get_engine())

    df["order_date"] = pd.to_datetime(df["order_date"])
    df["year"] = df["order_date"].dt.year
    df["month"] = (
        df["order_date"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    numeric_columns = [
        "quantity",
        "list_price",
        "discount",
        "sales_before_discount",
        "net_sales",
    ]

    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col])

    return df


@st.cache_data(ttl=600)
def load_products() -> pd.DataFrame:
    df = pd.read_sql(text(PRODUCTS_QUERY), get_engine())

    df["list_price"] = pd.to_numeric(
        df["list_price"],
        errors="coerce",
    )

    return df


@st.cache_data(ttl=600)
def load_table_counts() -> pd.DataFrame:
    engine = get_engine()
    rows = []

    
    # Check which tables actually exist before querying them.
    
    with engine.connect() as conn:
        existing_tables = set(
            conn.execute(
                text("SHOW TABLES")
            ).scalars().all()
        )

        for table_name in TABLES:
            if table_name not in existing_tables:
                rows.append({
                    "table_name": table_name,
                    "total_rows": None,
                    "status": "Table not found",
                })
                continue

            
            # Table names come only from the fixed TABLES list.
            
            
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM `{table_name}`")
            ).scalar_one()

            rows.append({
                "table_name": table_name,
                "total_rows": count,
                "status": "Available",
            })

    return pd.DataFrame(rows)


# LOAD DATA


try:
    sales = load_sales()
    products = load_products()

except Exception as e:
    st.error(f"Could not load dashboard data: {e}")
    st.info(
        "Check DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, "
        "and DB_NAME in your Streamlit secrets or environment."
    )
    st.stop()


if sales.empty:
    st.warning("No sales records were found in the database.")
    st.stop()


# GLOBAL FILTERS


st.sidebar.title("🚲 Filters")

years = sorted(sales["year"].dropna().unique().tolist())
brands = sorted(sales["brand_name"].dropna().unique().tolist())
categories = sorted(
    sales["category_name"].dropna().unique().tolist()
)

sel_years = st.sidebar.multiselect(
    "Year",
    years,
    default=years,
)

sel_brands = st.sidebar.multiselect(
    "Brand",
    brands,
    default=brands,
)

sel_categories = st.sidebar.multiselect(
    "Category",
    categories,
    default=categories,
)

df = sales[
    sales["year"].isin(sel_years)
    & sales["brand_name"].isin(sel_brands)
    & sales["category_name"].isin(sel_categories)
].copy()

# DASHBOARD HEADER

st.title("Bike Store Sales Dashboard")

st.caption(
    "Source: MySQL · bike_store_db · "
    "Net sales = Quantity × List Price × (1 − Discount)"
)


if df.empty:
    st.warning(
        "No sales data matches the selected global filters. "
        "Please adjust your selections."
    )
    st.stop()


# KEY PERFORMANCE INDICATORS most common as i have found that these are most common not sure if there are more

total_orders = df["order_id"].nunique()
total_units = int(df["quantity"].sum())

gross = df["sales_before_discount"].sum()
net = df["net_sales"].sum()

discount_given = gross - net
discount_percentage = discount_given / gross if gross else 0

average_order_value = net / total_orders if total_orders else 0

k1, k2, k3, k4, k5 = st.columns(5)

k1.metric("Net Sales", f"${net:,.0f}")
k2.metric("Orders", f"{total_orders:,}")
k3.metric("Units Sold", f"{total_units:,}")

k4.metric(
    "Avg Order Value",
    f"${average_order_value:,.0f}",
)

k5.metric(
    "Discounts Given",
    f"${discount_given:,.0f}",
    f"{discount_percentage:.1%} of gross",
    delta_color="off",
)

st.divider()


# DASHBOARD TABS , the iconse been omported online and as from live example 

tab_trend, tab_brand, tab_product, tab_catalog, tab_data = (
    st.tabs([
        "📈 Sales Trends",
        "🏷️ Brands & Categories",
        "🏆 Top Products",
        "📦 Catalog Pricing",
        "🗄️ Data Overview",
    ])
)


# TAB 1: SALES TRENDS

with tab_trend:

    c1, c2 = st.columns([2, 1])

    monthly = (
        df.groupby("month")
        .agg(
            total_orders=("order_id", "nunique"),
            units_sold=("quantity", "sum"),
            total_sales=("net_sales", "sum"),
        )
        .reset_index()
        .sort_values("month")
    )

    monthly_fig = px.line(
        monthly,
        x="month",
        y="total_sales",
        markers=True,
        title="Monthly Net Sales",
        labels={
            "month": "Month",
            "total_sales": "Net Sales ($)",
        },
    )

    monthly_fig.update_layout(hovermode="x unified")

    c1.plotly_chart(
        monthly_fig,
        use_container_width=True,
    )

    yearly = (
        df.groupby("year")
        .agg(
            total_orders=("order_id", "nunique"),
            units_sold=("quantity", "sum"),
            total_sales=("net_sales", "sum"),
        )
        .reset_index()
        .sort_values("year")
    )

    yearly["growth_pct"] = (
        yearly["total_sales"]
        .pct_change()
        .mul(100)
        .round(2)
    )

    yearly_fig = px.bar(
        yearly,
        x="year",
        y="total_sales",
        text_auto=".3s",
        title="Yearly Net Sales",
        labels={
            "year": "Year",
            "total_sales": "Net Sales ($)",
        },
    )

    yearly_fig.update_xaxes(type="category")

    c2.plotly_chart(
        yearly_fig,
        use_container_width=True,
    )

    st.subheader("Year-over-Year Growth")

    yearly_display = yearly.rename(
        columns={
            "year": "Year",
            "total_orders": "Orders",
            "units_sold": "Units",
            "total_sales": "Net Sales",
            "growth_pct": "Growth %",
        }
    )

    st.dataframe(
        yearly_display.style.format(
            {
                "Net Sales": "${:,.2f}",
                "Growth %": "{:.2f}%",
            },
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
    )

    selected_years_sorted = sorted(
        df["year"].dropna().unique().tolist()
    )

    consecutive_years = (
        len(selected_years_sorted) >= 2
        and all(
            selected_years_sorted[i + 1]
            - selected_years_sorted[i] == 1
            for i in range(len(selected_years_sorted) - 1)
        )
    )

    if consecutive_years:
        st.caption(
            "Growth is calculated between consecutive selected years."
        )
    else:
        st.info(
            "For meaningful year-over-year comparisons, select "
            "at least two consecutive years in the sidebar."
        )


# TAB 2: BRANDS & CATEGORIES


with tab_brand:

    c1, c2 = st.columns(2)

    brand_sales = (
        df.groupby("brand_name")
        .agg(
            units_sold=("quantity", "sum"),
            total_sales=("net_sales", "sum"),
        )
        .reset_index()
        .sort_values("total_sales", ascending=True)
    )

    brand_fig = px.bar(
        brand_sales,
        x="total_sales",
        y="brand_name",
        orientation="h",
        text_auto=".3s",
        title="Net Sales by Brand",
        labels={
            "total_sales": "Net Sales ($)",
            "brand_name": "",
        },
    )

    c1.plotly_chart(
        brand_fig,
        use_container_width=True,
    )

    category_sales = (
        df.groupby("category_name")["net_sales"]
        .sum()
        .reset_index()
        .sort_values("net_sales", ascending=True)
    )

    category_fig = px.bar(
        category_sales,
        x="net_sales",
        y="category_name",
        orientation="h",
        text_auto=".3s",
        title="Net Sales by Category",
        labels={
            "net_sales": "Net Sales ($)",
            "category_name": "",
        },
    )

    c2.plotly_chart(
        category_fig,
        use_container_width=True,
    )

    treemap_fig = px.treemap(
        df,
        path=["brand_name", "category_name"],
        values="net_sales",
        title="Sales Mix: Brand → Category",
    )

    st.plotly_chart(
        treemap_fig,
        use_container_width=True,
    )

# TAB 3: TOP PRODUCTS

with tab_product:

    top_n = st.slider(
        "Number of products",
        min_value=5,
        max_value=25,
        value=10,
    )

    metric = st.radio(
        "Rank by",
        ["Units sold", "Net sales"],
        horizontal=True,
    )

    rank_col = (
        "units_sold"
        if metric == "Units sold"
        else "total_sales"
    )

    top = (
        df.groupby(
            ["product_id", "product_name", "brand_name"]
        )
        .agg(
            units_sold=("quantity", "sum"),
            total_sales=("net_sales", "sum"),
        )
        .reset_index()
        .sort_values(rank_col, ascending=False)
        .head(top_n)
    )

    top_fig = px.bar(
        top.sort_values(rank_col),
        x=rank_col,
        y="product_name",
        color="brand_name",
        orientation="h",
        text_auto=".3s",
        title=f"Top {top_n} Products by {metric}",
        labels={
            rank_col: metric,
            "product_name": "",
            "brand_name": "Brand",
        },
    )

    top_fig.update_layout(
        height=max(400, top_n * 35)
    )

    st.plotly_chart(
        top_fig,
        use_container_width=True,
    )

    top_display = top.rename(
        columns={
            "product_id": "ID",
            "product_name": "Product",
            "brand_name": "Brand",
            "units_sold": "Units",
            "total_sales": "Net Sales",
        }
    )

    st.dataframe(
        top_display.style.format(
            {"Net Sales": "${:,.2f}"}
        ),
        use_container_width=True,
        hide_index=True,
    )


# TAB 4: CATALOG PRICING

with tab_catalog:

    st.subheader("Catalog Pricing Analysis")

    st.caption(
        "These filters apply only to Catalog Pricing. "
        "The global sidebar filters control the sales analysis."
    )

    # Local catalog filters.
    # These filters use the catalog dataset, not sales data.

    catalog_brands = sorted(
        products["brand_name"].dropna().unique().tolist()
    )

    catalog_categories = sorted(
        products["category_name"].dropna().unique().tolist()
    )

    f1, f2 = st.columns(2)

    with f1:
        selected_catalog_brands = st.multiselect(
            "Catalog Brand",
            catalog_brands,
            default=catalog_brands,
            key="catalog_brands",
        )

    with f2:
        selected_catalog_categories = st.multiselect(
            "Catalog Category",
            catalog_categories,
            default=catalog_categories,
            key="catalog_categories",
        )

    
    # IMPORTANT: All Catalog Pricing metrics, charts, and tables must use catalog_filtered instead of products.


    catalog_filtered = products[
        products["brand_name"].isin(
            selected_catalog_brands
        )
        & products["category_name"].isin(
            selected_catalog_categories
        )
    ].copy()

    if catalog_filtered.empty:

        st.warning(
            "No products match the selected catalog filters. "
            "Please adjust your selections."
        )

    else:

        # CATALOG KPI

        total_products = len(catalog_filtered)

        average_price = (
            catalog_filtered["list_price"].mean()
        )

        lowest_price = (
            catalog_filtered["list_price"].min()
        )

        highest_price = (
            catalog_filtered["list_price"].max()
        )

        p1, p2, p3, p4 = st.columns(4)

        p1.metric(
            "Total Products",
            f"{total_products:,}",
        )

        p2.metric(
            "Average Price",
            f"${average_price:,.2f}",
        )

        p3.metric(
            "Lowest Price",
            f"${lowest_price:,.2f}",
        )

        p4.metric(
            "Highest Price",
            f"${highest_price:,.2f}",
        )

        # AVG price and product COUNT by brand

        brand_price = (
            catalog_filtered.groupby("brand_name")
            .agg(
                total_products=("product_id", "count"),
                average_price=("list_price", "mean"),
                highest_price=("list_price", "max"),
            )
            .round(2)
            .reset_index()
        )

        c1, c2 = st.columns(2)

        brand_price_avg = brand_price.sort_values(
            "average_price",
            ascending=False,
        )

        avg_price_fig = px.bar(
            brand_price_avg,
            x="brand_name",
            y="average_price",
            text_auto=".0f",
            title="Average List Price by Brand",
            labels={
                "brand_name": "",
                "average_price": "Avg Price ($)",
            },
        )

        c1.plotly_chart(
            avg_price_fig,
            use_container_width=True,
        )

        brand_price_count = brand_price.sort_values(
            "total_products",
            ascending=False,
        )

        product_count_fig = px.bar(
            brand_price_count,
            x="brand_name",
            y="total_products",
            text_auto=True,
            title="Number of Products by Brand",
            labels={
                "brand_name": "",
                "total_products": "Products",
            },
        )

        c2.plotly_chart(
            product_count_fig,
            use_container_width=True,
        )

        # Box plot

        st.subheader("Price Distribution by Category")

        box_fig = px.box(
            catalog_filtered,
            x="category_name",
            y="list_price",
            points="outliers",
            title="Price Distribution by Category",
            labels={
                "category_name": "Category",
                "list_price": "List Price ($)",
            },
        )

        st.plotly_chart(
            box_fig,
            use_container_width=True,
        )

        st.markdown(
            """
            **How to read this chart**

            - **Middle line:** the median price of the category.
            - **Box:** the middle 50% of product prices.
            - **Whiskers:** the range of prices within the
              chart's standard whisker limits.
            - **Individual points:** potential price outliers.

            A taller box generally indicates greater variation
            among the middle 50% of prices. Longer whiskers or
            outliers can indicate a wider overall price range.
            """
        )

        # Calculate the category with the widest observation range.
        category_ranges = (
            catalog_filtered.groupby("category_name")["list_price"]
            .agg(
                lowest_price="min",
                highest_price="max",
            )
            .dropna()
        )

        category_ranges["price_range"] = (
            category_ranges["highest_price"]
            - category_ranges["lowest_price"]
        )

        if not category_ranges.empty:

            widest_category = (
                category_ranges["price_range"].idxmax()
            )

            widest_range = (
                category_ranges.loc[
                    widest_category,
                    "price_range",
                ]
            )

            st.info(
                f"**Example:** {widest_category} has the "
                f"widest observed price range among the "
                f"selected categories: "
                f"${widest_range:,.2f} "
                f"(highest price minus lowest price)."
            )

        # Top 10 most expensive products only

        st.subheader(
            "Top 10 Most Expensive Products"
        )

        expensive_products = (
            catalog_filtered.sort_values(
                "list_price",
                ascending=False,
            )
            .head(10)
            .copy()
        )

        st.dataframe(
            expensive_products.style.format(
                {"list_price": "${:,.2f}"}
            ),
            use_container_width=True,
            hide_index=True,
        )

# TAB 5: DATA OVERVIEW

with tab_data:

    st.subheader("Row Count per Table")

    try:

        counts = load_table_counts()

        c1, c2 = st.columns([1, 2])

        c1.dataframe(
            counts,
            use_container_width=True,
            hide_index=True,
        )

        # Only plot tables that were successfully found.
        available_counts = counts[
            counts["status"] == "Available"
        ].copy()

        if not available_counts.empty:

            counts_fig = px.bar(
                available_counts.sort_values(
                    "total_rows"
                ),
                x="total_rows",
                y="table_name",
                orientation="h",
                text_auto=True,
                title="Records per Table",
                labels={
                    "table_name": "Table",
                    "total_rows": "Rows",
                },
            )

            c2.plotly_chart(
                counts_fig,
                use_container_width=True,
            )

        missing_tables = counts[
            counts["status"] == "Table not found"
        ]["table_name"].tolist()

        if missing_tables:

            st.warning(
                "The following tables were not found in "
                "the connected database: "
                + ", ".join(missing_tables)
            )

    except Exception as e:

        st.error(
            f"Could not load table counts: {e}"
        )

        st.info(
            "Verify the database connection and table permissions."
        )

