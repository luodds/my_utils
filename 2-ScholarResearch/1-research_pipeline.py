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

# ==============================================================================
#                               核心配置区域
# ==============================================================================

# 1. 搜索设置

# KEYWORDS = [
#     "Few-shot learning",
#     "Supervised Contrastive Learning",
#     "Prompt Tuning",
#     "5G Core Network",
#     "Threat Detection",
#     "Traffic Classification",
#     "Encrypted Traffic Analysis",
#     "Prompt-based Learning"
# ]

KEYWORDS = [
    "5G-NIDD"
]

TARGET_COUNT_PER_KEYWORD = 100   # 🎯 每个关键词想要抓取的数量

# 2. 网络与代理设置
# 注意：如果你的代理不需要，请将 PROXY_SERVER 设为 None
PROXY_SERVER = "http://127.0.0.1:7897"   
PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if PROXY_SERVER else None

# 3. 输出路径设置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
RAW_DATA_FILE = os.path.join(OUTPUT_DIR, 'multi_keyword_data.json')
REPORT_FILE = os.path.join(OUTPUT_DIR, 'multi_keyword_report.xlsx')
CHART_FILE = os.path.join(OUTPUT_DIR, 'multi_keyword_chart.png')

# 自动创建浏览器缓存目录，用于保存登录状态
USER_DATA_DIR = os.path.join(os.getcwd(), "user_data_browser")

# 4. 其他爬虫参数
TIMEOUT_MS = 60000          # 页面加载超时时间
MIN_SLEEP = 2.0             # 最小间隔(秒)
MAX_SLEEP = 5.0             # 最大间隔(秒)

# 确保输出目录存在
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# ==============================================================================
#                  模块 1: 辅助函数 (提取、检测、翻译)
# ==============================================================================

def extract_details(page, url):
    """ 
    增强版详情提取：支持 ArXiv, CVF, NeurIPS, Springer, ACM, IEEE 等主流来源 
    """
    domain = url.lower()
    content = ""
    doi = ""
    
    # --- 1. DOI 提取逻辑 ---
    try:
        doi_selectors = [
            'meta[name="citation_doi"]', 'meta[name="dc.identifier"]', 
            'meta[name="prism.doi"]', 'meta[property="og:url"]'
        ]
        for sel in doi_selectors:
            meta = page.query_selector(sel)
            if meta:
                val = meta.get_attribute("content")
                if val and "10." in val:
                    match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', val, re.IGNORECASE)
                    if match: 
                        doi = match.group(1)
                        break
        if not doi:
            match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', url, re.IGNORECASE)
            if match: doi = match.group(1)
    except: pass

    # --- 2. 摘要提取逻辑 ---
    try:
        if "arxiv.org" in domain:
            elem = page.query_selector("blockquote.abstract")
            if elem: content = elem.inner_text().replace("Abstract:", "").strip()
        elif "thecvf.com" in domain:
            elem = page.query_selector("div#abstract")
            if elem: content = elem.inner_text().strip()
        elif "proceedings.neurips.cc" in domain or "proceedings.mlr.press" in domain:
            elem = page.query_selector("div.abstract, .abstract-container, p.abstract")
            if not elem:
                try: content = page.locator("h4:text('Abstract') + p").inner_text()
                except: pass
            else: content = elem.inner_text()
        elif "springer.com" in domain or "nature.com" in domain:
            elem = page.query_selector("#Abs1-content, .c-article-section__content, .abstract-content")
            if elem: content = elem.inner_text()
        elif "sciencedirect.com" in domain:
            elem = page.query_selector("div.abstract.author, div#abstracts")
            if elem: content = elem.inner_text()
        elif "ieee.org" in domain:
            elem = page.query_selector("div.abstract-text, div.u-mb-1 div")
            if elem: 
                text = elem.inner_text().strip()
                if text.lower().startswith("abstract"): text = text[8:].strip(" :")
                content = text
        elif "acm.org" in domain:
            elem = page.query_selector(".abstractSection, div[role='paragraph']")
            if elem: content = elem.inner_text()
        elif "openreview.net" in domain:
            elem = page.query_selector("span.note-content-value")
            if elem: content = elem.inner_text()

        # --- 3. 通用兜底 ---
        if not content or len(content) < 50:
            meta_desc = page.query_selector('meta[name="description"]') or page.query_selector('meta[property="og:description"]')
            if meta_desc:
                desc_text = meta_desc.get_attribute('content').strip()
                if len(desc_text) > 50 and "10." not in desc_text[:20]: content = desc_text
            
            if not content:
                try:
                    body_text = page.inner_text("body")
                    idx = body_text.find("Abstract")
                    if idx != -1:
                        snippet = body_text[idx:idx+1500]
                        lines = [line.strip() for line in snippet.split('\n') if len(line.strip()) > 50]
                        if lines: content = lines[0]
                except: pass

    except Exception as e:
        print(f"Error parsing {url}: {e}")

    # --- 4. 清洗 ---
    if content:
        content = re.sub(r'\s+', ' ', content).strip()
        if content.lower().startswith("abstract"): content = content[8:].strip(" :-")
            
    if len(content) < 20 or content.startswith("http") or content.startswith("10."):
        content = "未找到有效摘要"

    return content, doi

