#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from pathlib import Path

sns.set_theme(style="whitegrid")

pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 50)

DATA_PATH = "bina_az_data_template.xlsx"

OUT_DIR = Path("eda_output")
OUT_DIR.mkdir(exist_ok=True)

print("Setup completed.")


# In[2]:


df = pd.read_excel(
    DATA_PATH,
    sheet_name="Melumatlar"
)

print("Original shape:", df.shape)

df.head()


# In[3]:


data_columns = [
    col for col in df.columns
    if col != "sira_no"
]

df = df.dropna(
    how="all",
    subset=data_columns
).copy()

print("Shape after removing completely empty rows:", df.shape)


# In[4]:


df.info()


# In[5]:


print("Duplicate rows:", df.duplicated().sum())


# In[6]:


if "elan_nomresi" in df.columns:
    print(
        "Duplicate listing IDs:",
        df["elan_nomresi"].dropna().duplicated().sum()
    )


# In[7]:


missing = (
    df.isna()
    .mean()
    .mul(100)
    .round(1)
    .sort_values(ascending=False)
)

missing = missing[missing > 0]

print("Missing values (%):")
print(missing)


# In[8]:


categorical_cols = [
    "elan_novu",
    "emeliyyat_novu",
    "seher",
    "rayon",
    "mikrorayon_kompleks",
    "metro",
    "temir",
    "cixaris_kupca",
    "ipoteka",
    "daxili_kredit",
    "satici_novu",
    "kompleks_elanidir",
    "qiymet_vahidi"
]

for col in categorical_cols:
    if col in df.columns:
        print(f"\n--- {col} ---")
        print(df[col].value_counts(dropna=False))


# In[9]:


print(
    df["emeliyyat_novu"]
    .value_counts(dropna=False)
)


# In[10]:


n_sales = (
    df["emeliyyat_novu"] == "Satış"
).sum()

n_rent = (
    df["emeliyyat_novu"] == "Kirayə"
).sum()

print("Sales:", n_sales)
print("Rent:", n_rent)


# In[11]:


print(
    df["kompleks_elanidir"]
    .value_counts(dropna=False)
)


# In[12]:


df_core = df[
    (df["emeliyyat_novu"] == "Satış") &
    (df["kompleks_elanidir"] != "Bəli") &
    (df["qiymet_vahidi"] == "AZN")
].copy()

print("Core dataset shape:", df_core.shape)


# In[13]:


numeric_cols = [
    "otaq_sayi",
    "sahe_m2",
    "torpaq_sahe_sot",
    "mertebe",
    "bina_mertebe_sayi",
    "qiymet_azn",
    "qiymet_m2",
    "baxis_sayi"
]

numeric_cols = [
    col for col in numeric_cols
    if col in df_core.columns
]

print(numeric_cols)


# In[14]:


if len(df_core) >= 5:
    print(
        df_core[numeric_cols]
        .describe()
        .T
    )
else:
    print(
        f"Only {len(df_core)} core rows available. "
        "Descriptive statistics will be meaningful after more data is added."
    )


# In[15]:


checks = {
    "negative_price": (
        df_core["qiymet_azn"] < 0
    ).sum(),

    "zero_price": (
        df_core["qiymet_azn"] == 0
    ).sum(),

    "negative_area": (
        df_core["sahe_m2"] < 0
    ).sum(),

    "zero_area": (
        df_core["sahe_m2"] == 0
    ).sum(),

    "negative_rooms": (
        df_core["otaq_sayi"] < 0
    ).sum(),

    "zero_rooms": (
        df_core["otaq_sayi"] == 0
    ).sum()
}

pd.Series(checks)


# In[16]:


invalid_floor = df_core[
    df_core["mertebe"].notna() &
    df_core["bina_mertebe_sayi"].notna() &
    (
        (df_core["mertebe"] <= 0) |
        (df_core["bina_mertebe_sayi"] <= 0) |
        (df_core["mertebe"] > df_core["bina_mertebe_sayi"])
    )
]

print("Invalid floor records:", len(invalid_floor))


# In[17]:


df["area_per_room"] = (
    df["sahe_m2"] /
    df["otaq_sayi"].replace(0, np.nan)
)

df[
    [
        "sahe_m2",
        "otaq_sayi",
        "area_per_room"
    ]
].head()


# In[18]:


df["floor_ratio"] = (
    df["mertebe"] /
    df["bina_mertebe_sayi"].replace(0, np.nan)
)

df[
    [
        "mertebe",
        "bina_mertebe_sayi",
        "floor_ratio"
    ]
].head()


# In[19]:


df["is_top_floor"] = (
    df["mertebe"].notna() &
    df["bina_mertebe_sayi"].notna() &
    (
        df["mertebe"] ==
        df["bina_mertebe_sayi"]
    )
).astype("int8")


# In[20]:


df["is_first_floor"] = (
    df["mertebe"] == 1
).astype("int8")


# In[21]:


engineered_features = [
    "area_per_room",
    "floor_ratio",
    "is_top_floor",
    "is_first_floor"
]

