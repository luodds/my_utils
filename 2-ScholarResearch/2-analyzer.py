import json
import pandas as pd
import time
import re
from deep_translator import GoogleTranslator
import matplotlib.pyplot as plt
from tqdm import tqdm  # 【新增】引入进度条库

# === 配置区域 ===
INPUT_FILE = "2-ScholarResearch/output/1-raw_data.json"  
OUTPUT_FILE = "2-ScholarResearch/output/2-analysis_report.xlsx" 

# 【代理设置】
PROXY_URL = "http://127.0.0.1:2011" 
PROXIES = {
    "http": PROXY_URL,
    "https": PROXY_URL
}
# ==============

# 初始化 tqdm 的 pandas 适配器
tqdm.pandas() 

# === 1. 期刊评级逻辑 ===
def rate_venue(venue_text):
    if not isinstance(venue_text, str):
        return "未知", "未知"
    
    venue_lower = venue_text.lower()
    clean_name = venue_text
    try:
        parts = venue_text.split(" - ")
        if len(parts) >= 2:
            clean_name = parts[-2]
            clean_name = re.sub(r'\d{4}', '', clean_name).strip().strip(',')
    except: pass

    level = "普通"
    # 简单的关键词匹配规则
    if "ieee trans" in venue_lower or "acm trans" in venue_lower:
        level = "顶刊 (Trans)"
    elif "nature" in venue_lower or "science" in venue_lower:
        level = "神刊 (Nature/Science)"
    elif any(x in venue_lower for x in ["cvpr", "iccv", "eccv", "neurips", "icml", "aaai", "ijcai", "sigcomm", "infocom"]):
        level = "顶会 (CCF A/B)"
    elif "ieee" in venue_lower or "acm" in venue_lower or "springer" in venue_lower or "elsevier" in venue_lower:
        level = "核心期刊/会议"
    elif "arxiv" in venue_lower:
        level = "预印本 (ArXiv)"

    return clean_name, level

# === 2. 翻译函数 ===
def translate_text(text, target='zh-CN'):
    """
    调用 Google 翻译 API (带代理)
    """
    if not text or len(text) < 5 or text == "未找到":
        return ""
    
    try:
        # 实例化翻译器
        translator = GoogleTranslator(source='auto', target=target, proxies=PROXIES)
        
        # 截断过长文本
        result = translator.translate(text[:4000])
        
        # 稍微休息一下，防止请求过快 (配合进度条，这里可以设小一点)
        time.sleep(0.2) 
        return result
        
    except Exception as e:
        return "[翻译出错]"

def run_analysis():
    print(f"🚀 读取数据: {INPUT_FILE} ...")
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ 找不到文件！")
        return

    df = pd.DataFrame(data)
    print(f"✅ 成功加载 {len(df)} 条数据")

    # --- 数据清洗与评级 ---
    print("\nProcessing... 正在清洗期刊名称并评级...")
    df[['Clean_Venue', 'Level']] = df['venue'].apply(lambda x: pd.Series(rate_venue(x)))

    # --- 翻译模块 ---
    print("\nTranslating... 正在翻译 (已配置代理: 127.0.0.1:2011)...")
    
    # 选取数据 (如果要全量跑，保持下面这行)
    df_subset = df.copy() 
    # df_subset = df.head(10).copy() # 测试用
    
    total = len(df_subset)
    print(f"计划翻译 {total} 条数据，请查看下方进度条：")

    # 【核心修改】将 .apply() 换成 .progress_apply()
    
    print("\n1. 正在翻译标题:")
    df_subset['标题(中文)'] = df_subset['title'].progress_apply(lambda x: translate_text(x))
    
    print("\n2. 正在翻译摘要:")
    df_subset['摘要(中文)'] = df_subset['abstract'].progress_apply(lambda x: translate_text(x))

    # --- 导出 Excel ---
    print("\nSaving... 正在保存 Excel...")
    cols = ['title', '标题(中文)', 'Level', 'Clean_Venue', 'year', 'doi', 'url', 'abstract', '摘要(中文)']
    final_cols = [c for c in cols if c in df_subset.columns]
    
    try:
        df_subset[final_cols].to_excel(OUTPUT_FILE, index=False)
        print(f"🎉 大功告成！结果已保存至: {OUTPUT_FILE}")
        
        # 尝试生成图表
        year_counts = df['year'].value_counts().sort_index()
        year_counts = year_counts[year_counts.index.str.match(r'^\d{4}$', na=False)]
        if not year_counts.empty:
            plt.figure(figsize=(10, 6))
            year_counts.plot(kind='bar', color='skyblue')
            plt.title('Paper Publication Trend')
            plt.savefig('2-ScholarResearch/output/3-trend_chart.png')
            print("📊 图表已生成: 2-ScholarResearch/output/3-trend_chart.png")
            
    except Exception as e:
        print(f"❌ 保存失败 (请检查 Excel 是否被打开): {e}")

if __name__ == "__main__":
    run_analysis()