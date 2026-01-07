from playwright.sync_api import sync_playwright
import time
import random
import json
import os
import re

# === 配置区域 ===
KEYWORD = "GNNExplainer"
TARGET_COUNT = 300                      # 目标数量
PROXY_SERVER = "http://127.0.0.1:2011"  
JSON_FILENAME = "2-ScholarResearch/output/1-raw_data.json"
# ==============

def extract_details(page, url):
    """ 详情页提取逻辑 """
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
    """ 
    专门用于【阶段1：列表页】的强力拦截 
    只有在 Google 列表页被封时才暂停，因为列表页必须解封才能继续
    """
    try:
        title = page.title().lower()
        if "robot" in title or "unusual traffic" in page.inner_text("body").lower():
            print("\n🚨🚨🚨 Google 列表页被锁！必须人工介入！")
            print("👉 请在浏览器手动过验证。")
            input("✅ 完成后按【回车】继续...")
            return True
    except: pass
    return False

def is_target_captcha(page):
    """
    专门用于【阶段2：详情页】的检测
    只返回 True/False，不暂停程序
    """
    try:
        title = page.title().lower()
        body = page.inner_text("body").lower()
        # 常见验证码特征词
        if "just a moment" in title or "verify you are human" in title or "captcha" in body or "are you a robot" in body:
            return True
    except: pass
    return False

def run():
    USER_DATA_DIR = os.path.join(os.getcwd(), "user_data_browser") 
    task_list = [] 

    with sync_playwright() as p:
        print(f"🚀 启动浏览器...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False, 
            proxy={"server": PROXY_SERVER},
            args=['--disable-blink-features=AutomationControlled'], 
            viewport={"width": 1600, "height": 900},
        )
        page = context.pages[0]

        # ==========================================
        # 阶段 1: 扫描列表页 (必须保证成功，否则暂停)
        # ==========================================
        print(f"\n======== 阶段 1: 扫描列表页 (目标: {TARGET_COUNT} 篇) ========")
        
        current_offset = 0
        while len(task_list) < TARGET_COUNT:
            list_url = f"https://scholar.google.com/scholar?q={KEYWORD.replace(' ', '+')}&start={current_offset}"
            print(f"📖 扫描第 {current_offset//10 + 1} 页 (进度 {len(task_list)}/{TARGET_COUNT})...")
            
            retry = 0
            while retry < 3:
                try:
                    page.goto(list_url, timeout=60000)
                    check_google_captcha_blocking(page) # 这里如果被封，会暂停等你修
                    page.wait_for_selector("div.gs_r", timeout=30000)
                    break
                except:
                    print("   ⚠️ 列表页加载慢，重试中...")
                    retry += 1
                    time.sleep(3)
            
            cards = page.query_selector_all("div.gs_r.gs_or.gs_scl")
            if not cards: break

            new_cnt = 0
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
                        
                        task_list.append({"title": title_el.inner_text(), "url": url, "venue": venue, "year": year, "raw_info": raw_info})
                        new_cnt += 1
            
            print(f"   ✅ 新增 {new_cnt} 条")
            current_offset += 10
            time.sleep(random.uniform(2, 5)) # 列表页翻页必须休息

        # ==========================================
        # 阶段 2: 深度抓取 (遇到验证码直接跳过)
        # ==========================================
        print(f"\n======== 阶段 2: 深度抓取 (自动跳过验证码) ========")
        final_results = []
        
        for i, task in enumerate(task_list):
            print(f"👉 [{i+1}/{len(task_list)}] {task['title'][:20]}...")
            abstract, doi = "未找到", "未找到"
            
            try:
                # 缩短超时时间，如果卡住直接算跳过
                page.goto(task['url'], timeout=15000, wait_until="domcontentloaded")
                time.sleep(random.uniform(1.5, 3))
                
                # 【核心修改】：检测是否是验证码页面
                if is_target_captcha(page):
                    print(f"   💨 触发验证码拦截，自动跳过 (SKIP)")
                    abstract = "验证码拦截 (已跳过)"
                else:
                    abstract, doi = extract_details(page, task['url'])
                    print(f"   📝 摘要: {len(abstract)}字 | DOI: {doi}")

            except Exception as e:
                print(f"   ❌ 访问异常: {str(e)[:20]} (已跳过)")
                abstract = "访问异常"
            
            final_results.append({**task, "doi": doi, "abstract": abstract})
            
            if (i + 1) % 20 == 0:
                with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
                    json.dump(final_results, f, ensure_ascii=False, indent=4)
                print("   💾 自动保存...")

        context.close()

    if final_results:
        with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=4)
        print(f"\n🎉 完成！结果已保存: {JSON_FILENAME}")

if __name__ == "__main__":
    run()