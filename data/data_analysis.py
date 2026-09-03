import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split


# ============================================================
# 1. LOAD DATA
# ============================================================

df = pd.read_csv("Downloads/sample_30.csv")

print("Shape:", df.shape)
print("\nFirst 5 rows:")
print(df.head())

print("\nData information:")
print(df.info())


# ============================================================
# 2. INITIAL DATA CHECK
# ============================================================

print("\nDuplicate rows:", df.duplicated().sum())
print("Duplicate listing IDs:", df["listing_id"].duplicated().sum())

print("\nMissing price values:", df["price_azn"].isna().sum())
print("Non-positive prices:", (df["price_azn"] <= 0).sum())

print("\nDeal type distribution:")
print(df["deal_type"].value_counts(dropna=False))


# ============================================================
# 3. MISSING VALUES ANALYSIS
# ============================================================

missing = (
    df.isna()
    .sum()
    .to_frame("missing_count")
)

missing["missing_percent"] = (
    missing["missing_count"] / len(df) * 100
).round(1)

missing = missing.sort_values(
    "missing_percent",
    ascending=False
)

print("\nMissing values:")
print(missing)


print("\nMissing floor values:")
print(df[["floor", "total_floors"]].isna().sum())


# ============================================================
# 4. NUMERICAL DATA VALIDATION
# ============================================================

numeric_cols = [
    "price_azn",
    "area_m2",
    "rooms",
    "floor",
    "total_floors"
]

print("\nNegative and zero values:")

for col in numeric_cols:
    print(
        col,
        "negative:", (df[col] < 0).sum(),
        "zero:", (df[col] == 0).sum()
    )


# Check invalid floor relationships
invalid_floor = df[
    df["floor"].notna()
    & df["total_floors"].notna()
    & (
        (df["floor"] <= 0)
        | (df["total_floors"] <= 0)
        | (df["floor"] > df["total_floors"])
    )
]

print("\nInvalid floor records:", len(invalid_floor))


# ============================================================
# 5. CATEGORICAL DATA ANALYSIS
# ============================================================

categorical_cols = [
    "deal_type",
    "property_type",
    "renovation",
    "has_kupca",
    "has_mortgage",
    "city",
    "seller_type"
]

for col in categorical_cols:
    print(f"\n{col}")
    print(df[col].value_counts(dropna=False))


print("\nUnique values:")
print("has_kupca:", df["has_kupca"].nunique())
print("seller_type:", df["seller_type"].nunique())


# ============================================================
# 6. REMOVE COMPLETELY MISSING COLUMNS
# ============================================================

drop_cols = [
    "building_type",
    "district",
    "latitude",
    "longitude"
]

df = df.drop(columns=drop_cols)


# ============================================================
# 7. CHECK AND REMOVE CONSTANT COLUMNS
# ============================================================

constant_cols = [
    col
    for col in df.columns
    if df[col].nunique(dropna=False) <= 1
]

print("\nConstant columns:", constant_cols)

df = df.drop(columns=constant_cols)


# ============================================================
# 8. HIGH-MISSING COLUMNS
# ============================================================

missing_after_cleaning = (
    df.isna()
    .mean()
    .mul(100)
    .round(1)
    .sort_values(ascending=False)
)

print("\nRemaining missing values:")
print(missing_after_cleaning[missing_after_cleaning > 0])


# ============================================================
# 9. FEATURE ENGINEERING
# ============================================================

# Price per square meter
df["price_per_m2"] = (
    df["price_azn"] / df["area_m2"]
)

# Area per room
df["area_per_room"] = (
    df["area_m2"] /
    df["rooms"].replace(0, np.nan)
)

# Floor ratio
df["floor_ratio"] = (
    df["floor"] /
    df["total_floors"].replace(0, np.nan)
)

# First floor indicator
df["is_first_floor"] = (
    df["floor"] == 1
).astype("int8")

# Top floor indicator
df["is_top_floor"] = (
    df["floor"].notna()
    & df["total_floors"].notna()
    & (df["floor"] == df["total_floors"])
).astype("int8")

# Description features
df["description_length"] = (
    df["description"].str.len()
)

df["description_word_count"] = (
    df["description"].str.split().str.len()
)

# Pool indicator
df["has_pool"] = (
    df["description"]
    .str.lower()
    .str.contains(
        "hovuz|бассейн",
        regex=True
    )
    .astype(int)
)


