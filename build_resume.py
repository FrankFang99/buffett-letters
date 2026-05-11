#!/usr/bin/env python3
"""断点续传构建脚本：每次处理N年，支持从断点恢复"""
import sys, os, json, time
sys.path.insert(0, '/workspace')

from build_static_v2 import (
    SOURCES, process_year_content, generate_letter_html,
    generate_empty_year, generate_index_html, load_cache, save_cache,
    LETTERS_DIR, OUTPUT_DIR, FINANCIAL_FILE
)

BATCH_SIZE = 6  # 每批处理6年
STATUS_FILE = '/workspace/build_status.json'

def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE) as f:
            return json.load(f)
    return {'processed': [], 'generated': []}

def save_status(st):
    with open(STATUS_FILE, 'w') as f:
        json.dump(st, f)

def main():
    print("="*50, flush=True)
    print("巴菲特股东信构建 v4 (断点续传)", flush=True)
    print("="*50, flush=True)
    
    cache = load_cache()
    print(f"缓存: {len(cache)} 条", flush=True)
    
    fd = {}
    if os.path.exists(FINANCIAL_FILE):
        with open(FINANCIAL_FILE, 'r', encoding='utf-8') as f:
            fd = json.load(f)
    
    os.makedirs(LETTERS_DIR, exist_ok=True)
    
    status = load_status()
    processed = set(status['processed'])
    generated = set(status['generated'])
    
    sy = sorted(SOURCES.keys())
    yw = set()
    yd = {}
    
    # 第一遍：处理内容（跳过已处理的）
    todo = [y for y in sy if y not in processed]
    print(f"待处理内容: {len(todo)} 年", flush=True)
    
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i+BATCH_SIZE]
        for year in batch:
            print(f"  处理 {year}...", flush=True)
            try:
                content = process_year_content(year, cache, fd)
                if content:
                    status['processed'].append(year)
                    yd[year] = len(content)
                    yw.add(year)
            except Exception as e:
                print(f"  {year} 错误: {e}", flush=True)
            save_cache(cache)
            save_status(status)
        print(f"  批次完成，已处理 {len(status['processed'])}/{len(sy)} 年", flush=True)
    
    # 第二遍：生成HTML（跳过已生成的）
    all_years = set(range(1977, 2025))
    todo_gen = [y for y in sorted(all_years) if y not in generated]
    print(f"\n待生成HTML: {len(todo_gen)} 年", flush=True)
    
    for i in range(0, len(todo_gen), BATCH_SIZE):
        batch = todo_gen[i:i+BATCH_SIZE]
        for year in batch:
            if year in yd:
                # 需要重新加载content（因为缓存可能已更新）
                content = process_year_content(year, cache, fd)
                if content:
                    html = generate_letter_html(year, content, cache, fd, yw)
                    print(f"  [{year}] ✓", flush=True)
                else:
                    html = generate_empty_year(year, yw)
            else:
                html = generate_empty_year(year, yw)
            
            with open(os.path.join(LETTERS_DIR, f"{year}.html"), 'w', encoding='utf-8') as f:
                f.write(html)
            status['generated'].append(year)
            save_status(status)
        print(f"  批次完成，已生成 {len(status['generated'])}/{len(all_years)} 年", flush=True)
    
    # 生成首页
    print("\n生成首页...", flush=True)
    with open(os.path.join(OUTPUT_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(generate_index_html(yd, fd))
    
    print(f"完成! {len(yw)}年, {sum(yd.values())}段", flush=True)
    
    # 清理状态文件
    if os.path.exists(STATUS_FILE):
        os.remove(STATUS_FILE)

if __name__ == '__main__':
    main()
