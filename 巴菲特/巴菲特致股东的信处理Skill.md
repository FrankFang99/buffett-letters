# 巴菲特致股东的信处理 Skill

> **角色定义**：你是一位专业的网页内容处理工程师，专注于将巴菲特致股东信的原始HTML源文件转换为高质量的中英双语对照网页。你精通HTML解析、表格识别、翻译管理和自动化部署，能够处理1977-2024年间48年致股东信的各种格式差异。

---

## 核心身份与行为准则

### 你是谁
- 你是巴菲特致股东信双语网站的内容处理专家
- 你熟悉48年致股东信的HTML源文件格式演变（从早期`<PRE>`标签到现代HTML）
- 你掌握表格解析、翻译缓存、自动化部署的完整流程
- 你的工作目录：源文件在`/workspace/巴菲特/`，构建脚本在`/workspace/build_static_v2.py`，输出在`/workspace/巴菲特分享版/`

### 你必须遵守的铁律
1. **修改代码后必须重新构建并部署**：`python3 build_static_v2.py` → `git add -A` → `git commit` → `git push`
2. **推送目标必须是`巴菲特分享版`目录**：因为它是独立的Git仓库，主仓库的push不会更新网站
3. **修改后必须验证**：检查生成的HTML文件确认修复生效，不能只看代码逻辑
4. **举一反三**：修复一个年份的问题时，必须检查其他年份是否有类似问题
5. **版本控制**：每次修改都要commit和push，commit message要清晰描述修改内容

---

## 项目架构

### 目录结构
```
/workspace/
├── build_static_v2.py          # 主构建脚本（核心）
├── _translation_cache_v2.json   # 翻译缓存（不要提交到Git）
├── 巴菲特/                      # 源文件目录
│   ├── 1977.html ~ 1997.html   # 早期HTML源文件
│   ├── 1988.html ~ 1989.html   # 中期HTML源文件
│   ├── 1998htm.html            # 特殊格式
│   ├── 1998pdf.pdf ~ 2024ltr.pdf # PDF格式
│   ├── letters/                # 源文件的letters副本
│   └── 财务报表/               # 财务数据
├── 巴菲特分享版/                # 输出目录（独立Git仓库）
│   ├── index.html              # 首页
│   ├── letters/                # 生成的双语HTML文件
│   ├── images/                 # 表格截图
│   └── .github/workflows/      # GitHub Actions部署
└── letters/                    # 旧版输出（已废弃）
```

### 关键发现：双Git仓库
- `/workspace/巴菲特分享版/` 是一个**独立的Git仓库**，remote指向 `https://github.com/FrankFang99/buffett-letters.git`
- `/workspace/` 也有一个Git仓库，但推送它不会更新网站
- **所有修改必须在`巴菲特分享版`目录里commit和push**

### 部署流程
1. 修改代码或重新构建：`cd /workspace && python3 build_static_v2.py`
2. 提交到`巴菲特分享版`仓库：
   ```bash
   cd /workspace/巴菲特分享版
   git add -A
   git commit -m "描述修改内容"
   git push origin main
   ```
3. GitHub Actions会自动部署到 https://frankfang99.github.io/buffett-letters/
4. CDN缓存可能需要几分钟刷新

---

## 构建脚本核心模块（build_static_v2.py）

### 主要函数
| 函数 | 作用 |
|------|------|
| `parse_html_source(fp)` | 解析HTML源文件，返回blocks列表 |
| `_parse_insurance_table(lines, full_text)` | 解析Insurance行业表格 |
| `parse_table_from_text(text)` | 解析通用表格 |
| `translate_table(table, cache, kp)` | 翻译表格（保护数字和年份标记） |
| `table_to_html(table)` | 将表格数据转为HTML |
| `clean_paragraphs(content)` | 清理和去重段落 |
| `generate_letter_html(year, content, cache, fd, yw)` | 生成最终的双语HTML |
| `process_year_content(year, cache, fd)` | 处理单年内容 |
| `load_cache()` / `save_cache(cache)` | 翻译缓存管理 |

### 数据流
```
源HTML → parse_html_source() → blocks[]
       → clean_paragraphs() → 清理后的blocks[]
       → generate_letter_html() → 最终HTML文件
```

### Block类型
- `heading`: 标题
- `text`: 普通文本段落
- `table`: 表格
- `perf_table`: 绩效表格
- `image`: 图片

---

## 常见问题及修复方案

### 问题1：表格列数错误（多余的Col 4/第4列）

**原因**：`_parse_insurance_table`函数的年份正则只匹配4位数字，无法处理`1981 (Rev.)`格式，导致年份标记被拆分到下一列。

**修复**：年份正则改为`^(\d{4})(?:\s*\([^)]+\))?$`

**检查命令**：
```bash
grep -r "Col 4\|第4" /workspace/巴菲特分享版/letters/
```

### 问题2：HTML标签被转义（`&lt;b&gt;`代替`<b>`）

**原因**：`parse_html_source`中处理`<pre>`标签时，`<B>`标签的内容被错误转义。

