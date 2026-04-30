import pandas as pd

df = pd.read_excel(r"D:\yuwang\action\data\Object-Models-Updated.xlsx")
print(f"总行数: {len(df)}")
print(f"原有: 158, 新增: {len(df)-158}")
print()

new = df.iloc[158:]
print("=== 新增模型字段完整性检查 ===")
for col in df.columns:
    filled = new[col].notna().sum()
    total = len(new)
    pct = filled / total * 100
    print(f"  {col}: {filled}/{total} ({pct:.0f}%)")

print()
print("=== 无官网的模型（需后续补充）===")
no_url = new[new["官网"].isna()]
for _, r in no_url.iterrows():
    name = r["模型名称"]
    company = r["公司"] if pd.notna(r["公司"]) else "?"
    oc = r["开闭源"]
    print(f"  - {name} ({company}) [{oc}]")

print()
print("=== 无尺寸的开源模型（可能需要补充）===")
open_no_size = new[(new["开闭源"] == "开源") & (new["尺寸"].isna())]
for _, r in open_no_size.iterrows():
    name = r["模型名称"]
    company = r["公司"] if pd.notna(r["公司"]) else "?"
    print(f"  - {name} ({company})")

print()
print("=== 按公司统计 ===")
company_counts = new["公司"].value_counts()
for c, n in company_counts.items():
    print(f"  {c}: {n}个")
nan_count = new["公司"].isna().sum()
if nan_count:
    print(f"  未知公司: {nan_count}个")

print()
print("=== 按类型统计 ===")
for t, n in new["类型"].value_counts().items():
    print(f"  {t}: {n}个")

print()
print("=== 按开闭源统计 ===")
for o, n in new["开闭源"].value_counts().items():
    print(f"  {o}: {n}个")

print()
print("=== 有尺寸信息的模型 ===")
has_size = new[new["尺寸"].notna()]
for _, r in has_size.iterrows():
    print(f"  - {r['模型名称']}: {r['尺寸']}")