print("\nFeature engineering completed.")

print("\nPrice per m2 statistics:")
print(df["price_per_m2"].describe())


# ============================================================
# 10. OUTLIER DETECTION
# ============================================================

Q1 = df["price_per_m2"].quantile(0.25)
Q3 = df["price_per_m2"].quantile(0.75)

IQR = Q3 - Q1

lower = Q1 - 1.5 * IQR
upper = Q3 + 1.5 * IQR

outliers = df[
    (df["price_per_m2"] < lower)
    | (df["price_per_m2"] > upper)
]

print("\nOutlier analysis:")
print("Q1:", Q1)
print("Q3:", Q3)
print("IQR:", IQR)
print("Lower bound:", lower)
print("Upper bound:", upper)
print("Number of outliers:", len(outliers))

if len(outliers) > 0:
    print(
        outliers[
            [
                "listing_id",
                "property_type",
                "price_azn",
                "area_m2",
                "price_per_m2"
            ]
        ]
    )


# ============================================================
# 11. TEXT FEATURE CHECK
# ============================================================

print("\nText-based features:")
print(
    df[
        [
            "description",
            "description_length",
            "description_word_count",
            "has_pool"
        ]
    ].head(10)
)

print("\nPool feature distribution:")
print(df["has_pool"].value_counts(dropna=False))


# ============================================================
# 12. DESCRIPTIVE STATISTICS
# ============================================================

print("\nPrice statistics:")
print(df["price_azn"].describe())

print("\nNumerical statistics:")
print(
    df[
        [
            "price_azn",
            "area_m2",
            "rooms",
            "price_per_m2"
        ]
    ].describe().T
)


# ============================================================
# 13. PRICE ANALYSIS BY PROPERTY TYPE
# ============================================================

print("\nPrice statistics by property type:")

print(
    df.groupby("property_type")["price_azn"]
    .agg(
        [
            "count",
            "min",
            "median",
            "mean",
            "max"
        ]
    )
)


# ============================================================
# 14. CORRELATION ANALYSIS
# ============================================================

corr_cols = [
    "price_azn",
    "area_m2",
    "rooms",
    "floor",
    "total_floors",
    "area_per_room",
    "floor_ratio",
    "description_length",
    "description_word_count"
]

corr = df[corr_cols].corr(numeric_only=True)

print("\nCorrelation with price:")
print(
    corr["price_azn"]
    .sort_values(ascending=False)
)


# ============================================================
# 15. PRICE DISTRIBUTION
# ============================================================

plt.figure(figsize=(8, 5))

sns.histplot(
    df["price_azn"],
    bins=10,
    kde=True
)

plt.title("Distribution of Property Prices")
plt.xlabel("Price (AZN)")
plt.ylabel("Number of Listings")

plt.tight_layout()
plt.show()


# ============================================================
# 16. FINAL FEATURE SELECTION
# ============================================================

FEATURES = [
    "property_type",
    "area_m2",
    "rooms",
    "floor",
    "total_floors",
    "renovation",
    "has_mortgage",
    "city",
    "area_per_room",
    "floor_ratio",
    "is_first_floor",
    "is_top_floor"
]

X = df[FEATURES].copy()
y = df["price_azn"].copy()


print("\nSelected features:")

for feature in FEATURES:
    print("-", feature)


print("\nX shape:", X.shape)
print("y shape:", y.shape)


# ============================================================
# 17. FINAL FEATURE CHECK
# ============================================================

print("\nMissing values in selected features:")
print(X.isnull().sum())

print("\nCategorical columns:")
print(
    X.select_dtypes(
        include="object"
    ).columns.tolist()
)

print("\nNumerical columns:")
print(
    X.select_dtypes(
        include=np.number
    ).columns.tolist()
)

print("\nTarget:", y.name)
print("Target shape:", y.shape)


# ============================================================
# 18. TRAIN / TEST SPLIT
# ============================================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

print("\nTrain/Test split:")
print("X_train shape:", X_train.shape)
print("X_test shape:", X_test.shape)
print("y_train shape:", y_train.shape)
print("y_test shape:", y_test.shape)


# ============================================================
# 19. SAVE CLEANED DATASET
# ============================================================

df.to_csv(
    "bina_az_cleaned_features.csv",
    index=False
)

print("\nCleaned dataset saved successfully.")