def check_google_captcha_blocking(page):
    """ Google 反爬拦截检测 """
    try:
        if "/sorry/" in page.url: is_blocked = True
        else:
            text = page.inner_text("body").lower()
            is_blocked = "unusual traffic" in text or "异常流量" in text or "robot" in page.title().lower()

        if is_blocked:
            print("\n🚨🚨🚨 触发 Google 拦截！(检测到异常流量)")
            print("1. 请在自动打开的浏览器中手动完成验证码。")
            print("2. 完成后，请在终端按【回车】继续程序。")
            page.bring_to_front() # 把页面置顶
            input() 
            return True
    except: pass
    return False

def is_target_captcha(page):
    """ 目标论文网站的反爬检测 (Cloudflare等) """
    try:
        title = page.title().lower()
        body = page.inner_text("body").lower()
        if "just a moment" in title or "verify you are human" in title or "captcha" in body:
            return True
    except: pass
    return False

def rate_venue(venue_text):
    """ 期刊评级 """
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
    """ 谷歌翻译 """
    if not text or len(text) < 5 or text == "未找到" or text == "未找到有效摘要": return ""
    try:
        translator = GoogleTranslator(source='auto', target=target, proxies=PROXIES)
        res = translator.translate(text[:4000])
        time.sleep(0.2)
        return res
    except: return "[翻译出错]"

# ==============================================================================
#                  模块 2: 核心爬虫控制流程
# ==============================================================================

