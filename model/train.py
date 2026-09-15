#!/usr/bin/env python3
import os
import json
import pandas as pd
import numpy as np
from catboost import CatBoostRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# ==========================================
# 1. LOAD AND FILTER DATA
# ==========================================
# Dynamically find the script's directory to avoid path issues
df = pd.read_csv('/Users/iatakishi/Documents/coding env/Loupe/cleaned_data/sale.csv', header=None)

# Filter only apartments (new and old buildings)
df_apartments = df[df[2].isin(['menziller/yeni-tikili', 'menziller/kohne-tikili'])].copy()
print(f"Total apartment records: {len(df_apartments)}")

# ==========================================
# 2. RENAME COLUMNS TO ENGLISH (FOR READABILITY)
# ==========================================
col_names = [
    'ID', 'URL', 'Property_Type', 'Area_Unit', 'Area', 'Land_Area', 'Rooms', 'Floor', 'Total_Floors',
    'Renovated', 'Furnished', 'Has_Document', 'Building_Age', 'City', 'District', 'Neighborhood',
    'Floor_Ratio', 'Has_Gas', 'Has_Water', 'Price_Per_Sqm', 'Has_Elevator', 'Has_Parking', 'Price'
]
df_apartments.columns = col_names

# ==========================================
# 3. DROP LEAKAGE, UNNECESSARY COLUMNS & CLEAN TARGET
# ==========================================
# Save IDs and URLs before dropping them, we need them for the bot's JSON database
listing_ids = df_apartments['ID'].values
listing_urls = df_apartments['URL'].values

# Columns to drop:
# - ID, URL: Metadata, not features.
# - Area_Unit: All are 'm²' for apartments, provides no predictive value.
# - Land_Area: All NaN for apartments.
# - Floor_Ratio: Derived from Floor / Total_Floors (Redundant/Leakage).
# - Price_Per_Sqm: Directly mathematically related to the target (Major Data Leakage).
drop_cols = ['ID', 'URL', 'Area_Unit', 'Land_Area', 'Floor_Ratio', 'Price_Per_Sqm']

X = df_apartments.drop(columns=drop_cols + ['Price'])

# Convert Price to numeric. 'coerce' turns any invalid strings into NaN
y_original = pd.to_numeric(df_apartments['Price'], errors='coerce')

# Drop rows where Price is NaN (invalid/corrupted data)
valid_mask = y_original.notna()
X = X[valid_mask].reset_index(drop=True)
y_original = y_original[valid_mask].reset_index(drop=True)
listing_ids = listing_ids[valid_mask]
listing_urls = listing_urls[valid_mask]

print(f"Total valid records after cleaning target: {len(y_original)}")

# ==========================================
# 4. TRANSFORM TARGET VARIABLE
# ==========================================
# Cap extreme prices at the 99th percentile to prevent gradient distortion.
y = y_original.copy()
price_cap = y.quantile(0.99)
outlier_count = (y > price_cap).sum()
print(f"Clipping {outlier_count} extreme prices above {price_cap:,.0f} AZN")
y_clipped = y.clip(upper=price_cap)

# Apply log1p to stabilize variance and make the distribution more symmetric
y_log = np.log1p(y_clipped)

# ==========================================
# 5. PREPARE CATEGORICAL FEATURES
# ==========================================
# CatBoost handles categorical values natively.
# We convert boolean and NaN columns to string and fill with 'Unknown'.
cat_cols = [
    'Property_Type', 'Renovated', 'Furnished', 'Has_Document',
    'City', 'District', 'Neighborhood',
    'Has_Gas', 'Has_Water', 'Has_Elevator', 'Has_Parking'
]

for col in cat_cols:
    # Fill NaNs with 'Unknown' so the model learns missingness as a distinct category
    X[col] = X[col].fillna('Unknown').astype(str)

# ==========================================
# 6. TRAIN / TEST SPLIT
# ==========================================
# Target variable (y_log) is already transformed.
X_train, X_test, y_train_log, y_test_log = train_test_split(
    X, y_log, test_size=0.2, random_state=42
)

