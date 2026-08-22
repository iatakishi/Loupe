import pandas as pd
import numpy as np
from catboost import CatBoostRegressor
from sklearn.model_selection import KFold
from sklearn.metrics import mean_absolute_percentage_error

# ============================================
# 1. MOCK DATA (Əvvəlki kimidir)
# ============================================
np.random.seed(42)
n_samples = 1000

mock_data = {
    'room_count': np.random.randint(1, 6, n_samples),
    'area_sqm': np.random.randint(30, 250, n_samples),
    'floor': np.random.randint(1, 20, n_samples),
    'district': np.random.choice(['Yasamal', 'Nasimi', 'Narimanov', 'Binagadi', 'Khatai'], n_samples),
    'renovation': np.random.choice(['Yaxshi', 'Orta', 'Temirsiz'], n_samples),
    'price_azn': np.random.randint(50000, 500000, n_samples)
}
df = pd.DataFrame(mock_data)

features = ['room_count', 'area_sqm', 'floor', 'district', 'renovation']
X = df[features]
y = df['price_azn']
cat_features = ['district', 'renovation']

# ============================================
# 2. K-FOLD CROSS-VALIDATION (Əsas hissə)
# ============================================
# Datanı 5 hissəyə bölürük. 4 hissə ilə öyrədirik, 1 hissə ilə test edirik.
# Bunu 5 dəfə təkrarlayırıq (hər dəfə fərqli 1 hissə test olur).
kf = KFold(n_splits=5, shuffle=True, random_state=42)

fold_mape_scores = []

print("Cross-Validation başlayır (5 Fold)...")

for fold, (train_idx, val_idx) in enumerate(kf.split(X)):
    # Hər fold üçün data-nı bölürük
    X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
    y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

    # Hər fold üçün YENİ model yaradırıq (təmiz səhifə)
    model = CatBoostRegressor(
        iterations=100,
        learning_rate=0.1,
        depth=6,
        loss_function='MAE',
        cat_features=cat_features,
        verbose=0
    )

    # Öyrədirik və test edirik
    model.fit(X_train, y_train)
    y_pred = model.predict(X_val)

    # Xətanı ölçürük
    fold_mape = mean_absolute_percentage_error(y_val, y_pred) * 100
    fold_mape_scores.append(fold_mape)

    print(f"Fold {fold + 1} bitdi. MAPE: {fold_mape:.2f}%")

# ============================================
# 3. NƏTİCƏLƏRİN TƏHLİLİ
# ============================================
mean_mape = np.mean(fold_mape_scores)
std_mape = np.std(fold_mape_scores)

print("\n--- CROSS-VALIDATION NƏTİCƏSİ ---")
print(f"Orta MAPE (Mean): {mean_mape:.2f}%")
print(f"Standart Kənarlaşma (Std Dev): {std_mape:.2f}%")

if std_mape > 5:
    print("⚠️ XƏBƏRDARLIQ: Model qeyri-stabildir! Bəzi fold-larda çox səhv edir, bəzilərində yaxşı.")
else:
    print("✅ Model stabildir. Fərqli data qruplarında eyni performansı göstərir.")