def run_multi_keyword_spider():
    print(f"\n🚀 [阶段 1/3] 正在启动独立浏览器实例...")
    print(f"📋 待抓取关键词列表: {KEYWORDS}")
    
    global_task_list = [] 
    seen_urls = set()     

    with sync_playwright() as p:
        # ==================== 修改部分：自动启动浏览器 ====================
        try:
            # 准备启动参数
            launch_args = [
                "--disable-blink-features=AutomationControlled", # 隐藏自动化特征
                "--no-sandbox",
                "--disable-infobars",
                "--start-maximized" # 最大化窗口
            ]
            
            # 配置代理 (如果设置了)
            proxy_config = {"server": PROXY_SERVER} if PROXY_SERVER else None

            print(f"   📂 使用用户数据目录: {USER_DATA_DIR}")
            
            # 使用 launch_persistent_context 启动一个持久化的浏览器上下文
            # 这样可以保存你的登录状态 (Cookies)，减少验证码
            context = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False,  # 必须为 False 才能看到界面
                proxy=proxy_config,
                args=launch_args,
                viewport=None # 禁用默认视口大小，跟随窗口
            )
            
            # 获取第一个页面
            page = context.pages[0] if context.pages else context.new_page()
            print("   ✅ 浏览器启动成功！")
            
            # 可以在这里注入一段 JS 去除 webdriver 特征
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """)

        except Exception as e:
            print(f"   ❌ 启动失败: {e}")
            return []
        # ===============================================================

        # 2. 访问 Google Scholar
        print("   🔍 正在访问 Google Scholar...")
        try:
            page.goto("https://scholar.google.com", timeout=TIMEOUT_MS)
            
            # 检测是否被拦截
            if check_google_captcha_blocking(page):
                pass # 已经在函数里 wait for input 了
            
            # 检查是否登录（可选）
            if page.query_selector("a#gs_hdr_act_s"):
                print("   👉 提示: 你当前似乎【未登录】Google 账号。建议登录以获取更多搜索结果。")
            else:
                print("   👤 检测到已登录状态 (Cookies生效中)")

        except Exception as e:
            print(f"   ⚠️  访问警告: {e}")

        # ================= LOOP 1: 遍历所有关键词 (抓取列表) =================
        print(f"\n🌊 [子阶段 A] 开始遍历关键词...")
        
        for kw_index, keyword in enumerate(KEYWORDS):
            print(f"\n   👉 ({kw_index+1}/{len(KEYWORDS)}) 正在搜索: [{keyword}]")
            
            current_kw_count = 0
            current_offset = 0
            
            while current_kw_count < TARGET_COUNT_PER_KEYWORD:
                list_url = f"https://scholar.google.com/scholar?q={keyword.replace(' ', '+')}&start={current_offset}"
                
                retry = 0
                while retry < 3:
                    try:
                        page.goto(list_url, timeout=TIMEOUT_MS)
                        # 检测验证码
                        if check_google_captcha_blocking(page):
                            pass 
                        page.wait_for_selector("div.gs_r", timeout=30000)
                        break
                    except:
                        retry += 1
                        time.sleep(3)
                
                cards = page.query_selector_all("div.gs_r.gs_or.gs_scl")
                if not cards: 
                    print("      ⚠️  未找到更多结果卡片，结束当前关键词搜索。")
                    break

                exclude_ext = ('.pdf', '.gz', '.ps', '.zip')
                
                new_items_on_page = 0
                for item in cards:
                    if current_kw_count >= TARGET_COUNT_PER_KEYWORD: break
                    link_el = item.query_selector("h3.gs_rt a")
                    title_el = item.query_selector("h3.gs_rt")
                    pub_el = item.query_selector("div.gs_a")
                    
                    if link_el and title_el:
                        url = link_el.get_attribute("href")
                        if url and url.startswith("http") and not url.lower().endswith(exclude_ext):
                            if url in seen_urls: continue
                            seen_urls.add(url)
                            
                            venue, year = "Unknown", "Unknown"
                            raw_info = pub_el.inner_text() if pub_el else ""
                            try:
                                parts = raw_info.split(" - ")
                                if len(parts) >= 2:
                                    venue = parts[-2]
                                    year_match = re.search(r'\b(19|20)\d{2}\b', venue)
                                    if year_match: year = year_match.group(0)
                            except: pass
                            
                            global_task_list.append({
                                "keyword": keyword,
                                "title": title_el.inner_text(), 
                                "url": url, 
                                "venue": venue, 
                                "year": year
                            })
                            current_kw_count += 1
                            new_items_on_page += 1

                print(f"      ---> 本页新增: {new_items_on_page} | 进度: {current_kw_count}/{TARGET_COUNT_PER_KEYWORD}")
                current_offset += 10
                if current_kw_count < TARGET_COUNT_PER_KEYWORD:
                    sleep_time = random.uniform(3, 6)
                    time.sleep(sleep_time)
            
            time.sleep(random.uniform(4, 8))

        print(f"\n📋 列表采集完毕！共 {len(global_task_list)} 篇。")

        # ================= LOOP 2: 遍历任务池 (抓取详情) =================
        print(f"\n🕵️  [子阶段 B] 开始深度抓取详情...")
        
        final_results = []
        
        # 使用 tqdm 显示总进度
        for index, task in enumerate(tqdm(global_task_list, desc="Deep Crawling")):
            abstract, doi = "未找到", "未找到"
            try:
                page.goto(task['url'], timeout=45000, wait_until="domcontentloaded")
                time.sleep(random.uniform(2.0, 4.0)) 
                
                if is_target_captcha(page):
                    abstract = "验证码拦截 (已跳过)"
                else:
                    abstract, doi = extract_details(page, task['url'])
            except Exception:
                abstract = "访问异常"
            
            # 将结果加入列表
            task_result = {**task, "doi": doi, "abstract": abstract}
            final_results.append(task_result)

            # 每爬 10 篇自动保存
            if (index + 1) % 10 == 0:
                try:
                    with open(RAW_DATA_FILE, 'w', encoding='utf-8') as f:
                        json.dump(final_results, f, ensure_ascii=False, indent=4)
                except: pass

        # 关闭浏览器上下文
        try:
            context.close()
        except: pass
        
    return final_results

# ==============================================================================
#                  模块 3: 数据分析与翻译
# ==============================================================================

def run_analyzer_module(data_list):
    print(f"\n📊 [阶段 2/3] 启动数据处理与翻译...")
    
    if not data_list:
        print("❌ 没有数据可供分析！")
        return

    df = pd.DataFrame(data_list)
    
    # 1. 评级
    print("   🏷️  正在进行期刊分级...")
    df[['Clean_Venue', 'Level']] = df['venue'].apply(lambda x: pd.Series(rate_venue(x)))

    # 2. 翻译 (带进度条)
    print("   🌍 正在翻译标题与摘要 (调用 Google API)...")
    # 如果没有配置代理，且国内网络环境差，这里可能会报错
    tqdm.pandas(desc="Translating")
    df['标题(中文)'] = df['title'].progress_apply(lambda x: translate_text(x))
    df['摘要(中文)'] = df['abstract'].progress_apply(lambda x: translate_text(x))

    # 3. 整理列顺序
    cols = ['keyword', 'title', '标题(中文)', 'Level', 'Clean_Venue', 'year', 'doi', 'url', 'abstract', '摘要(中文)']
    final_cols = [c for c in cols if c in df.columns]
    
    # 4. 保存
    try:
        # 保存原始 JSON
        with open(RAW_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=4)
            
        # 保存 Excel
        df[final_cols].to_excel(REPORT_FILE, index=False)
        print(f"   💾 数据已保存:\n      -> Excel: {REPORT_FILE}\n      -> JSON:  {RAW_DATA_FILE}")
    except Exception as e:
        print(f"   ❌ 保存失败: {e}")

    # 5. 简单绘图
    try:
        if not df.empty:
            plt.figure(figsize=(12, 6))
            # 统计各个关键词的年份分布
            df_filtered = df[df['year'].astype(str).str.match(r'^\d{4}$')]
            if not df_filtered.empty:
                df_filtered.groupby(['year', 'keyword']).size().unstack().plot(kind='bar', stacked=True)
                plt.title('Paper Count by Year & Keyword')
                plt.savefig(CHART_FILE)
                print(f"   📊 统计图表已生成: {CHART_FILE}")
    except Exception as e: 
        print(f"绘图跳过: {e}")

# ==============================================================================
#                  主程序入口
# ==============================================================================

if __name__ == "__main__":
    print("="*60)
    print(f"🚀  Advanced Multi-Keyword Scholar Pipeline (Auto-Launch)")
    print(f"📂  Working Dir: {BASE_DIR}")
    print("="*60)
    
    # 1. 执行爬虫 (列表 -> 详情)
    raw_data = run_multi_keyword_spider()
    
    # 2. 执行分析 (翻译 -> 报表)
    if raw_data:
        run_analyzer_module(raw_data)
    
    print("\n🎉🎉🎉 全流程任务完成！")