# ==========================================
# 7. BUILD AND TRAIN CATBOOST MODEL
# ==========================================
model = CatBoostRegressor(
    iterations=2000,
    learning_rate=0.03,  # Slower learning rate for better convergence
    depth=8,  # Slightly deeper trees to capture complex interactions
    l2_leaf_reg=5.0,  # L2 regularization to strictly prevent overfitting
    random_strength=1.5,  # Adds randomness to split selection
    bagging_temperature=0.5,  # Bayesian bagging temperature for variance reduction
    border_count=128,  # Optimized border count for faster training on 1500 rows
    cat_features=cat_cols,
    random_seed=42,
    verbose=100,  # Print progress every 100 iterations
    early_stopping_rounds=150  # Stop training if validation metric doesn't improve
)

print("\nModel training started...")
model.fit(X_train, y_train_log, eval_set=(X_test, y_test_log))

# ==========================================
# 8. EVALUATE RESULTS
# ==========================================
# Inverse transform predictions (expm1) to get actual AZN values
preds_log = model.predict(X_test)
preds_actual = np.expm1(preds_log)
y_test_actual = np.expm1(y_test_log)

mae = mean_absolute_error(y_test_actual, preds_actual)
rmse = np.sqrt(mean_squared_error(y_test_actual, preds_actual))
r2 = r2_score(y_test_actual, preds_actual)

print("\n--- MODEL 1 (APARTMENTS) RESULTS ---")
print(f"MAE  (Mean Absolute Error): {mae:.2f} AZN")
print(f"RMSE (Root Mean Squared Error): {rmse:.2f} AZN")
print(f"R²   (Explained Variance): {r2:.4f}")

# Feature Importance (Which factors impact price the most?)
feature_importances = model.get_feature_importance()
feature_names = X.columns
importance_df = pd.DataFrame({
    'Feature': feature_names,
    'Importance': feature_importances
}).sort_values(by='Importance', ascending=False)

print("\n--- TOP 10 MOST IMPORTANT FEATURES ---")
print(importance_df.head(10).to_string(index=False))

# ==========================================
# 9. GENERATE STATIC DB (PREDICTIONS.JSON) FOR BOT
# ==========================================
print("\nGenerating predictions for the entire dataset to build the Static DB...")

# Predict on the FULL dataset (X contains all cleaned features)
all_preds_log = model.predict(X)
all_preds_actual = np.expm1(all_preds_log)

# We use the original unclipped 'y_original' for actual price comparison in the bot
actual_prices = y_original.values

# Build the lookup dictionary
predictions_db = {}
for i in range(len(df_apartments)):
    url = str(listing_urls[i])
    listing_id = int(listing_ids[i])

    predicted_price = round(all_preds_actual[i], 0)
    actual_price = round(actual_prices[i], 0)

    # Calculate bargain score: How much cheaper is it compared to the model's prediction?
    if predicted_price > 0:
        bargain_score = round(((predicted_price - actual_price) / predicted_price) * 100, 1)
    else:
        bargain_score = 0.0

    # Determine alert level based on the bargain score
    if bargain_score >= 15:
        alert_level = "very_cheap"
    elif bargain_score >= 10:
        alert_level = "below_market"
    else:
        alert_level = "none"

    predictions_db[url] = {
        "id": listing_id,
        "url": url,
        "predicted_price": int(predicted_price),
        "actual_price": int(actual_price),
        "bargain_score": bargain_score,
        "alert_level": alert_level,
        # Extra features to help the bot format the Telegram message easily
        "area": float(df_apartments.iloc[i]['Area']),
        "rooms": int(float(df_apartments.iloc[i]['Rooms'])) if pd.notna(df_apartments.iloc[i]['Rooms']) else 0,
        "district": str(df_apartments.iloc[i]['District'])
    }

# Save to JSON file in the same directory as the script (model folder)
script_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(script_dir, 'predictions.json')

with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(predictions_db, f, ensure_ascii=False, indent=4)

print(f"✅ Successfully saved {len(predictions_db)} predictions to {json_path}")