df[
    engineered_features
].head(10)


# In[22]:


df[engineered_features].describe()


# In[23]:


selected_features = [
    "elan_novu",
    "seher",
    "rayon",
    "mikrorayon_kompleks",
    "metro",
    "nishangah",
    "otaq_sayi",
    "sahe_m2",
    "torpaq_sahe_sot",
    "mertebe",
    "bina_mertebe_sayi",
    "temir",
    "cixaris_kupca",
    "ipoteka",
    "daxili_kredit",
    "satici_novu",
    "baxis_sayi",
    "area_per_room",
    "floor_ratio",
    "is_top_floor",
    "is_first_floor"
]

selected_features = [
    col for col in selected_features
    if col in df.columns
]

print("Selected features:")
print(selected_features)


# In[24]:


valid_price_m2 = df_core[
    "qiymet_m2"
].dropna()

print(
    "Valid price/m² values:",
    len(valid_price_m2)
)


# In[25]:


if len(valid_price_m2) >= 5:

    plt.figure(figsize=(8, 5))

    sns.histplot(
        valid_price_m2,
        bins=20,
        kde=True
    )

    plt.title("Price per m² Distribution")
    plt.xlabel("AZN / m²")
    plt.ylabel("Number of listings")

    plt.tight_layout()

    plt.savefig(
        OUT_DIR / "price_per_m2_distribution.png",
        dpi=150
    )

    plt.close()

    print("Histogram saved.")

else:

    print(
        "Not enough valid price/m² values for visualization yet."
    )


# In[28]:


corr_features = [
    "otaq_sayi",
    "sahe_m2",
    "torpaq_sahe_sot",
    "mertebe",
    "bina_mertebe_sayi",
    "baxis_sayi",
    "area_per_room",
    "floor_ratio",
    "is_top_floor",
    "is_first_floor",
    "qiymet_azn"
]

corr_features = [
    col for col in corr_features
    if col in df_core.columns or col in df.columns
]


# In[29]:


analysis_df = df_core.copy()

for col in [
    "area_per_room",
    "floor_ratio",
    "is_top_floor",
    "is_first_floor"
]:
    analysis_df[col] = df.loc[
        analysis_df.index,
        col
    ]


# In[30]:


if len(analysis_df) >= 5:

    corr = analysis_df[
        corr_features
    ].corr(numeric_only=True)

    plt.figure(figsize=(10, 8))

    sns.heatmap(
        corr,
        annot=True,
        fmt=".2f",
        center=0
    )

    plt.title(
        "Correlation Between Numerical Features"
    )

    plt.tight_layout()

    plt.savefig(
        OUT_DIR / "correlation_heatmap.png",
        dpi=150
    )

    plt.close()

    print("Correlation heatmap saved.")

else:

    print(
        "Not enough data for meaningful correlation analysis yet."
    )


# In[31]:


if len(valid_price_m2) >= 5:

    q1 = valid_price_m2.quantile(0.25)
    q3 = valid_price_m2.quantile(0.75)

    iqr = q3 - q1

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    outliers = df_core[
        (df_core["qiymet_m2"] < lower_bound) |
        (df_core["qiymet_m2"] > upper_bound)
    ]

    print(
        f"Lower bound: {lower_bound:.2f}"
    )

    print(
        f"Upper bound: {upper_bound:.2f}"
    )

    print(
        "Number of outliers:",
        len(outliers)
    )

else:

    print(
        "Not enough data for reliable outlier detection yet."
    )


# In[32]:


final_columns = [
    "elan_novu",
    "seher",
    "rayon",
    "mikrorayon_kompleks",
    "metro",
    "nishangah",
    "otaq_sayi",
    "sahe_m2",
    "torpaq_sahe_sot",
    "mertebe",
    "bina_mertebe_sayi",
    "temir",
    "cixaris_kupca",
    "ipoteka",
    "daxili_kredit",
    "satici_novu",
    "baxis_sayi",
    "area_per_room",
    "floor_ratio",
    "is_top_floor",
    "is_first_floor",
    "qiymet_azn"
]

final_columns = [
    col for col in final_columns
    if col in df.columns
]

df_final = df[
    final_columns
].copy()

print("Final dataset shape:", df_final.shape)

df_final.head()


# In[33]:


TARGET = "qiymet_azn"

FEATURES = [
    col for col in df_final.columns
    if col != TARGET
]

print("TARGET:")
print(TARGET)

print("\nFEATURES:")
print(FEATURES)


# In[34]:


final_missing = (
    df_final.isna()
    .mean()
    .mul(100)
    .round(1)
    .sort_values(ascending=False)
)

print("Missing values in final dataset (%):")
print(
    final_missing[
        final_missing > 0
    ]
)


# In[35]:


OUTPUT_PATH = "bina_az_cleaned_features.csv"

df_final.to_csv(
    OUTPUT_PATH,
    index=False,
    encoding="utf-8-sig"
)

print(
    f"Saved: {OUTPUT_PATH}"
)


# In[ ]:





# In[ ]:





# In[ ]:




