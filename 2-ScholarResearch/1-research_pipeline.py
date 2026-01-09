import os
import json
import time
import random
import re
import pandas as pd
from playwright.sync_api import sync_playwright
from deep_translator import GoogleTranslator
import matplotlib.pyplot as plt
from tqdm import tqdm

# ================= 核心配置区域 (只需改这里) =================

# 1. 搜索设置
KEYWORD = "Few-shot learning"    # 🔍 在这里修改你想搜索的关键词
TARGET_COUNT = 5               # 🎯 想要抓取的论文数量 (测试建议先填 20-50)

# 2. 网络与代理
PROXY_SERVER = "http://127.0.0.1:2011" # 🌐 你的本地代理地址
PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER}

# 3. 路径设置 (自动获取当前脚本所在目录)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
RAW_DATA_FILE = os.path.join(OUTPUT_DIR, '1-raw_data.json')
REPORT_FILE = os.path.join(OUTPUT_DIR, '1-analysis_report.xlsx')
CHART_FILE = os.path.join(OUTPUT_DIR, '1-trend_chart.png')
USER_DATA_DIR = os.path.join(os.getcwd(), "user_data_browser")

# 确保输出目录存在
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# ==========================================================
#                  模块 1: 爬虫逻辑 (Spider)
# ==========================================================

def extract_details(page, url):
    """ 详情页提取摘要和DOI """
    domain = url.lower()
    content = ""
    doi = ""
    try:
        # DOI 提取
        doi_meta = (page.query_selector('meta[name="citation_doi"]') or 
                    page.query_selector('meta[name="dc.identifier"]') or 
                    page.query_selector('meta[name="prism.doi"]'))
        if doi_meta: doi = doi_meta.get_attribute("content").strip()
        if not doi:
            doi_match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', url, re.IGNORECASE)
            if doi_match: doi = doi_match.group(1)

        # 摘要提取
        if "sciencedirect.com" in domain:
            try:
                script = page.eval_on_selector("script[type='application/ld+json']", "el => el.innerText")
                data = json.loads(script)
                if 'description' in data: content = data['description']
                if not doi and 'identifier' in data: doi = data['identifier']
            except: pass
            if not content:
                elem = page.query_selector("div.abstract") or page.query_selector("div[id^='abs']")
                if elem: content = elem.inner_text().strip()
        elif "ieee.org" in domain:
            try: page.wait_for_selector("div.abstract-text", timeout=3000)
            except: pass
            elem = page.query_selector("div.abstract-text")
            if elem: 
                text = elem.inner_text().strip()
                if text.lower().startswith("abstract"): text = text.split(":", 1)[-1].strip()
                content = text
        
        if not content:
            meta = page.query_selector('meta[name="description"]') or page.query_selector('meta[property="og:description"]')
            if meta: content = meta.get_attribute('content').strip()

    except Exception: pass
    return content, doi

def check_google_captcha_blocking(page):
    """ 列表页反爬检测 (已增强对中文和URL的检测) """
    try:
        # 1. 检查 URL 是否包含 /sorry/ (Google 拦截页的特征)
        if "/sorry/" in page.url:
            is_blocked = True
        else:
            # 2. 检查页面文字关键词
            text = page.inner_text("body").lower()
            is_blocked = "unusual traffic" in text or "异常流量" in text or "robot" in page.title().lower()

        if is_blocked:
            print("\n🚨🚨🚨 触发 Google 拦截！(检测到异常流量)")
            print("👇 动作指导：")
            print("1. 请在浏览器中查看是否有【验证码/复选框】。")
            print("2. 如果有，请手动点击并完成验证，直到看到正常的搜索列表。")
            print("3. 如果没有验证码（白屏或纯文字），说明 IP 被封，请更换代理节点或稍后再试。")
            print("waiting... (完成操作后，请在终端按【回车】继续)")
            
            # 这里的 input 会暂停程序，等你处理完浏览器
            input() 
            return True
    except: pass
    return False

def is_target_captcha(page):
    """ 详情页反爬检测 (自动跳过) """
    try:
        title = page.title().lower()
        body = page.inner_text("body").lower()
        if "just a moment" in title or "verify you are human" in title or "captcha" in body or "are you a robot" in body:
            return True
    except: pass
    return False

def run_spider_module():
    print(f"\n🕷️  [阶段 1/2] 启动爬虫 | 关键词: {KEYWORD}")
    task_list = [] 

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False, 
            proxy={"server": PROXY_SERVER},
            args=['--disable-blink-features=AutomationControlled'], 
            viewport={"width": 1600, "height": 900},
        )
        page = context.pages[0]

        # --- 子阶段 1: 列表扫描 ---
        current_offset = 0
        print(f"   📖 正在扫描列表页...")
        
        while len(task_list) < TARGET_COUNT:
            list_url = f"https://scholar.google.com/scholar?q={KEYWORD.replace(' ', '+')}&start={current_offset}"
            
            retry = 0
            while retry < 3:
                try:
                    page.goto(list_url, timeout=60000)
                    check_google_captcha_blocking(page)
                    page.wait_for_selector("div.gs_r", timeout=30000)
                    break
                except:
                    retry += 1
                    time.sleep(3)
            
            cards = page.query_selector_all("div.gs_r.gs_or.gs_scl")
            if not cards: break

            exclude = ('.pdf', '.gz', '.ps', '.zip')
            for item in cards:
                if len(task_list) >= TARGET_COUNT: break
                link_el = item.query_selector("h3.gs_rt a")
                title_el = item.query_selector("h3.gs_rt")
                pub_el = item.query_selector("div.gs_a")
                
                if link_el and title_el:
                    url = link_el.get_attribute("href")
                    if url and url.startswith("http") and not url.lower().endswith(exclude):
                        venue, year = "Unknown", "Unknown"
                        raw_info = pub_el.inner_text() if pub_el else ""
                        try:
                            parts = raw_info.split(" - ")
                            if len(parts) >= 2:
                                venue = parts[-2]
                                year_match = re.search(r'\b(19|20)\d{2}\b', venue)
                                if year_match: year = year_match.group(0)
                        except: pass
                        task_list.append({"title": title_el.inner_text(), "url": url, "venue": venue, "year": year})

            current_offset += 10
            print(f"      ---> 已收集: {len(task_list)}/{TARGET_COUNT}")
            if len(task_list) < TARGET_COUNT:
                time.sleep(random.uniform(2, 4))

        # --- 子阶段 2: 详情抓取 ---
        print(f"\n   🕵️  正在抓取详情 (摘要 & DOI)...")
        final_results = []
        
        # 使用 tqdm 显示进度
        for task in tqdm(task_list, desc="Deep Crawling"):
            abstract, doi = "未找到", "未找到"
            try:
                page.goto(task['url'], timeout=15000, wait_until="domcontentloaded")
                time.sleep(random.uniform(1.0, 2.5))
                
                if is_target_captcha(page):
                    abstract = "验证码拦截 (已跳过)"
                else:
                    abstract, doi = extract_details(page, task['url'])
            except Exception:
                abstract = "访问异常"
            
            final_results.append({**task, "doi": doi, "abstract": abstract})
        
        context.close()
    
    # 保存原始数据
    with open(RAW_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=4)
    print(f"   ✅ 爬虫结束，数据已保存至: {RAW_DATA_FILE}")
    return final_results

# ==========================================================
#                  模块 2: 分析逻辑 (Analyzer)
# ==========================================================

tqdm.pandas() 

def rate_venue(venue_text):
    """ 期刊评级逻辑 """
    if not isinstance(venue_text, str): return "未知", "未知"
    venue_lower = venue_text.lower()
    clean_name = venue_text
    try:
        parts = venue_text.split(" - ")
        if len(parts) >= 2:
            clean_name = parts[-2]
            clean_name = re.sub(r'\d{4}', '', clean_name).strip().strip(',')
    except: pass

    level = "普通"
    if "ieee trans" in venue_lower or "acm trans" in venue_lower: level = "顶刊 (Trans)"
    elif "nature" in venue_lower or "science" in venue_lower: level = "神刊"
    elif any(x in venue_lower for x in ["cvpr", "iccv", "eccv", "neurips", "icml", "aaai"]): level = "顶会 (CCF A)"
    elif "arxiv" in venue_lower: level = "预印本 (ArXiv)"

    return clean_name, level

def translate_text(text, target='zh-CN'):
    """ 翻译函数 """
    if not text or len(text) < 5 or text == "未找到": return ""
    try:
        translator = GoogleTranslator(source='auto', target=target, proxies=PROXIES)
        res = translator.translate(text[:4000])
        time.sleep(0.2)
        return res
    except: return "[翻译出错]"

def run_analyzer_module(data_list):
    print(f"\n📊 [阶段 2/2] 启动分析与翻译...")
    
    if not data_list:
        print("❌ 没有数据可供分析！")
        return

    df = pd.DataFrame(data_list)
    
    # 1. 评级
    print("   🏷️  正在进行期刊分级...")
    df[['Clean_Venue', 'Level']] = df['venue'].apply(lambda x: pd.Series(rate_venue(x)))

    # 2. 翻译 (带进度条)
    print("   🌍 正在翻译标题与摘要 (调用 Google API)...")
    print("      (如果卡住请检查代理是否稳定)")
    df['标题(中文)'] = df['title'].progress_apply(lambda x: translate_text(x))
    df['摘要(中文)'] = df['abstract'].progress_apply(lambda x: translate_text(x))

    # 3. 保存 Excel
    cols = ['title', '标题(中文)', 'Level', 'Clean_Venue', 'year', 'doi', 'url', 'abstract', '摘要(中文)']
    final_cols = [c for c in cols if c in df.columns]
    
    try:
        df[final_cols].to_excel(REPORT_FILE, index=False)
        print(f"   💾 Excel 报表已生成: {REPORT_FILE}")
    except Exception as e:
        print(f"   ❌ 保存 Excel 失败 (请关闭文件重试): {e}")

    # 4. 绘图
    try:
        year_counts = df['year'].value_counts().sort_index()
        year_counts = year_counts[year_counts.index.str.match(r'^\d{4}$', na=False)]
        if not year_counts.empty:
            plt.figure(figsize=(10, 6))
            year_counts.plot(kind='bar', color='skyblue')
            plt.title(f'Publication Trend: {KEYWORD}')
            plt.savefig(CHART_FILE)
            print(f"   📊 趋势图已生成: {CHART_FILE}")
    except: pass

# ==========================================================
#                  主程序入口
# ==========================================================

if __name__ == "__main__":
    print("="*50)
    print(f"🚀  Scholar Research Pipeline (One-Step)")
    print(f"📂  Root: {BASE_DIR}")
    print("="*50)
    
    # 步骤 1: 爬取数据
    raw_data = run_spider_module()
    
    # 步骤 2: 分析数据 (如果爬到了数据)
    if raw_data:
        run_analyzer_module(raw_data)
    
    print("\n🎉🎉🎉 全流程任务完成！请查看 output 目录。")