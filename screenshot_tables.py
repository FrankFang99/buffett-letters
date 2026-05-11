#!/usr/bin/env python3
"""从HTML源文件中截取复杂表格（pre_table）的图片"""
import sys, os, json, re, base64
sys.path.insert(0, '/workspace')

from build_static_v2 import parse_html_source, SOURCES, BASE_DIR
from bs4 import BeautifulSoup

OUTPUT_DIR = '/workspace/巴菲特分享版/images'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def html_to_image(html_content, width=800):
    """用Playwright将HTML渲染为图片"""
    from playwright.sync_api import sync_playwright
    
    # 创建完整的HTML页面
    full_html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
body {{ margin: 10px; padding: 0; background: white; font-family: "Courier New", monospace; font-size: 13px; }}
pre {{ white-space: pre; font-size: 13px; line-height: 1.4; }}
</style></head>
<body>{html_content}</body></html>'''
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': width, 'height': 100})
        page.set_content(full_html)
        # 获取内容高度
        height = page.evaluate('document.body.scrollHeight')
        page.set_viewport_size({'width': width, 'height': height + 20})
        img_bytes = page.screenshot(full_page=True)
        browser.close()
        return img_bytes

def extract_pre_table_html(source_file, year):
    """从源文件中提取pre_table对应的原始HTML"""
    with open(source_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    soup = BeautifulSoup(content, 'html.parser')
    for t in soup(['script', 'style', 'noscript']): t.decompose()
    
    # 获取所有pre标签的文本
    pre_tags = soup.find_all('pre')
    if not pre_tags:
        return []
    
    text = pre_tags[0].get_text(separator='\n')
    paragraphs = re.split(r'\n\s*\n', text)
    
    images = []
    img_idx = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para or len(para) < 15: continue
        
        lines = para.split('\n')
        dot_lines = [l for l in lines if ' . ' in l or '....' in l or
                     (re.match(r'^\s*[\d,]+\s', l) and
                      (re.search(r'\$[\s\d,]+', l) or re.search(r'\.{3,}', l) or
                       re.search(r'\s{3,}\S', l) or len(re.findall(r'[\d,]+', l)) >= 3))]
        indented_lines = [l for l in lines if re.match(r'^\s{2,}', l) and re.search(r'\d', l)]
        deep_indented = [l for l in lines if re.match(r'^\s{4,}', l) and l.strip()]
        has_equity = ('Shares' in para and 'Company' in para) or ('Cost' in para and 'Market' in para)
        is_complex = (len(indented_lines) >= 3 and len(deep_indented) >= 2 
                      and len(dot_lines) >= 3 and not has_equity)
        
        # 也检查Net Earnings等关键词
        table_header_kws = ['Net Earnings', 'Earnings Before', 'Income Taxes', 'After Tax', 'Berkshire Share']
        has_table_header = any(kw in para for kw in table_header_kws)
        
        if is_complex or (has_table_header and len(lines) >= 5):
            # 检查下一个段落是否应该合并
            all_paragraphs = re.split(r'\n\s*\n', text)
            pi = None
            for i, p in enumerate(all_paragraphs):
                if p.strip() == para:
                    pi = i
                    break
            
            full_text = para
            if pi is not None and pi + 1 < len(all_paragraphs):
                next_para = all_paragraphs[pi + 1].strip()
                next_lines = next_para.split('\n')
                next_dot = [l for l in next_lines if ' . ' in l or '....' in l or
                            (re.match(r'^\s*[\d,]+\s', l) and
                             (re.search(r'\$[\s\d,]+', l) or re.search(r'\.{3,}', l) or
                              re.search(r'\s{3,}\S', l) or len(re.findall(r'[\d,]+', l)) >= 3))]
                if len(next_dot) >= 3:
                    full_text = para + '\n' + next_para
            
            # 生成图片
            pre_html = f'<pre>{full_text}</pre>'
            try:
                img_bytes = html_to_image(pre_html)
                img_filename = f'table_{year}_{img_idx}.png'
                img_path = os.path.join(OUTPUT_DIR, img_filename)
                with open(img_path, 'wb') as f:
                    f.write(img_bytes)
                images.append({
                    'filename': img_filename,
                    'text_preview': full_text[:80]
                })
                img_idx += 1
                print(f"  截图: {img_filename} ({len(img_bytes)} bytes)")
            except Exception as e:
                print(f"  截图失败: {e}")
    
    return images

# 处理所有HTML源文件年份
all_images = {}
for year in sorted(SOURCES.keys()):
    source = SOURCES[year]
    fp = os.path.join(BASE_DIR, source)
    if not os.path.exists(fp): continue
    if not source.endswith('.html'): continue
    
    # 检查是否有pre_table
    try:
        blocks = parse_html_source(fp)
        has_pre = any(b['type'] == 'pre_table' for b in blocks)
        if not has_pre:
            continue
    except:
        continue
    
    print(f"\n{year}: 处理pre_table...")
    images = extract_pre_table_html(fp, year)
    if images:
        all_images[year] = images

# 保存图片映射
with open('/workspace/table_images.json', 'w') as f:
    json.dump(all_images, f, ensure_ascii=False, indent=2)

print(f"\n完成! 共截取 {sum(len(v) for v in all_images.values())} 张表格图片")
print(f"涉及 {len(all_images)} 个年份")