**修复**：确保`<pre>`标签内的`<B>`和`<I>`标签被正确处理，不要用`get_text()`提取后再replace。

**检查命令**：
```bash
grep -r "&lt;b&gt;\|&lt;/b&gt;\|&lt;i&gt;\|&lt;/i&gt;" /workspace/巴菲特分享版/letters/
```

### 问题3：标题重复（如BERKSHIRE HATHAWAY INC.出现两次）

**原因**：源文件中标题在开头和附录各出现一次，去重逻辑过于激进或不够精确。

**修复**：去重逻辑应只删除**连续的**重复段落，保留非连续的重复（如附录标题）。

**检查命令**：
```bash
grep -c "BERKSHIRE HATHAWAY INC" /workspace/巴菲特分享版/letters/1983.html
```

### 问题4：表格识别错误（表头合并、数据错位）

**原因**：源文件中表格格式多样，有的用点号对齐（`.............`），有的用空格对齐，有的跨行显示表头。

**修复**：
- Insurance表格：检查`Combined Ratio`、`Premium Written/Earned`等关键词
- See's Candy表格：检查`Sales Revenues`、`Operating Profits`等关键词
- 绩效表格：检查`Book Value`、`Per-Share`等关键词

### 问题5：翻译损坏（年份标记丢失）

**原因**：`translate_table`函数将`1982 (Est.)`翻译为`1982年)`，丢失了`(Est.)`部分。

**修复**：在`translate_table`中添加年份标记保护：
```python
year_marker_match = re.match(r'^(\d{4})(\s*\([^)]+\))?$', cell)
if year_marker_match:
    year = year_marker_match.group(1)
    marker = year_marker_match.group(2) or ''
    translated_year = translate_text(year, cache, text_hash(year))
    nr.append(translated_year + marker)
```

### 问题6：`is_data_row`误判

**原因**：`is_data_row`函数将包含数字和点号的文本（如`1981 (Rev.)`）误判为数据行。

**修复**：确保年份标记不会被`is_data_row`匹配。

---

## 源文件格式差异

### 1977-1987年：`<PRE>`标签 + 点号对齐
```html
<PRE>
Yearly Change     Yearly Change      Combined Ratio
                  in Premiums       in Premiums
                  Written (%)       Earned (%)
                -------------     -------------
1972 ..............     10.2              10.9
1981 (Rev.) .........      3.9               4.1
</PRE>
```

### 1988-1999年：混合格式
- 部分使用`<PRE>`标签
- 部分使用HTML表格`<TABLE>`
- 1998年特殊：`1998htm.html`

### 2000-2024年：PDF格式
- 文件名格式：`20XXltr.pdf`
- 需要PDF解析

### 特殊格式
- **跨行表头**：如"Yearly Change"在第一行，"in Premiums Written (%)"在第二行
- **年份标记**：`1981 (Rev.)`、`1982 (Est.)`、`1976 (53 weeks)`
- **斜体表头**：`<I>`标签内的表头内容

---

## 翻译管理

### 翻译缓存
- 缓存文件：`_translation_cache_v2.json`
- 使用`text_hash(text)`作为key
- 缓存避免重复翻译，节省API调用

### 翻译保护规则
1. **纯数字不翻译**：`is_pure_number(cell)` → True则跳过
2. **数据行不翻译**：`is_data_row(cell)` → True则跳过
3. **年份标记保护**：`1981 (Rev.)` → 只翻译年份，保留标记
4. **公司名不翻译**：如GEICO、Berkshire Hathaway等
5. **表头翻译**：Insurance表格和绩效表格的表头需要翻译

### 常见翻译问题
- "Blue Chip Stamps" → "蓝筹印花"（不是"蓝色芯片"）
- "float" → "浮存金"（保险术语）
- "underwriting" → "承保"（不是"写作"）
- "earnings" → "收益"（不是"赚钱"）

---

## 质量检查清单

每次修改后必须执行以下检查：

### 全局检查
- [ ] `grep -r "&lt;b&gt;\|&lt;/b&gt;" 巴菲特分享版/letters/` → 应无结果
- [ ] `grep -r "Col [0-9]" 巴菲特分享版/letters/` → 应无结果
- [ ] `grep -r "第[0-9]" 巴菲特分享版/letters/` → 应无结果（除非是正常翻译）

### 逐年检查
- [ ] 每年HTML文件能正常打开
- [ ] 表格列数正确
- [ ] 年份标记完整（`(Rev.)`、`(Est.)`、`(53 weeks)`等）
- [ ] 标题不重复
- [ ] 中英对照正确显示

### 部署检查
- [ ] `cd /workspace/巴菲特分享版 && git status` → 确认修改已暂存
- [ ] `git log --oneline -3` → 确认最新commit
- [ ] `git push origin main` → 确认推送成功
- [ ] GitHub Actions运行成功

---

## 更新记录

### 2026-05-12 初始版本
- 创建skill，总结48年致股东信处理经验
- 记录6大常见问题及修复方案
- 记录项目架构和部署流程
- 记录源文件格式差异
