#!/usr/bin/env python3
"""
巴菲特股东信静态网站构建 v4
- PyMuPDF提取PDF（保留粗体）
- 表格检测：多行点号引导表格 → HTML table；单行数据行 → data-row
- Performance vs S&P 500 表格特殊处理（年份+双列）
- * * * 分隔符居中显示
- 逐段并排布局（英文|中文）
- YandexTranslate翻译，带缓存
"""
import os, re, json, time, sys, threading, hashlib, html as html_mod
import fitz
from bs4 import BeautifulSoup, NavigableString, Tag
from translatepy.translators.yandex import YandexTranslate

BASE_DIR = "/workspace/巴菲特"
OUTPUT_DIR = "/workspace/巴菲特分享版"
LETTERS_DIR = os.path.join(OUTPUT_DIR, "letters")
CACHE_FILE = os.path.join(OUTPUT_DIR, "_translation_cache_v2.json")
FINANCIAL_FILE = os.path.join(BASE_DIR, "财务报表", "financial_data.json")

SOURCES = {}
# 1977-1997年从官网下载的HTML
for y in range(1977, 1998):
    if y in (1983, 1988):
        SOURCES[y] = f"{y}.html"  # 已有的本地HTML
    else:
        SOURCES[y] = f"{y}_letter.html"  # 从官网下载的
# 1998-2024年PDF
SOURCES.update({1998:"1998pdf.pdf",1999:"final1999pdf.pdf",
           2000:"2000pdf.pdf",2001:"2001pdf.pdf",2002:"2002pdf.pdf",2003:"2003ltr.pdf"})
for y in range(2004,2025): SOURCES[y]=f"{y}ltr.pdf"
os.makedirs(LETTERS_DIR,exist_ok=True)

translator = YandexTranslate()
translate_lock = threading.Lock()

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE,'r',encoding='utf-8') as f: return json.load(f)
    return {}
def save_cache(cache):
    with open(CACHE_FILE,'w',encoding='utf-8') as f: json.dump(cache,f,ensure_ascii=False,indent=2)
def is_pure_number(s):
    return len(re.sub(r'[\s\$\%\,\.\(\)\-\+\:\/\d]','',s))==0
def has_chinese(t):
    return bool(t) and bool(re.search(r'[\u4e00-\u9fff]',t))

# ============================================================
# 术语保护表：专有名词保持原文，财务术语使用标准翻译
# ============================================================
# 格式: (英文术语, 中文翻译)
# 中文翻译为 None 表示保持原文不翻译
_TERM_DICT = [
    # ---- 巴菲特旗下公司/品牌（保持原文）----
    ('BNSF', None),
    ('GEICO', None),
    ('Berkadia', None),
    ('Clayton', None),
    ('CORT', None),
    ('XTRA', None),
    ('HomeServices', None),
    ('General Re', None),
    ('BH Reinsurance', None),
    ('Marmon – Containers and Cranes', None),
    ('Marmon – Railcars', None),
    ('MidAmerican', None),
    ('PacifiCorp', None),
    ('Northern Natural', None),
    ('Kern River', None),
    ('NetJets', None),
    ('See\'s Candies', None),
    ('Fruit of the Loom', None),
    ('Duracell', None),
    ('Precision Castparts', None),
    ('Lubrizol', None),
    ('IMC', None),
    ('Berkadia (our 50% share)', None),
    # ---- 财务报表标准术语 ----
    ('After-Tax Earnings', '税后收益'),
    ('Capital Gains', '资本收益'),
    ('Underwriting Profit', '承保利润'),
    ('Yearend Float', '年末浮存金'),
    ('Insurance Operations', '保险业务'),
    ('Net earnings', '净收益'),
    ('Operating earnings', '经营收益'),
    ('Pre-tax earnings', '税前收益'),
    ('Balance Sheet', '资产负债表'),
    ('Earnings Statement', '收益表'),
    ('Revenues', '收入'),
    ('Operating expenses', '营业费用'),
    ('Interest expense', '利息费用'),
    ('Interest (net)', '利息（净额）'),
    ('Income taxes', '所得税'),
    ('Fixed assets', '固定资产'),
    ('Goodwill and other intangibles', '商誉及其他无形资产'),
    ('Goodwill', '商誉'),
    ('Deferred taxes', '递延税款'),
    ('Cash and equivalents', '现金及现金等价物'),
    ('Notes payable', '应付票据'),
    ('Accounts and notes receivable', '应收账款及票据'),
    ('Inventory', '存货'),
    ('Other current assets', '其他流动资产'),
    ('Total current assets', '流动资产合计'),
    ('Total current liabilities', '流动负债合计'),
    ('Other current liabilities', '其他流动负债'),
    ('Non-controlling interests', '非控制性权益'),
    ('Term debt and other liabilities', '长期债务及其他负债'),
    ('Term debt', '长期债务'),
    ('Berkshire equity', '伯克希尔股东权益'),
    ('Other assets', '其他资产'),
    ('Net financial income', '净财务收入'),
    ('Earnings applicable to Berkshire', '归属于伯克希尔的收益'),
    ('Operating earnings before interest and taxes', '息税前经营收益'),
    ('Operating earnings before corporate interest and taxes', '企业息税前经营收益'),
    ('Income taxes and non-controlling interests', '所得税及非控制性权益'),
    ('U.K. utilities', '英国公用事业'),
    ('Iowa utility', '爱荷华州公用事业'),
    ('Nevada utilities', '内华达州公用事业'),
    ('Gas pipelines (Northern Natural and Kern River)', '天然气管道（Northern Natural与Kern River）'),
    ('Canadian transmission utility', '加拿大输电公用事业'),
    ('Renewable projects', '可再生能源项目'),
    ('Other (net)', '其他（净额）'),
    ('Liabilities and Equity', '负债及权益'),
    ('Assets', '资产'),
    ('Liabilities', '负债'),
    ('Equity', '权益'),
    ('in millions', '单位：百万美元'),
    ('in billions', '单位：十亿美元'),
    ('in billions of dollars', '单位：十亿美元'),
    # ---- 表格列名/表头术语 ----
    ('No. of Shares', '股份数量'),
    ('No. of Sh.', '股份数量'),
    ('Number of Shares', '股份数量'),
    ('Shares', '股份'),
    ('Company', '公司'),
    ('Cost', '成本'),
    ('Market', '市值'),
    ('Market Value', '市值'),
    ('Berkshire Share', '伯克希尔份额'),
    ('Berkshire\'s Share', '伯克希尔份额'),
    ('Earnings Before Income Taxes', '税前收益'),
    ('After Tax', '税后'),
    ('Total', '合计'),
    ('Net Investment Income', '净投资收益'),
    ('Realized Securities Gain', '已实现证券收益'),
    ('Earnings from Operations', '经营收益'),
    ('Interest on Debt', '债务利息'),
    ('Premiums Written', '签单保费'),
    ('Premiums Earned', '已赚保费'),
    ('Combined Ratio', '综合比率'),
    ('Policyholder Dividends', '保单持有人股息'),
    ('Investment Income', '投资收益'),
    ('Capital Employed', '已投资资本'),
    ('Shareholders\' Equity', '股东权益'),
    ('Book Value per Share', '每股账面价值'),
    ('Operating Earnings per Share', '每股经营收益'),
    ('Net Worth per Share', '每股净资产'),
    ('Year', '年份'),
    ('Gain (Loss)', '收益（损失）'),
    ('Combined Ratio after Policyholder Dividends', '保单持有人股息后综合比率'),
    ('Yearly Change in Premium Earned', '已赚保费年度变化率'),
    ('Yearly Change in Premium Written', '签单保费年度变化率'),
    ('Inflation Rate Measured by GNP Deflator', 'GNP平减指数衡量的通胀率'),
    ('Inflation Rate', '通胀率'),
    ('(000s omitted)', '（单位：千）'),
    ('(in thousands)', '（单位：千）'),
    ('(in millions)', '（单位：百万）'),
    ('Common Stocks', '普通股'),
    ('Total Common', '普通股合计'),
    ('Total Common Stocks', '普通股合计'),
    ('Col ', '第'),  # Col 4 -> 第4 (prefix match for "Col N")
    ('Column', '列'),
    ('Property, Plant, and Equipment, net', '物业、厂房及设备净值'),
    ('Investments in and Advances to Unconsolidated Subsidiaries and Joint Ventures', '对未合并子公司和合资企业的投资及预付款'),
    ('Other Assets, including Goodwill', '其他资产（含商誉）'),
    ('Long-term Debt and Capitalized Leases', '长期债务及资本化租赁'),
    ('Notes Payable and Current Portion of Long-term Debt', '应付票据及长期债务流动部分'),
    ('Applicable Income Tax', '适用所得税'),
    ('Historical deferred and current tax', '历史递延及当期税款'),
    ('Non-Cash Inter-period Allocation Adjustment', '非现金跨期分摊调整'),
    ('Special non-cash inventory costs', '特殊非现金存货成本'),
    ('Historical costs, excluding depreciation', '历史成本（不含折旧）'),
    ('Depreciation of plant and equipment', '厂房设备折旧'),
    ('Selling & Admin. Expense', '销售及管理费用'),
    ('Amortization of Goodwill', '商誉摊销'),
    ('Other Income, Net', '其他收入净额'),
    ('Pre-Tax Income', '税前利润'),
    ('Operating Profit', '经营利润'),
    ('Gross Profit', '毛利润'),
    ('Costs of Goods Sold', '销售成本'),
    ('Revenues', '收入'),
    ('Shareholders\' Equity', '股东权益'),
    ('Total Current Assets', '流动资产合计'),
    ('Total Current Liabilities', '流动负债合计'),
    ('Total Liabilities', '负债合计'),
    ('Other Deferred Credits', '其他递延贷项'),
    ('Deferred Income Taxes', '递延所得税'),
    ('Accrued Liabilities', '应计负债'),
    ('Accounts Payable', '应付账款'),
    ('Receivables, net', '应收账款净额'),
    ('Cash and Cash Equivalents', '现金及现金等价物'),
    ('Inventories', '存货'),
    ('Other', '其他'),
    ('Assets', '资产'),
    ('Liabilities', '负债'),
    ('Company O', '公司O'),
    ('Company N', '公司N'),
    ('All Other Common Stockholdings', '其他普通股持仓合计'),
    ('All Other Holdings', '其他持仓合计'),
    ('Total Equities', '股权合计'),
    ('Total Equities at Cost', '股权成本合计'),
    ('Total Equities at Market', '股权市值合计'),
    ('Total', '合计'),
    ('Subtotal', '小计'),
    ('Grand Total', '总计'),
    ('All Other', '其他合计'),
    ('Other Common Stocks', '其他普通股'),
    ('Preferred Stocks', '优先股'),
    ('All Other Securities', '其他证券合计'),
    ('Tax-Exempt Bonds', '免税债券'),
    ('Taxable Bonds', '应税债券'),
    ('U.S. Government Securities', '美国政府证券'),
    ('State and Municipal Bonds', '州和市政债券'),
    ('Other Investments', '其他投资'),
    ('Short-Term Investments', '短期投资'),
    ('Cash and Cash Equivalents', '现金及现金等价物'),
    ('Receivables, net', '应收账款净额'),
    ('Other Assets', '其他资产'),
    ('Notes Payable', '应付票据'),
    ('Accrued Liabilities', '应计负债'),
    ('Deferred Income Taxes', '递延所得税'),
    ('Other Deferred Credits', '其他递延贷项'),
    ('Non-Cash Inter-period Allocation Adjustment', '非现金跨期分摊调整'),
    ('Applicable Income Tax', '适用所得税'),
    ('Historical deferred and current tax', '历史递延和当期税款'),
    ('Costs of Goods Sold', '销售成本'),
    ('Historical costs, excluding depreciation', '历史成本（不含折旧）'),
    ('Special non-cash inventory costs', '特殊非现金存货成本'),
    ('Depreciation of plant and equipment', '厂房设备折旧'),
    ('Selling & Admin. Expense', '销售及管理费用'),
    ('Operating Income', '经营收入'),
    ('Other Income', '其他收入'),
    ('Interest Expense', '利息费用'),
    ('Interest and Other', '利息及其他'),
    ('Income Before Taxes', '税前利润'),
    ('Net Income', '净利润'),
    ('Earnings per Share', '每股收益'),
    ('Shares Outstanding', '流通股数'),
    ('Revenues', '收入'),
    ('Cost of Sales', '销售成本'),
    ('Gross Profit', '毛利润'),
    ('Operating Expenses', '营业费用'),
    ('Other Operating Expenses', '其他营业费用'),
    ('Operating Profit', '经营利润'),
    ('Interest Income', '利息收入'),
    ('Interest Expense', '利息费用'),
    ('Other Income (Expense)', '其他收入（费用）'),
    ('Income before Taxes', '税前利润'),
    ('Income Tax Expense', '所得税费用'),
    ('Net Income', '净利润'),
    ('Preferred Stock Dividends', '优先股股息'),
    ('Net Income to Common', '普通股净利润'),
    ('Weighted Average Shares', '加权平均股数'),
    ('Current Portion of Long-term Debt', '长期债务流动部分'),
    ('Long-term Debt', '长期债务'),
    ('Stockholders\' Equity', '股东权益'),
    ('Total Liabilities and Equity', '负债及权益合计'),
    ('Total Current Liabilities', '流动负债合计'),
    ('Total Liabilities', '负债合计'),
    ('Total Assets', '资产合计'),
    ('Total Shareholders\' Equity', '股东权益合计'),
    ('Retained Earnings', '留存收益'),
    ('Common Stock', '普通股'),
    ('Additional Paid-in Capital', '资本公积'),
    ('Treasury Stock', '库存股'),
    ('Accumulated Other Comprehensive Income', '累计其他综合收益'),
    ('Preferred Stocks', '优先股'),
    ('U.S. Treasury Bills', '美国国债'),
    ('U.S. Treasury Bonds', '美国国债'),
    ('Tax-Exempt Bonds', '免税债券'),
    ('Corporate Bonds', '公司债券'),
    ('Other Equity', '其他股权'),
    ('Short-term Investments', '短期投资'),
    ('Cash Equivalents', '现金等价物'),
    ('Total Investments', '投资合计'),
    ('Purchased Goodwill', '购买商誉'),
    ('Book Value', '账面价值'),
    ('Market Value per Share', '每股市值'),
    ('Shares Outstanding', '流通股数'),
    ('Weighted-Average Shares', '加权平均股数'),
    ('Diluted Shares', '稀释股数'),
    ('Basic Earnings per Share', '基本每股收益'),
    ('Diluted Earnings per Share', '稀释每股收益'),
    ('Class A Shares', 'A类股'),
    ('Class B Shares', 'B类股'),
    ('Net Income', '净利润'),
    ('Gross Profit', '毛利润'),
    ('Operating Profit', '经营利润'),
    ('Total Revenue', '总收入'),
    ('Cost of Sales', '销售成本'),
    ('Selling, General and Administrative', '销售及管理费用'),
    ('Research and Development', '研发费用'),
    ('Depreciation and Amortization', '折旧与摊销'),
    ('Operating Cash Flow', '经营现金流'),
    ('Capital Expenditures', '资本支出'),
    ('Free Cash Flow', '自由现金流'),
    ('Long-term Debt', '长期债务'),
    ('Short-term Debt', '短期债务'),
    ('Retained Earnings', '留存收益'),
    ('Total Shareholders\' Equity', '股东权益合计'),
    ('Minority Interest', '少数股东权益'),
    ('Earnings per Share', '每股收益'),
    ('Dividends per Share', '每股股息'),
    ('Book Value per Share', '每股账面价值'),
    ('Return on Equity', '股本回报率'),
    ('Return on Assets', '资产回报率'),
    ('Debt-to-Equity Ratio', '债务股本比率'),
    ('Current Ratio', '流动比率'),
    ('Insurance Float', '保险浮存金'),
    ('Underwriting Gain', '承保收益'),
    ('Underwriting Loss', '承保损失'),
    ('Investment Gain', '投资收益'),
    ('Investment Loss', '投资损失'),
    ('Acquisition', '收购'),
    ('Disposal', '处置'),
    ('Foreign Currency Translation', '外币折算'),
    ('Pension Liability', '养老金负债'),
    ('Post-Retirement Benefits', '退休后福利'),
    ('Derivative Contracts', '衍生品合约'),
    ('Contractual Obligations', '合同义务'),
    ('Contingent Liabilities', '或有负债'),
    ('Related Party Transactions', '关联交易'),
    ('Segment Information', '分部信息'),
    ('Subsequent Events', '期后事项'),
    ('Stock-Based Compensation', '股权激励费用'),
    ('Share Repurchases', '股票回购'),
    ('New Business', '新业务'),
    ('Renewal Business', '续保业务'),
    ('Loss Ratio', '赔付率'),
    ('Expense Ratio', '费用率'),
    ('Frequency', '频率'),
    ('Severity', '严重程度'),
    ('Reserve Development', '准备金发展'),
    ('Catastrophe Losses', '巨灾损失'),
    ('Other Income', '其他收入'),
    ('Other Expense', '其他费用'),
    ('Non-Cash', '非现金'),
    ('Cash Flow from Operations', '经营活动现金流'),
    ('Cash Flow from Investing', '投资活动现金流'),
    ('Cash Flow from Financing', '筹资活动现金流'),
    ('Change in Cash', '现金变动'),
    ('Beginning Balance', '期初余额'),
    ('Ending Balance', '期末余额'),
    ('Average Balance', '平均余额'),
    ('Interest Income', '利息收入'),
    ('Interest Expense', '利息费用'),
    ('Other Underwriting Expense', '其他承保费用'),
    ('Amortization of Deferred Policy Acquisition Costs', '递延保单获取成本摊销'),
    ('Statutory Income', '法定收益'),
    ('Statutory Surplus', '法定盈余'),
    ('Admitted Assets', '认可资产'),
    ('Non-Admitted Assets', '非认可资产'),
    ('Policyholder Benefits', '保单持有人福利'),
    ('Ceded Premiums', '分出保费'),
    ('Gross Premiums', '总保费'),
    ('Net Premiums', '净保费'),
    ('Unearned Premiums', '未赚保费'),
    ('Loss Reserves', '损失准备金'),
    ('Loss Adjustment Expenses', '损失调整费用'),
    ('Dividends Declared', '已宣告股息'),
    ('Shares Repurchased', '回购股份'),
    ('Shares Issued', '发行股份'),
    ('Treasury Stock', '库存股'),
    ('Accumulated Other Comprehensive Income', '累计其他综合收益'),
    ('Comprehensive Income', '综合收益'),
    ('Tax Rate', '税率'),
    ('Effective Tax Rate', '有效税率'),
    ('Pre-Tax Income', '税前利润'),
    ('After-Tax Income', '税后利润'),
    ('Non-Operating Income', '非经营收入'),
    ('Non-Operating Expense', '非经营费用'),
    ('Extraordinary Items', '非常项目'),
    ('Accounting Change', '会计变更'),
    ('Discontinued Operations', '终止经营业务'),
    ('Restructuring Charges', '重组费用'),
    ('Asset Write-Downs', '资产减值'),
    ('Impairment Charges', '减值损失'),
    ('Goodwill Impairment', '商誉减值'),
    ('Capital Surplus', '资本公积'),
    ('Paid-in Capital', '实收资本'),
    ('Total Liabilities', '负债合计'),
    ('Total Assets', '资产合计'),
    ('Net Working Capital', '净营运资本'),
    ('Tangible Book Value', '有形账面价值'),
    ('Intangible Assets', '无形资产'),
    ('Property, Plant and Equipment', '物业、厂房及设备'),
    ('Gross Property, Plant and Equipment', '物业、厂房及设备总额'),
    ('Net Property, Plant and Equipment', '物业、厂房及设备净值'),
    ('Accumulated Depreciation', '累计折旧'),
    ('Inventories', '存货'),
    ('Prepaid Expenses', '预付费用'),
    ('Deferred Revenue', '递延收入'),
    ('Accounts Payable', '应付账款'),
    ('Accrued Expenses', '应计费用'),
    ('Short-Term Borrowings', '短期借款'),
    ('Long-Term Borrowings', '长期借款'),
    ('Convertible Securities', '可转换证券'),
    ('Warrants', '认股权证'),
    ('Options', '期权'),
    ('Restricted Stock', '限制性股票'),
    ('Performance Shares', '绩效股'),
    ('Unit Values', '单位价值'),
    ('Trading Volume', '交易量'),
    ('Market Capitalization', '市值'),
    ('Price-to-Book Ratio', '市净率'),
    ('Price-to-Earnings Ratio', '市盈率'),
    ('Dividend Yield', '股息率'),
    ('Payout Ratio', '派息率'),
    ('Retention Ratio', '留存比率'),
    ('Return on Invested Capital', '投资资本回报率'),
    ('Economic Goodwill', '经济商誉'),
    ('Float per Share', '每股浮存金'),
    ('Insurance Premiums', '保险保费'),
    ('Supplemental Coverage', '补充保险'),
    ('Self-Insurance', '自保'),
    ('Retrospective Contracts', '追溯合同'),
    ('Prospective Contracts', '预期合同'),
    ('Short-Tail Lines', '短尾业务'),
    ('Long-Tail Lines', '长尾业务'),
    ('Reserve Adequacy', '准备金充足性'),
    ('Underwriting Discipline', '承保纪律'),
    ('Pricing Power', '定价权'),
    ('Competitive Advantage', '竞争优势'),
    ('Moat', '护城河'),
    ('Owner Earnings', '所有者收益'),
    ('Look-Through Earnings', '透视收益'),
    ('Purchase-Price Accounting', '购买法会计'),
    ('Pool-of-Interests Accounting', '权益结合法会计'),
    ('Stock Options', '股票期权'),
    ('Executive Compensation', '高管薪酬'),
    ('Board of Directors', '董事会'),
    ('Annual Meeting', '年度股东大会'),
    ('Shareholder of Record', '登记股东'),
    ('Outstanding Shares', '流通股'),
    ('Voting Power', '投票权'),
    ('Dual-Class Structure', '双股权结构'),
    ('Acquisition Criteria', '收购标准'),
    ('Intrinsic Value', '内在价值'),
    ('Margin of Safety', '安全边际'),
    ('Mr. Market', '市场先生'),
    ('Permanent Holdings', '永久持仓'),
    ('Temporary Holdings', '临时持仓'),
    ('Portfolio', '投资组合'),
    ('Diversification', '多元化'),
    ('Concentration', '集中度'),
    ('Liquidity', '流动性'),
    ('Volatility', '波动性'),
    ('Beta', '贝塔系数'),
    ('Systemic Risk', '系统性风险'),
    ('Unsystematic Risk', '非系统性风险'),
    ('Risk-Free Rate', '无风险利率'),
    ('Equity Risk Premium', '股权风险溢价'),
    ('Discount Rate', '折现率'),
    ('Terminal Value', '终值'),
    ('Free Cash Flow to Equity', '股权自由现金流'),
    ('Enterprise Value', '企业价值'),
    ('EV/EBITDA', '企业价值/息税折旧摊销前利润'),
    ('Price/Book', '市净率'),
    ('Price/Sales', '市销率'),
    ('Price/Earnings', '市盈率'),
    ('Dividend Discount Model', '股息折现模型'),
    ('Discounted Cash Flow', '折现现金流'),
    ('Net Present Value', '净现值'),
    ('Internal Rate of Return', '内部收益率'),
    ('Hurdle Rate', '门槛收益率'),
    ('Cost of Capital', '资本成本'),
    ('Weighted Average Cost of Capital', '加权平均资本成本'),
    ('Economic Value Added', '经济增加值'),
    ('Market Value Added', '市场增加值'),
    ('Total Return', '总回报'),
    ('Annualized Return', '年化回报'),
    ('Cumulative Return', '累计回报'),
    ('Benchmark', '基准'),
    ('Index Fund', '指数基金'),
    ('Active Management', '主动管理'),
    ('Passive Management', '被动管理'),
    ('Expense Ratio', '费用率'),
    ('Turnover Ratio', '换手率'),
    ('Tracking Error', '跟踪误差'),
    ('Information Ratio', '信息比率'),
    ('Sharpe Ratio', '夏普比率'),
    ('Sortino Ratio', '索提诺比率'),
    ('Maximum Drawdown', '最大回撤'),
    ('Value at Risk', '风险价值'),
    ('Stress Testing', '压力测试'),
    ('Scenario Analysis', '情景分析'),
    ('Monte Carlo Simulation', '蒙特卡洛模拟'),
    ('Black-Scholes Model', '布莱克-斯科尔斯模型'),
    ('Implied Volatility', '隐含波动率'),
    ('Historical Volatility', '历史波动率'),
    ('Options Pricing', '期权定价'),
    ('Futures Contract', '期货合约'),
    ('Forward Contract', '远期合约'),
    ('Swap Agreement', '互换协议'),
    ('Credit Default Swap', '信用违约互换'),
    ('Interest Rate Swap', '利率互换'),
    ('Currency Swap', '货币互换'),
    ('Hedging', '对冲'),
    ('Speculation', '投机'),
    ('Arbitrage', '套利'),
    ('Leverage', '杠杆'),
    ('Deleveraging', '去杠杆'),
    ('Refinancing', '再融资'),
    ('Debt Maturity', '债务到期'),
    ('Credit Rating', '信用评级'),
    ('Default Risk', '违约风险'),
    ('Recovery Rate', '回收率'),
    ('Yield Spread', '收益率利差'),
    ('Treasury Yield', '国债收益率'),
    ('Corporate Yield', '公司债收益率'),
    ('Municipal Bond', '市政债券'),
    ('High-Yield Bond', '高收益债券'),
    ('Investment Grade', '投资级'),
    ('Speculative Grade', '投机级'),
    ('Junk Bond', '垃圾债券'),
    ('Sovereign Debt', '主权债务'),
    ('Emerging Markets', '新兴市场'),
    ('Developed Markets', '发达市场'),
    ('Domestic Markets', '国内市场'),
    ('International Diversification', '国际多元化'),
    ('Currency Exposure', '货币敞口'),
    ('Translation Risk', '折算风险'),
    ('Transaction Risk', '交易风险'),
    ('Economic Risk', '经济风险'),
    ('Operating Risk', '经营风险'),
    ('Financial Risk', '财务风险'),
    ('Business Risk', '商业风险'),
    ('Industry Analysis', '行业分析'),
    ('Competitive Analysis', '竞争分析'),
    ('SWOT Analysis', 'SWOT分析'),
    ('Porter\'s Five Forces', '波特五力模型'),
    ('PEST Analysis', 'PEST分析'),
    ('Supply Chain', '供应链'),
    ('Customer Base', '客户基础'),
    ('Market Share', '市场份额'),
    ('Revenue Growth', '收入增长'),
    ('Profit Margin', '利润率'),
    ('Gross Margin', '毛利率'),
    ('Operating Margin', '营业利润率'),
    ('Net Margin', '净利润率'),
    ('Return on Sales', '销售回报率'),
    ('Asset Turnover', '资产周转率'),
    ('Inventory Turnover', '存货周转率'),
    ('Receivables Turnover', '应收账款周转率'),
    ('Days Sales Outstanding', '应收账款周转天数'),
    ('Days Inventory Outstanding', '存货周转天数'),
    ('Days Payable Outstanding', '应付账款周转天数'),
    ('Cash Conversion Cycle', '现金转换周期'),
    ('Working Capital Management', '营运资本管理'),
    ('Capital Budgeting', '资本预算'),
    ('Capital Allocation', '资本配置'),
    ('Mergers and Acquisitions', '并购'),
    ('Joint Venture', '合资企业'),
    ('Strategic Alliance', '战略联盟'),
    ('Licensing Agreement', '许可协议'),
    ('Franchise', '特许经营'),
    ('Royalty', '特许权使用费'),
    ('Intellectual Property', '知识产权'),
    ('Patent', '专利'),
    ('Trademark', '商标'),
    ('Copyright', '版权'),
    ('Trade Secret', '商业秘密'),
    ('Research and Development', '研发'),
    ('Innovation', '创新'),
    ('Technology', '技术'),
    ('Digital Transformation', '数字化转型'),
    ('E-commerce', '电子商务'),
    ('Cloud Computing', '云计算'),
    ('Artificial Intelligence', '人工智能'),
    ('Machine Learning', '机器学习'),
    ('Big Data', '大数据'),
    ('Blockchain', '区块链'),
    ('Cryptocurrency', '加密货币'),
    ('Fintech', '金融科技'),
    ('Insurtech', '保险科技'),
    ('Regtech', '监管科技'),
    ('Proptech', '房地产科技'),
    ('Wealthtech', '财富科技'),
    ('Sustainability', '可持续性'),
    ('ESG', '环境、社会和治理'),
    ('Carbon Footprint', '碳足迹'),
    ('Climate Change', '气候变化'),
    ('Renewable Energy', '可再生能源'),
    ('Solar Energy', '太阳能'),
    ('Wind Energy', '风能'),
    ('Hydroelectric', '水电'),
    ('Natural Gas', '天然气'),
    ('Oil and Gas', '石油天然气'),
    ('Pipeline', '管道'),
    ('Transmission', '输电'),
    ('Distribution', '配电'),
    ('Generation', '发电'),
    ('Capacity', '装机容量'),
    ('Load Factor', '负荷因子'),
    ('Rate Base', '费率基数'),
    ('Regulated Return', '监管回报率'),
    ('Cost of Service', '服务成本'),
    ('Rate Case', '费率案例'),
    ('Public Utility Commission', '公用事业委员会'),
    ('Federal Energy Regulatory Commission', '联邦能源监管委员会'),
    ('Nuclear Regulatory Commission', '核监管委员会'),
    ('Environmental Protection Agency', '环境保护署'),
    ('Securities and Exchange Commission', '证券交易委员会'),
    ('Financial Accounting Standards Board', '财务会计准则委员会'),
    ('International Accounting Standards Board', '国际会计准则理事会'),
    ('Generally Accepted Accounting Principles', '公认会计原则'),
    ('International Financial Reporting Standards', '国际财务报告准则'),
    ('Auditor', '审计师'),
    ('Audit Opinion', '审计意见'),
    ('Unqualified Opinion', '无保留意见'),
    ('Qualified Opinion', '保留意见'),
    ('Adverse Opinion', '否定意见'),
    ('Disclaimer of Opinion', '无法表示意见'),
    ('Internal Controls', '内部控制'),
    ('Material Weakness', '重大缺陷'),
    ('Significant Deficiency', '重要缺陷'),
    ('Management Discussion and Analysis', '管理层讨论与分析'),
    ('Notes to Financial Statements', '财务报表附注'),
    ('Independent Auditor', '独立审计师'),
    ('Big Four', '四大'),
    ('Sarbanes-Oxley Act', '萨班斯-奥克斯利法案'),
    ('Dodd-Frank Act', '多德-弗兰克法案'),
    ('Volcker Rule', '沃尔克规则'),
    ('Basel III', '巴塞尔协议III'),
    ('Capital Adequacy', '资本充足率'),
    ('Tier 1 Capital', '一级资本'),
    ('Tier 2 Capital', '二级资本'),
    ('Risk-Weighted Assets', '风险加权资产'),
    ('Liquidity Coverage Ratio', '流动性覆盖率'),
    ('Net Stable Funding Ratio', '净稳定资金比率'),
    ('Leverage Ratio', '杠杆率'),
    ('Countercyclical Capital Buffer', '逆周期资本缓冲'),
    ('Systemically Important Financial Institution', '系统重要性金融机构'),
    ('Living Will', '生前遗嘱'),
    ('Resolution Plan', '处置计划'),
    ('Recovery Plan', '恢复计划'),
    ('Stress Test', '压力测试'),
    ('Contingency Plan', '应急计划'),
    ('Business Continuity', '业务连续性'),
    ('Disaster Recovery', '灾难恢复'),
    ('Cybersecurity', '网络安全'),
    ('Data Privacy', '数据隐私'),
    ('General Data Protection Regulation', '通用数据保护条例'),
    ('California Consumer Privacy Act', '加州消费者隐私法案'),
    ('Personal Information', '个人信息'),
    ('Data Breach', '数据泄露'),
    ('Identity Theft', '身份盗窃'),
    ('Phishing', '网络钓鱼'),
    ('Malware', '恶意软件'),
    ('Ransomware', '勒索软件'),
    ('Firewall', '防火墙'),
    ('Encryption', '加密'),
    ('Two-Factor Authentication', '双因素认证'),
    ('Multi-Factor Authentication', '多因素认证'),
    ('Single Sign-On', '单点登录'),
    ('Access Control', '访问控制'),
    ('Authorization', '授权'),
    ('Authentication', '认证'),
    ('Non-Disclosure Agreement', '保密协议'),
    ('Non-Compete Agreement', '竞业禁止协议'),
    ('Employment Agreement', '雇佣协议'),
    ('Severance Package', '遣散方案'),
    ('Golden Parachute', '金色降落伞'),
    ('Poison Pill', '毒丸计划'),
    ('White Knight', '白衣骑士'),
    ('Tender Offer', '要约收购'),
    ('Hostile Takeover', '恶意收购'),
    ('Proxy Fight', '代理权争夺'),
    ('Shareholder Proposal', '股东提案'),
    ('Say-on-Pay', '薪酬投票'),
    ('Clawback Provision', '追回条款'),
    ('Earnout', '盈利对赌'),
    ('Representation and Warranty', '陈述与保证'),
    ('Indemnification', '赔偿'),
    ('Holdback', '扣留款'),
    ('Escrow', '第三方托管'),
    ('Closing Conditions', '交割条件'),
    ('Due Diligence', '尽职调查'),
    ('Letter of Intent', '意向书'),
    ('Memorandum of Understanding', '谅解备忘录'),
    ('Term Sheet', '条款清单'),
    ('Purchase Agreement', '收购协议'),
    ('Stock Purchase Agreement', '股权收购协议'),
    ('Asset Purchase Agreement', '资产收购协议'),
    ('Merger Agreement', '合并协议'),
    ('Joint Venture Agreement', '合资协议'),
    ('Partnership Agreement', '合伙协议'),
    ('Operating Agreement', '经营协议'),
    ('Limited Liability Company', '有限责任公司'),
    ('Partnership', '合伙企业'),
    ('Corporation', '公司'),
    ('Sole Proprietorship', '个人独资企业'),
    ('Non-Profit Organization', '非营利组织'),
    ('Government Entity', '政府实体'),
    ('State-Owned Enterprise', '国有企业'),
    ('Privately Held', '非上市'),
    ('Publicly Traded', '上市公司'),
    ('Listed Company', '上市公司'),
    ('Delisted', '退市'),
    ('Initial Public Offering', '首次公开募股'),
    ('Secondary Offering', '二次发行'),
    ('Private Placement', '私募'),
    ('Rights Offering', '配股'),
    ('Stock Split', '股票拆分'),
    ('Reverse Stock Split', '反向拆分'),
    ('Stock Dividend', '股票股息'),
    ('Cash Dividend', '现金股息'),
    ('Special Dividend', '特别股息'),
    ('Interim Dividend', '中期股息'),
    ('Final Dividend', '期末股息'),
    ('Record Date', '登记日'),
    ('Ex-Dividend Date', '除息日'),
    ('Payment Date', '付款日'),
    ('Declaration Date', '宣告日'),
    ('Shareholder Equity', '股东权益'),
    ('Retained Earnings', '留存收益'),
    ('Accumulated Deficit', '累计亏损'),
    ('Other Comprehensive Income', '其他综合收益'),
    ('Treasury Shares', '库存股'),
    ('Non-Controlling Interest', '非控制性权益'),
    ('Minority Interest', '少数股东权益'),
    ('Provision for Income Taxes', '所得税准备'),
    ('Current Income Tax Expense', '当期所得税费用'),
    ('Deferred Income Tax Expense', '递延所得税费用'),
    ('Deferred Tax Asset', '递延所得税资产'),
    ('Deferred Tax Liability', '递延所得税负债'),
    ('Tax Credit', '税收抵免'),
    ('Tax Benefit', '税收优惠'),
    ('Taxable Income', '应纳税所得额'),
    ('Pre-Tax Accounting Income', '税前会计利润'),
    ('Effective Tax Rate', '有效税率'),
    ('Statutory Tax Rate', '法定税率'),
    ('Tax Shield', '税盾'),
    ('Tax Loss Carryforward', '税损结转'),
    ('Tax Loss Carryback', '税损追补'),
    ('Permanent Difference', '永久性差异'),
    ('Temporary Difference', '暂时性差异'),
    ('Depreciation', '折旧'),
    ('Amortization', '摊销'),
    ('Depletion', '折耗'),
    ('Impairment', '减值'),
    ('Write-Off', '核销'),
    ('Write-Down', '减记'),
    ('Reversal', '转回'),
    ('Recovery', '收回'),
    ('Gain', '收益'),
    ('Loss', '损失'),
    ('Realized Gain', '已实现收益'),
    ('Unrealized Gain', '未实现收益'),
    ('Realized Loss', '已实现损失'),
    ('Unrealized Loss', '未实现损失'),
    ('Accumulated Other Comprehensive Loss', '累计其他综合损失'),
    ('Reclassification Adjustment', '重分类调整'),
    ('Available-for-Sale', '可供出售'),
    ('Held-to-Maturity', '持有至到期'),
    ('Fair Value', '公允价值'),
    ('Fair Value Hierarchy', '公允价值层级'),
    ('Level 1', '第一层级'),
    ('Level 2', '第二层级'),
    ('Level 3', '第三层级'),
    ('Mark-to-Market', '按市值计价'),
    ('Lower of Cost or Market', '成本与市价孰低'),
    ('Impairment Test', '减值测试'),
    ('Discounted Cash Flow', '折现现金流'),
    ('Present Value', '现值'),
    ('Future Value', '终值'),
    ('Annuity', '年金'),
    ('Perpetuity', '永续年金'),
    ('Growing Perpetuity', '增长型永续年金'),
    ('Capitalization Rate', '资本化率'),
    ('Earnings Multiple', '收益倍数'),
    ('Revenue Multiple', '收入倍数'),
    ('EBITDA Multiple', 'EBITDA倍数'),
    ('Book Value Multiple', '账面价值倍数'),
    ('Comparable Company Analysis', '可比公司分析'),
    ('Precedent Transaction Analysis', '先例交易分析'),
    ('Leveraged Buyout', '杠杆收购'),
    ('Management Buyout', '管理层收购'),
    ('Employee Stock Ownership Plan', '员工持股计划'),
    ('401(k) Plan', '401(k)计划'),
    ('Pension Plan', '养老金计划'),
    ('Defined Benefit Plan', '固定收益计划'),
    ('Defined Contribution Plan', '固定缴款计划'),
    ('Actuarial Assumption', '精算假设'),
    ('Service Cost', '服务成本'),
    ('Interest Cost', '利息成本'),
    ('Expected Return on Plan Assets', '计划资产预期回报'),
    ('Prior Service Cost', '前期服务成本'),
    ('Transition Obligation', '过渡义务'),
    ('Transition Asset', '过渡资产'),
    ('Pension Obligation', '养老金义务'),
    ('Plan Assets', '计划资产'),
    ('Funded Status', '资金状况'),
    ('Unfunded Obligation', '未注资义务'),
    ('Overfunded', '超注资'),
    ('Underfunded', '注资不足'),
    ('Vested Benefits', '既得福利'),
    ('Non-Vested Benefits', '未既得福利'),
    ('Actuarial Gain', '精算收益'),
    ('Actuarial Loss', '精算损失'),
    ('Curtailment', '缩减'),
    ('Settlement', '结算'),
    ('Amendment', '修订'),
    ('Benefit Reduction', '福利削减'),
    ('Lease', '租赁'),
    ('Operating Lease', '经营租赁'),
    ('Finance Lease', '融资租赁'),
    ('Lease Term', '租赁期'),
    ('Lease Liability', '租赁负债'),
    ('Right-of-Use Asset', '使用权资产'),
    ('Lease Expense', '租赁费用'),
    ('Rent Expense', '租金费用'),
    ('Contingent Rent', '或有租金'),
    ('Lease Incentive', '租赁激励'),
    ('Lease Classification', '租赁分类'),
    ('Lease Modification', '租赁修改'),
    ('Lease Termination', '租赁终止'),
    ('Sale-Leaseback', '售后回租'),
    ('Lessor', '出租人'),
    ('Lessee', '承租人'),
    ('Manufacturer', '制造商'),
    ('Distributor', '分销商'),
    ('Retailer', '零售商'),
    ('Wholesaler', '批发商'),
    ('Supplier', '供应商'),
    ('Vendor', '供应商'),
    ('Customer', '客户'),
    ('Subsidiary', '子公司'),
    ('Parent Company', '母公司'),
    ('Affiliate', '关联公司'),
    ('Associated Company', '联营公司'),
    ('Joint Venture', '合资企业'),
    ('Partnership', '合伙企业'),
    ('Sole Proprietorship', '个人独资企业'),
    ('Branch', '分支机构'),
    ('Division', '部门'),
    ('Business Segment', '业务分部'),
    ('Geographic Segment', '地理分部'),
    ('Reportable Segment', '可报告分部'),
    ('Intersegment Transaction', '分部间交易'),
    ('Elimination', '抵消'),
    ('Consolidation', '合并'),
    ('Non-Controlling Interest', '非控制性权益'),
    ('Acquisition Method', '收购法'),
    ('Equity Method', '权益法'),
    ('Proportionate Consolidation', '比例合并法'),
    ('Fair Value Option', '公允价值选择权'),
    ('Pushdown Accounting', '下推会计'),
    ('Step Acquisition', '分步收购'),
    ('Business Combination', '业务合并'),
    ('Contingent Consideration', '或有对价'),
    ('Identifiable Assets', '可辨认资产'),
    ('Assumed Liabilities', '承担负债'),
    ('Goodwill', '商誉'),
    ('Bargain Purchase', '廉价收购'),
    ('Negative Goodwill', '负商誉'),
    ('Intangible Asset', '无形资产'),
    ('Customer List', '客户名单'),
    ('Brand Name', '品牌名称'),
    ('Technology', '技术'),
    ('Patent', '专利'),
    ('Trademark', '商标'),
    ('Copyright', '版权'),
    ('Franchise', '特许经营权'),
    ('License', '许可'),
    ('Royalty Agreement', '特许权使用费协议'),
    ('Non-Compete Agreement', '竞业禁止协议'),
    ('Employment Contract', '雇佣合同'),
    ('Non-Disclosure Agreement', '保密协议'),
    ('Indemnification', '赔偿'),
    ('Insurance', '保险'),
    ('Reinsurance', '再保险'),
    ('Ceded Reinsurance', '分出再保险'),
    ('Assumed Reinsurance', '分入再保险'),
    ('Retroactive Reinsurance', '追溯再保险'),
    ('Prospective Reinsurance', '预期再保险'),
    ('Loss Sensitive Contract', '损失敏感合同'),
    ('Modified Coinsurance', '修改共保'),
    ('Deposit Accounting', '存款会计'),
    ('Finite Risk Reinsurance', '有限风险再保险'),
    ('Catastrophe Bond', '巨灾债券'),
    ('Weather Derivative', '天气衍生品'),
    ('Insurance-Linked Security', '保险连接证券'),
    ('Side Pocket', '侧袋账户'),
    ('General Account', '一般账户'),
    ('Separate Account', '独立账户'),
    ('Policyholder', '保单持有人'),
    ('Insured', '被保险人'),
    ('Beneficiary', '受益人'),
    ('Premium', '保费'),
    ('Deductible', '免赔额'),
    ('Copayment', '共同付款'),
    ('Coinsurance', '共同保险'),
    ('Limit', '限额'),
    ('Coverage', '保险范围'),
    ('Exclusion', '除外责任'),
    ('Endorsement', '批单'),
    ('Rider', '附加险'),
    ('Binder', '临时保险单'),
    ('Certificate of Insurance', '保险凭证'),
    ('Evidence of Insurance', '保险证明'),
    ('Loss Notice', '损失通知'),
    ('Proof of Loss', '损失证明'),
    ('Adjuster', '理算师'),
    ('Claim', '索赔'),
    ('Loss Reserve', '损失准备金'),
    ('Case Reserve', '个案准备金'),
    ('IBNR Reserve', '已发生未报案准备金'),
    ('Development on Earned Premiums', '已赚保费准备金发展'),
    ('Loss Adjustment Expense Reserve', '损失调整费用准备金'),
    ('Unallocated Loss Adjustment Expenses', '未分配损失调整费用'),
    ('Direct Settlement', '直接理赔'),
    ('Reinsurance Recoverable', '再保险摊回'),
    ('Ceded Premium', '分出保费'),
    ('Ceded Losses', '分出损失'),
    ('Net Premium', '净保费'),
    ('Net Losses', '净损失'),
    ('Gross Premium', '总保费'),
    ('Gross Losses', '总损失'),
    ('Earned Premium', '已赚保费'),
    ('Unearned Premium Reserve', '未赚保费准备金'),
    ('Written Premium', '签单保费'),
    ('Inforce Premium', '有效保费'),
    ('Policy Fee', '保单费用'),
    ('Brokerage Commission', '经纪佣金'),
    ('Contingent Commission', '或有佣金'),
    ('Profit Commission', '利润佣金'),
    ('Sliding Scale Commission', '浮动佣金'),
    ('No Claims Bonus', '无赔款优待'),
    ('Experience Rating', '经验费率'),
    ('Schedule Rating', '表定费率'),
    ('Judgment Rating', '判断费率'),
    ('Loss Ratio', '赔付率'),
    ('Expense Ratio', '费用率'),
    ('Combined Ratio', '综合比率'),
    ('Underwriting Profit', '承保利润'),
    ('Underwriting Loss', '承保损失'),
    ('Investment Income', '投资收益'),
    ('Investment Gain', '投资收益'),
    ('Investment Loss', '投资损失'),
    ('Other Income', '其他收入'),
    ('Other Expense', '其他费用'),
    ('Federal Income Tax', '联邦所得税'),
    ('State Income Tax', '州所得税'),
    ('Foreign Income Tax', '外国所得税'),
    ('Deferred Tax', '递延税款'),
    ('Tax-Exempt Income', '免税收入'),
    ('Taxable Income', '应纳税所得额'),
    ('Net Income', '净利润'),
    ('Net Operating Income', '净经营收入'),
    ('Net Investment Income', '净投资收入'),
    ('Net Underwriting Gain', '净承保收益'),
    ('Net Underwriting Loss', '净承保损失'),
    ('Surplus', '盈余'),
    ('Policyholders\' Surplus', '保单持有人盈余'),
    ('Admitted Assets', '认可资产'),
    ('Non-Admitted Assets', '非认可资产'),
    ('Liabilities', '负债'),
    ('Reserves', '准备金'),
    ('Loss Reserves', '损失准备金'),
    ('Loss Adjustment Expense Reserves', '损失调整费用准备金'),
    ('Unearned Premium Reserves', '未赚保费准备金'),
    ('Other Liabilities', '其他负债'),
    ('Total Admitted Assets', '认可资产合计'),
    ('Total Liabilities', '负债合计'),
    ('Policyholders\' Surplus', '保单持有人盈余'),
    ('Gross Written Premium', '总签单保费'),
    ('Net Written Premium', '净签单保费'),
    ('Direct Premium', '直接保费'),
    ('Assumed Premium', '分入保费'),
    ('Ceded Premium', '分出保费'),
    ('Earned Premium', '已赚保费'),
    ('Incurred Losses', '已发生损失'),
    ('Paid Losses', '已付损失'),
    ('Case Incurred', '个案已发生'),
    ('IBNR', '已发生未报案'),
    ('Development', '发展'),
    ('Net Incurred Losses', '净已发生损失'),
    ('Net Paid Losses', '净已付损失'),
    ('Direct Losses Incurred', '直接已发生损失'),
    ('Assumed Losses Incurred', '分入已发生损失'),
    ('Ceded Losses Incurred', '分出已发生损失'),
    ('Loss Adjustment Expenses Incurred', '已发生损失调整费用'),
    ('Direct LAE Incurred', '直接已发生损失调整费用'),
    ('Ceded LAE Incurred', '分出已发生损失调整费用'),
    ('Net LAE Incurred', '净已发生损失调整费用'),
    ('Dividends to Policyholders', '保单持有人股息'),
    ('Federal Income Taxes', '联邦所得税'),
    ('State Income Taxes', '州所得税'),
    ('Foreign Income Taxes', '外国所得税'),
    ('Net Underwriting Gain', '净承保收益'),
    ('Net Underwriting Loss', '净承保损失'),
    ('Net Investment Income', '净投资收入'),
    ('Realized Capital Gains', '已实现资本收益'),
    ('Net Capital Gains', '净资本收益'),
    ('Other Income', '其他收入'),
    ('Net Income', '净利润'),
    ('Net Operating Gain', '净经营收益'),
    ('Net Operating Loss', '净经营损失'),
    ('Surplus Aid', '盈余补助'),
    ('Non-Operating Income', '非经营收入'),
    ('Non-Operating Loss', '非经营损失'),
    ('Extraordinary Dividends', '特别股息'),
    ('Change in Surplus', '盈余变动'),
    ('Beginning Surplus', '期初盈余'),
    ('Ending Surplus', '期末盈余'),
    ('Surplus as of December 31', '截至12月31日盈余'),
    ('Surplus as of January 1', '截至1月1日盈余'),
    ('Growth in Surplus', '盈余增长'),
    ('Return on Average Surplus', '平均盈余回报率'),
    ('Surplus Relief', '盈余释放'),
    ('Surplus Strain', '盈余压力'),
    ('Surplus Aid', '盈余补助'),
    ('Underwriting Leverage', '承保杠杆'),
    ('Net Premium Written to Surplus', '净签单保费与盈余之比'),
    ('Reserve to Surplus', '准备金与盈余之比'),
    ('Admitted Assets to Surplus', '认可资产与盈余之比'),
    ('Liabilities to Surplus', '负债与盈余之比'),
    ('Agents', '代理人'),
    ('Brokers', '经纪人'),
    ('Direct Writers', '直接承保人'),
    ('Managing General Agents', '管理总代理人'),
    ('Excess and Surplus Lines', '超额和盈余线'),
    ('Surplus Lines', '盈余线'),
    ('Admitted Market', '许可市场'),
    ('Non-Admitted Market', '非许可市场'),
    ('Residual Market', '残余市场'),
    ('Assigned Risk Plan', '强制风险计划'),
    ('Fair Access to Insurance Requirements', '保险公平准入要求'),
    ('Guaranty Fund', '担保基金'),
    ('Insolvency', '资不抵债'),
    ('Rehabilitation', '整顿'),
    ('Liquidation', '清算'),
    ('Conservatorship', '接管'),
    ('Receivership', '接管'),
    ('Scheme of Rehabilitation', '整顿方案'),
    ('Plan of Supervision', '监管计划'),
    ('Consent Order', '同意令'),
    ('Cease and Desist Order', '停止令'),
    ('Market Conduct', '市场行为'),
    ('Consumer Protection', '消费者保护'),
    ('Rate Filing', '费率备案'),
    ('Rate Approval', '费率审批'),
    ('Rate Change', '费率变更'),
    ('Rate Increase', '费率上调'),
    ('Rate Decrease', '费率下调'),
    ('Loss Cost', '损失成本'),
    ('Loss Cost Multiplier', '损失成本乘数'),
    ('Trend Factor', '趋势因子'),
    ('Development Factor', '发展因子'),
    ('Loss Development Factor', '损失发展因子'),
    ('Bornhuetter-Ferguson Method', 'Bornhuetter-Ferguson法'),
    ('Chain Ladder Method', '链梯法'),
    ('Cape Cod Method', 'Cape Cod法'),
    ('Frequency-Severity Method', '频率-严重程度法'),
    ('Actuarial Present Value', '精算现值'),
    ('Discount Rate', '折现率'),
    ('Mortality Rate', '死亡率'),
    ('Morbidity Rate', '发病率'),
    ('Persistence Rate', '续保率'),
    ('Lapse Rate', '退保率'),
    ('Surrender Rate', '退保率'),
    ('New Business Premium', '新业务保费'),
    ('Renewal Premium', '续保保费'),
    ('Persistency', '续保率'),
    ('Retention Rate', '留存率'),
    ('Churn Rate', '流失率'),
    ('Customer Acquisition Cost', '客户获取成本'),
    ('Lifetime Value', '客户终身价值'),
    ('Cross-Selling', '交叉销售'),
    ('Up-Selling', '向上销售'),
    ('Bundling', '捆绑销售'),
    ('Unbundling', '拆分销售'),
    ('Product Mix', '产品组合'),
    ('Risk Selection', '风险选择'),
    ('Underwriting', '承保'),
    ('Claims Management', '理赔管理'),
    ('Fraud Detection', '欺诈检测'),
    ('Subrogation', '代位求偿'),
    ('Salvage', '残值'),
    ('Recovery', '追偿'),
    ('Contribution', '贡献'),
    ('Deductible', '免赔额'),
    ('Limit', '限额'),
    ('Aggregate Limit', '累计限额'),
    ('Per Occurrence Limit', '每次事故限额'),
    ('Annual Aggregate Limit', '年度累计限额'),
    ('Policy Period', '保险期间'),
    ('Effective Date', '生效日期'),
    ('Expiration Date', '到期日期'),
    ('Cancellation', '取消'),
    ('Non-Renewal', '不续保'),
    ('Flat Cancellation', '中途取消'),
    ('Pro Rata Cancellation', '按比例取消'),
    ('Short-Rate Cancellation', '短期费率取消'),
    ('Reinstatement', '恢复'),
    ('Endorsement', '批单'),
    ('Amendment', '修订'),
    ('Rider', '附加险'),
    ('Waiver', '豁免'),
    ('Exclusion', '除外责任'),
    ('Condition', '条件'),
    ('Warranty', '保证'),
    ('Representation', '陈述'),
    ('Misrepresentation', '不实陈述'),
    ('Concealment', '隐瞒'),
    ('Breach of Warranty', '违反保证'),
    ('Material Misrepresentation', '重大不实陈述'),
    ('Utmost Good Faith', '最大诚信'),
    ('Indemnity Principle', '补偿原则'),
    ('Insurable Interest', '可保利益'),
    ('Subrogation Principle', '代位求偿原则'),
    ('Contribution Principle', '分摊原则'),
    ('Proximate Cause', '近因原则'),
    ('Loss Minimization', '损失最小化'),
    ('Duty to Defend', '辩护义务'),
    ('Duty to Indemnify', '赔偿义务'),
    ('Duty to Settle', '和解义务'),
    ('Bad Faith', '恶意'),
    ('Punitive Damages', '惩罚性损害赔偿'),
    ('Compensatory Damages', '补偿性损害赔偿'),
    ('Nominal Damages', '名义损害赔偿'),
    ('Statutory Damages', '法定损害赔偿'),
    ('Liquidated Damages', '约定损害赔偿'),
    ('Consequential Damages', '间接损害赔偿'),
    ('Incidental Damages', '附带损害赔偿'),
    ('Special Damages', '特别损害赔偿'),
    ('General Damages', '一般损害赔偿'),
    ('Actual Damages', '实际损害赔偿'),
    ('Exemplary Damages', '惩罚性损害赔偿'),
    ('Treble Damages', '三倍损害赔偿'),
    ('Punitive Damages', '惩罚性损害赔偿'),
    ('Attorney Fees', '律师费'),
    ('Court Costs', '诉讼费'),
    ('Interest on Judgment', '判决利息'),
    ('Pre-Judgment Interest', '判决前利息'),
    ('Post-Judgment Interest', '判决后利息'),
    ('Statute of Limitations', '诉讼时效'),
    ('Tolling', '中止'),
    ('Waiver', '放弃'),
    ('Estoppel', '禁止反言'),
    ('Laches', '懈怠'),
    ('Accord and Satisfaction', '和解与清偿'),
    ('Release', '豁免'),
    ('Covenant', '契约'),
    ('Warranty', '保证'),
    ('Representation', '陈述'),
    ('Condition Precedent', '先决条件'),
    ('Condition Subsequent', '后续条件'),
    ('Promissory Estoppel', '允诺禁反言'),
    ('Consideration', '对价'),
    ('Offer', '要约'),
    ('Acceptance', '承诺'),
    ('Counteroffer', '反要约'),
    ('Revocation', '撤销'),
    ('Rejection', '拒绝'),
    ('Option Contract', '期权合同'),
    ('Bilateral Contract', '双务合同'),
    ('Unilateral Contract', '单务合同'),
    ('Express Contract', '明示合同'),
    ('Implied Contract', '默示合同'),
    ('Quasi-Contract', '准合同'),
    ('Executed Contract', '已履行合同'),
    ('Executory Contract', '待履行合同'),
    ('Void Contract', '无效合同'),
    ('Voidable Contract', '可撤销合同'),
    ('Unenforceable Contract', '不可强制执行合同'),
    ('Illegal Contract', '非法合同'),
    ('Unconscionable Contract', '显失公平合同'),
    ('Adhesion Contract', '附合合同'),
    ('Standard Form Contract', '标准格式合同'),
    ('Boilerplate', '格式条款'),
    ('Force Majeure', '不可抗力'),
    ('Frustration of Purpose', '目的落空'),
    ('Impracticability', '不可行'),
    ('Impossibility', '不可能'),
    ('Breach of Contract', '违约'),
    ('Anticipatory Repudiation', '预期违约'),
    ('Actual Breach', '实际违约'),
    ('Material Breach', '重大违约'),
    ('Minor Breach', '轻微违约'),
    ('Partial Breach', '部分违约'),
    ('Total Breach', '全部违约'),
    ('Remedy', '救济'),
    ('Damages', '损害赔偿'),
    ('Specific Performance', '实际履行'),
    ('Injunction', '禁令'),
    ('Rescission', '撤销'),
    ('Reformation', '重订'),
    ('Restitution', '恢复原状'),
    ('Quantum Meruit', '按劳计酬'),
    ('Promissory Estoppel', '允诺禁反言'),
    ('Equitable Estoppel', '衡平禁反言'),
    ('Laches', '懈怠'),
    ('Unclean Hands', '不清之手'),
    ('Unjust Enrichment', '不当得利'),
    ('Constructive Trust', '推定信托'),
    ('Resulting Trust', '归复信托'),
    ('Express Trust', '明示信托'),
    ('Implied Trust', '默示信托'),
    ('Testamentary Trust', '遗嘱信托'),
    ('Living Trust', '生前信托'),
    ('Revocable Trust', '可撤销信托'),
    ('Irrevocable Trust', '不可撤销信托'),
    ('Discretionary Trust', '自由裁量信托'),
    ('Fixed Trust', '固定信托'),
    ('Purpose Trust', '目的信托'),
    ('Charitable Trust', '慈善信托'),
    ('Spendthrift Trust', '浪费者信托'),
    ('Protective Trust', '保护信托'),
    ('Life Insurance Trust', '人寿保险信托'),
    ('Insurance Trust', '保险信托'),
    ('Grantor Trust', '授予人信托'),
    ('Simple Trust', '简单信托'),
    ('Complex Trust', '复杂信托'),
    ('Unit Trust', '单位信托'),
    ('Investment Trust', '投资信托'),
    ('Real Estate Investment Trust', '房地产投资信托'),
    ('Mortgage-Backed Securities', '抵押贷款支持证券'),
    ('Asset-Backed Securities', '资产支持证券'),
    ('Collateralized Debt Obligation', '债务担保证券'),
    ('Collateralized Loan Obligation', '贷款担保证券'),
    ('Collateralized Mortgage Obligation', '抵押担保证券'),
    ('Mortgage-Backed Security', '抵押贷款支持证券'),
    ('Residential Mortgage-Backed Security', '住宅抵押贷款支持证券'),
    ('Commercial Mortgage-Backed Security', '商业抵押贷款支持证券'),
    ('Asset-Backed Commercial Paper', '资产支持商业票据'),
    ('Structured Investment Vehicle', '结构化投资工具'),
    ('Special Purpose Vehicle', '特殊目的载体'),
    ('Variable Interest Entity', '可变利益实体'),
    ('Qualified Special Purpose Entity', '合格特殊目的实体'),
    ('Consolidation', '合并'),
    ('Deconsolidation', '解除合并'),
    ('Variable Interest', '可变利益'),
    ('Primary Beneficiary', '主要受益人'),
    ('Qualifying Special Purpose Entity', '合格特殊目的实体'),
    ('Non-qualifying Special Purpose Entity', '不合格特殊目的实体'),
    ('Senior Securities', '优先证券'),
    ('Subordinated Securities', '次级证券'),
    ('Mezzanine Securities', '夹层证券'),
    ('Preferred Equity', '优先股权'),
    ('Common Equity', '普通股权'),
    ('Senior Debt', '优先债务'),
    ('Subordinated Debt', '次级债务'),
    ('Mezzanine Debt', '夹层债务'),
    ('Bridge Loan', '过桥贷款'),
    ('Term Loan', '定期贷款'),
    ('Revolving Credit Facility', '循环信贷额度'),
    ('Letter of Credit', '信用证'),
    ('Bank Guarantee', '银行保函'),
    ('Performance Bond', '履约保函'),
    ('Bid Bond', '投标保函'),
    ('Advance Payment Bond', '预付款保函'),
    ('Retention Bond', '保留金保函'),
    ('Maintenance Bond', '维修保函'),
    ('Warranty Bond', '保证保函'),
    ('Surety Bond', '保证债券'),
    ('Fidelity Bond', '忠诚保证'),
    ('Crime Insurance', '犯罪保险'),
    ('Fidelity Insurance', '忠诚保险'),
    ('Suretyship', '保证'),
    ('Guarantee', '担保'),
    ('Indemnity', '赔偿'),
    ('Hold Harmless', '免责'),
    ('Indemnify', '赔偿'),
    ('Reimburse', '报销'),
    ('Subrogate', '代位'),
    ('Recover', '追偿'),
    ('Salvage', '残值'),
    ('Contribution', '分摊'),
    ('Apportionment', '分摊'),
    ('Average', '海损'),
    ('Particular Average', '单独海损'),
    ('General Average', '共同海损'),
    ('Salvage', '救助'),
    ('Marine Insurance', '海上保险'),
    ('Inland Marine Insurance', '内陆运输保险'),
    ('Ocean Marine Insurance', '海洋运输保险'),
    ('Cargo Insurance', '货物保险'),
    ('Hull Insurance', '船体保险'),
    ('Protection and Indemnity Insurance', '保赔保险'),
    ('Freight Insurance', '运费保险'),
    ('Delay in Voyage', '航程延迟'),
    ('Deviation', '绕航'),
    ('Seaworthiness', '适航性'),
    ('Perils of the Sea', '海上风险'),
    ('Acts of God', '天灾'),
    ('Fortuitous Events', '意外事件'),
    ('Perils of the Sea', '海上风险'),
    ('War Risks', '战争风险'),
    ('Strikes', '罢工'),
    ('Riots', '暴乱'),
    ('Civil Commotions', '内乱'),
    ('Piracy', '海盗'),
    ('Terrorism', '恐怖主义'),
    ('Nuclear Incident', '核事故'),
    ('Pollution', '污染'),
    ('Asbestos', '石棉'),
    ('Environmental Liability', '环境责任'),
    ('Toxic Tort', '有毒侵权'),
    ('Mass Tort', '大规模侵权'),
    ('Product Liability', '产品责任'),
    ('Professional Liability', '职业责任'),
    ('Errors and Omissions', '错误与遗漏'),
    ('Directors and Officers Liability', '董事及高管责任'),
    ('Employment Practices Liability', '雇佣行为责任'),
    ('Cyber Liability', '网络责任'),
    ('Media Liability', '媒体责任'),
    ('Privacy Liability', '隐私责任'),
    ('Intellectual Property Liability', '知识产权责任'),
    ('Kidnap and Ransom', '绑架和勒索'),
    ('Political Risk', '政治风险'),
    ('Trade Credit Insurance', '贸易信用保险'),
    ('Credit Insurance', '信用保险'),
    ('Surety Bond', '保证债券'),
    ('Construction Bond', '建筑保函'),
    ('Supply Bond', '供应保函'),
    ('Maintenance Bond', '维修保函'),
    ('Subdivision Bond', '开发保函'),
    ('License and Permit Bond', '许可保函'),
    ('Customs Bond', '海关保函'),
    ('Court Bond', '法院保函'),
    ('Fiduciary Bond', '信托保函'),
    ('Public Official Bond', '公职人员保函'),
    ('Notary Bond', '公证保函'),
    ('Title Bond', '产权保函'),
    ('Utility Bond', '公用事业保函'),
    ('Miscellaneous Bond', '杂项保函'),
    ('Bond Premium', '保函保费'),
    ('Bond Penalty', '保函罚金'),
    ('Bond Limit', '保函限额'),
    ('Bond Term', '保函期限'),
    ('Bond Obligee', '保函受益人'),
    ('Bond Principal', '保函委托人'),
    ('Bond Surety', '保函保证人'),
    ('Bond Indemnity', '保函赔偿'),
    ('Bond Collateral', '保函抵押品'),
    ('Bond Power of Attorney', '保函授权书'),
    ('Bond Agreement', '保函协议'),
    ('Bond Application', '保函申请'),
    ('Bond Underwriting', '保函承保'),
    ('Bond Claims', '保函索赔'),
    ('Bond Losses', '保函损失'),
    ('Bond Recoveries', '保函追偿'),
    ('Bond Reserves', '保函准备金'),
    ('Bond Premiums Written', '保函签单保费'),
    ('Bond Premiums Earned', '保函已赚保费'),
    ('Bond In-Force', '保函有效'),
    ('Bond Cancelled', '保函取消'),
    ('Bond Expired', '保函到期'),
    ('Bond Renewed', '保函续期'),
    ('Bond Extended', '保函延期'),
    ('Bond Modified', '保函修改'),
    ('Bond Amended', '保函修订'),
    # ---- 其他常见术语 ----
    ('shareholder', '股东'),
    ('shareholders', '股东'),
    ('book value', '账面价值'),
    ('per-share book value', '每股账面价值'),
    ('operating earnings', '经营收益'),
    ('float', '浮存金'),
    ('insurance float', '保险浮存金'),
    ('S&P 500', '标普500'),
    ('annual meeting', '年度股东大会'),
]

# ===== 公司名保护列表 =====
# 这些是公司/机构名称，在翻译时应保持原文不翻译
# 匹配方式：精确匹配（忽略大小写和末尾标点）
_COMPANY_NAMES = [
    # 巴菲特主要持仓
    'Berkshire Hathaway', 'Blue Chip Stamps', 'Wesco Financial',
    'Government Employees Insurance Company', 'GEICO', 'GEICO Corp',
    'National Indemnity Company', 'National Fire and Marine',
    'Capital Cities Communications', 'Capital Cities/ABC',
    'The Coca-Cola Company', 'Coca-Cola', 'The Coca-Cola Co',
    'American Express Company', 'American Express',
    'The Washington Post Company', 'Washington Post',
    'The Walt Disney Company', 'Walt Disney', 'Disney',
    'Wells Fargo', 'Wells Fargo & Company',
    'The Gillette Company', 'Gillette',
    'Apple', 'Apple Inc', 'Apple Inc.',
    'Bank of America', 'Bank of America Corp',
    'American Airlines', 'US Airways', 'USAir Group',
    'IBM', 'International Business Machines',
    'Amazon', 'Amazon.com', 'Amazon.com Inc',
    'JPMorgan Chase', 'JPMorgan',
    'Goldman Sachs', 'Morgan Stanley',
    'Verizon', 'Verizon Communications',
    'Exxon Mobil', 'Exxon', 'Exxon Corporation',
    'Chevron', 'ConocoPhillips', 'Phillips 66',
    'General Motors', 'General Motors Corp',
    'General Electric', 'General Electric Co',
    'Procter & Gamble', "Procter and Gamble",
    'Johnson & Johnson', 'Johnson and Johnson',
    'Kraft Heinz', 'Kraft Foods', 'Heinz',
    'Tesco', 'Wal-Mart', 'Walmart',
    'Home Depot', 'Costco', 'Coca-Cola Enterprises',
    'Moody\'s', "McDonald's", 'McDonald\'s Corporation',
    'Salomon Inc', 'Salomon Brothers',
    'Guinness PLC', 'Cadbury Schweppes',
    'Freddie Mac', 'Federal Home Loan Mortgage',
    'Fannie Mae', 'Federal National Mortgage',
    'PNC Bank', 'PNC Bank Corporation',
    'San Juan Basin Royalty Trust',
    'First Empire State', 'Snapple Beverage',
    'Dexter Shoe', 'H.H. Brown', 'Justin Brands',
    'Shaw Industries', 'Clayton Homes', 'Marmon',
    'Iscar', 'IMC International Metalworking',
    'BYD', 'BYD Company',
    'PetroChina', 'PetroChina Company',
    'BNSF', 'Burlington Northern Santa Fe',
    'Lubrizol', 'Marmon Group',
    'Precision Castparts', 'Duracell',
    'Kraft Heinz', 'H.J. Heinz',
    'Charter Communications',
    'Liberty Media', 'Liberty Global',
    'Verisign', 'DaVita',
    'American International Group', 'AIG',
    'M&T Bank', 'M&T Bank Corporation',
    'Toronto-Dominion Bank', 'Bank of Montreal',
    'US Bancorp', 'U.S. Bancorp',
    'Bank of New York Mellon',
    'Mitsubishi', 'Mitsui', 'Itochu', 'Marubeni',
    'Sumitomo', 'Toyota', 'Honda', 'Nissan',
    'Samsung', 'Hyundai', 'LG',
    'Alibaba', 'Tencent', 'Baidu',
    'Snowflake', 'Snowflake Inc',
    'StoneCo', 'StoneCo Ltd',
    'Dominion Energy', 'Dominion Energy Inc',
    'Occidental Petroleum', 'Occidental',
    'Chevron', 'Merck', 'Merck & Co',
    'Activision Blizzard', 'Activision',
    'Paramount Global', 'ViacomCBS',
    'Citi', 'Citigroup', 'Citigroup Inc',
    'HP', 'Hewlett-Packard',
    'Intel', 'Advanced Micro Devices', 'AMD',
    'NVIDIA', 'Nvidia',
    'Microsoft', 'Microsoft Corp',
    'Alphabet', 'Google', 'Google Alphabet',
    'Meta', 'Meta Platforms', 'Facebook',
    'Netflix', 'Netflix Inc',
    'Tesla', 'Tesla Inc',
    'Uber', 'Uber Technologies',
    'Lyft', 'Airbnb',
    'Salesforce', 'Salesforce Inc',
    'Oracle', 'Oracle Corp',
    'Adobe', 'Adobe Inc',
    'Visa', 'Mastercard',
    'PayPal', 'PayPal Holdings',
    'Square', 'Block Inc',
    'Shopify', 'Shopify Inc',
    'Stripe', 'Palantir',
    'Snowflake', 'Snowflake Inc',
    'Unity', 'Unity Technologies',
    'Roblox', 'Roblox Corp',
    'Coinbase', 'Coinbase Global',
    'Robinhood', 'Robinhood Markets',
    # 巴菲特旗下子公司
    'Berkshire Hathaway Energy', 'BHE',
    'BNSF Railway', 'Burlington Northern',
    'Shaw Industries', 'Benjamin Moore',
    'Johns Manville', 'Acme Brick',
    'MiTek', 'International Dairy Queen',
    'Pampered Chef', 'Garan',
    'Forest River', 'Clayton Homes',
    'CORT Business Services', 'Business Wire',
    'FlightSafety International', 'NetJets',
    'Marmon Holdings', 'Russell Brands',
    'Brooks Sports', 'Fruit of the Loom',
    'Justin Brands', 'H.H. Brown',
    'Larson-Juhl', 'Ben Bridge Jeweler',
    'Helzberg Diamonds', 'Borsheims',
    'Jordan\'s Furniture', 'R.C. Willey',
    'Star Furniture', 'NFM', 'Nebraska Furniture Mart',
    'See\'s Candies', 'See\'s Candy',
    'Dairy Queen', 'DQ',
    # 保险公司
    'Gen Re', 'General Re', 'General Reinsurance',
    'Swiss Re', 'Munich Re',
    'Allianz', 'AXA', 'Zurich Insurance',
    'Chubb', 'AIG', 'Travelers',
    'Hartford Financial', 'Prudential Financial',
    'MetLife', 'Lincoln National',
    # 历史持仓
    'Capital Cities', 'ABC', 'American Broadcasting',
    'Affiliated Publications', 'Gannett',
    'Knight-Ridder', 'Times Mirror',
    'R. J. Reynolds', 'Reynolds Industries',
    'General Foods', 'Beatrice Companies',
    'Time Inc', 'Time Warner', 'Warner Bros',
    'Media General', 'SAFECO',
    'Kaiser Aluminum', 'Aluminum Company of America', 'Alcoa',
    'Handy & Harman', 'Handy and Harman', 'National Student Marketing',
    'Interpublic Group',
    'Ogilvy & Mather', 'Northwest Industries',
    'Lear Siegler', 'ACF Industries',
    'Amerada Hess', 'Federal Home Loan',
    'Champion International', 'Diversified Retailing',
    'Blue Chip Stamps', 'Associated Retail Stores',
    'Illinois National Bank', 'Rockford Bank',
    'Cornhusker Casualty', 'Lakeland Fire',
    'Texas United Insurance', 'Insurance Company of Iowa',
    'Kansas Fire and Casualty', 'Home and Automobile',
    'Central Fire and Casualty', 'Cypress Insurance',
    'Kerkling Reinsurance',
    # 其他知名公司
    'BlackRock', 'Vanguard', 'State Street',
    'Blackstone', 'KKR', 'Carlyle Group',
    'SoftBank', 'Berkshire Partners',
    '3M', '3M Company',
    'Boeing', 'Caterpillar', 'Deere',
    'Eli Lilly', 'Abbott Laboratories', 'AbbVie',
    'UnitedHealth', 'UnitedHealth Group',
    'CVS Health', 'Pfizer',
]

# 构建公司名查找集合（小写化，去末尾标点）
_COMPANY_SET = set()
for name in _COMPANY_NAMES:
    _COMPANY_SET.add(name.lower().rstrip('.,'))
    # 也添加去掉Inc/Corp/Ltd后缀的版本
    base = re.sub(r'\s+(Inc|Corp|Corporation|Ltd|LLC|PLC|Co|Company|Group|Holdings|Stamps|Candies)\.?$', '', name, flags=re.IGNORECASE).strip()
    if base and len(base) > 3:
        _COMPANY_SET.add(base.lower().rstrip('.,'))

def _is_company_name(text):
    """检查文本是否是公司名称（应保持原文不翻译）"""
    t = text.strip().rstrip('.,')
    tl = t.lower()
    # 公司名通常很短：超过15个词的文本几乎不可能是公司名
    if len(t.split()) > 15:
        return False
    # 精确匹配
    if tl in _COMPANY_SET:
        return True
    # 检查是否包含Inc/Corp/Ltd等公司后缀
    if re.search(r'\b(Inc|Corp|Corporation|Ltd|LLC|PLC|Co|Company|Group|Holdings|Partners|Associates|Enterprises|Industries|International|Communications|Broadcasting|Publications|Airlines|Motors|Financial|Insurance|Reinsurance|Securities|Investments|Energy|Railway|Railroad)\.?$', t, re.IGNORECASE):
        # 公司名通常<=8个词
        if 2 <= len(t.split()) <= 8:
            return True
    # Bank和Trust需要更严格的检测：前面必须是专有名词（首字母大写）
    if re.search(r'[A-Z][a-z]+\s+(Bank|Trust)\.?$', t):
        if len(t.split()) <= 8:
            return True
    return False

# 构建查找结构：按长度降序排列（优先匹配长术语）
_TERM_SORTED = sorted(_TERM_DICT, key=lambda x: len(x[0]), reverse=True)

def _term_translate(text):
    """术语翻译：匹配术语表返回标准翻译，未匹配返回None"""
    t = text.strip()
    # 精确匹配
    for en, zh in _TERM_SORTED:
        if t == en:
            return zh if zh is not None else en
    # 前缀匹配（仅处理简短后缀：括号注释、数字、逗号分隔）
    # 不匹配后面还有大段文本的情况（避免 "GEICO, 38%-owned by Berkshire..." 被错误匹配）
    for en, zh in _TERM_SORTED:
        if t.startswith(en) and len(t) > len(en) and t[len(en)] in ('(', '（', ',', '.'):
            rest = t[len(en):].strip()
            # 只匹配短文本（避免整个段落被当作术语前缀）
            if len(rest) > 60:
                continue
            if zh is not None:
                return zh + rest
            else:
                return en + rest
        # 空格后缀：仅当剩余文本很短（<=30字符）时匹配
        if t.startswith(en) and len(t) > len(en) and t[len(en)] == ' ':
            rest = t[len(en):].strip()
            if len(rest) <= 30:
                if zh is not None:
                    return zh + ' ' + rest
                else:
                    return en + ' ' + rest
        # 数字后缀：如 "Col " + "4" -> "第" + "4"
        if t.startswith(en) and len(t) > len(en) and t[len(en):].strip().isdigit():
            rest = t[len(en):].strip()
            if zh is not None:
                return zh + rest
            else:
                return en + rest
    return None

def _post_process_translation(zh_text, en_text=''):
    """翻译后处理：修复常见翻译质量问题"""
    t = zh_text
    # 0. 修复巴菲特相关专有名词的错误翻译
    t = t.replace('蓝筹股邮票', '蓝筹印花')
    t = t.replace('蓝筹股', '蓝筹印花')  # Blue Chip Stamps 不是"蓝筹股"
    t = re.sub(r'的手术', '的业务', t)  # "operation"在商业语境应为"业务"不是"手术"
    t = re.sub(r'结束了他的手术', '结束了他的业务', t)
    # 1. 修复公司名后多余中文句号：Inc。Corp。Ltd。→ Inc. Corp. Ltd.
    # 中文翻译器常把英文缩写后的点改成中文句号
    for abbr in ['Inc', 'Corp', 'Ltd', 'Co', 'Mr', 'Mrs', 'Dr', 'Jr', 'Sr', 'St', 'Ave', 'Blvd']:
        t = re.sub(r'(?<=' + abbr + r')\u3002', '.', t)
    # 2. 修复 "给...的股东。：" 中的多余句号
    t = re.sub(r'的股东。：', '的股东：', t)
    t = re.sub(r'的股东。', '的股东', t)
    # 3. 修复公司名后紧跟句号再加中文的情况
    # 如 "Berkshire Hathaway Inc.是" 不应变成 "伯克希尔哈撒韦公司。是"
    t = re.sub(r'公司。\s*([^，。；！？\s])', r'公司\1', t)
    t = re.sub(r'公司。(\s*[，。；！？])', r'公司\1', t)
    # 4. 去除翻译中残留的单独英文句号（不在缩写中）
    # 5. 修复 "。" 后紧跟 ":" 的情况
    t = re.sub(r'。:', '：', t)
    return t

def translate_text(text,cache,key):
    if not text or not text.strip(): return text
    text=text.strip()
    if is_pure_number(text) or len(text)<3: return text
    # 公司名保护：如果是公司名称，保持原文不翻译
    if _is_company_name(text):
        return text
    # 术语保护：专有名词和财务术语使用标准翻译
    term_zh = _term_translate(text)
    if term_zh is not None:
        term_zh = _post_process_translation(term_zh, text)
        cache[key]=term_zh; return term_zh
    if key in cache:
        cached_val = cache[key]
        # 如果缓存值不包含中文，说明可能是错误的缓存（如翻译失败时保存了原文），需要重新翻译
        if has_chinese(cached_val):
            return _post_process_translation(cached_val, text)
        # 缓存值没有中文，删除该缓存条目并继续重新翻译
        del cache[key]
    if len(text)>800:
        sents=re.split(r'(?<=[.!?])\s+',text)
        chunks,cur=[],""
        for s in sents:
            if len(cur)+len(s)>800 and cur: chunks.append(cur.strip()); cur=s
            else: cur=cur+" "+s if cur else s
        if cur.strip(): chunks.append(cur.strip())
        fc=[]
        for c in chunks:
            while len(c)>800: fc.append(c[:800]); c=c[800:]
            if c.strip(): fc.append(c.strip())
        parts=[translate_text(c,cache,f"{key}_p{ci}") for ci,c in enumerate(fc)]
        r=" ".join(parts); cache[key]=r; return r
    with translate_lock:
        for att in range(3):
            try:
                r=translator.translate(text,"zh"); t=str(r)
                if t and has_chinese(t):
                    t = _post_process_translation(t, text)
                    cache[key]=t; return t
                time.sleep(1)
            except Exception as e:
                if att == 2:
                    print(f"  翻译失败(3次): {text[:40]}... err={e}",flush=True)
                time.sleep(min(2 ** att, 10))  # 指数退避: 1s, 2s, 4s
    return text

def read_file_auto(fp):
    for enc in ["utf-8","windows-1252","latin-1"]:
        try:
            with open(fp,'r',encoding=enc) as f: return f.read()
        except: continue
    return ""

def text_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

def is_separator(text):
    clean = re.sub(r'\s+', '', text)
    return bool(re.match(r'^[\*\-\_]+$', clean)) and len(clean) >= 3

def is_data_row(text):
    """检测单行数据行（标签+点号+数字，不需要翻译）"""
    continuous_dots = re.findall(r'\.{3,}', text)
    spaced_dots = re.findall(r' \. \. ', text)
    dot_count = len(continuous_dots) + len(spaced_dots)
    if dot_count < 1: return False
    has_nums = bool(re.search(r'\d', text))
    if not has_nums: return False
    cleaned = re.sub(r'[\.\s\$\%\,\(\)\d\-\*]+', '', text).strip()
    return len(cleaned) < 30

def is_table_block(text):
    """检测多行表格block"""
    continuous_dots = re.findall(r'\.{3,}', text)
    spaced_dots = re.findall(r' \. \. ', text)
    dot_count = len(continuous_dots) + len(spaced_dots)
    has_dollar = '$' in text
    number_count = len(re.findall(r'\$[\s\d,]+|[\d,]+\.\d{0,2}\b|\([\d,]+\)', text))
    # 也统计逗号分隔的大数字（如 151,610,700），Investment表没有$符号
    comma_num_count = len(re.findall(r'\d{1,3}(?:,\d{3}){1,}', text))
    total_nums = max(number_count, comma_num_count)
    # 阈值1：3+个点号行且含$或多个数字
    if dot_count >= 3 and (has_dollar or total_nums >= 3):
        return True
    # 阈值2：2+个点号行且含$和多个数字
    if dot_count >= 2 and has_dollar and total_nums >= 2:
        return True
    # 阈值3：包含大量$符号（5+）和数字（财务数据表）
    dollar_count = text.count('$')
    if dollar_count >= 5 and total_nums >= 3:
        return True
    # 阈值4：大量点号（10+）且大量逗号分隔数字（如Investment持仓表）
    if dot_count >= 10 and comma_num_count >= 5:
        return True
    return False

def _parse_vertical_header_table(header_blocks, data_text, summary_text=None):
    """解析垂直表头表格（如2017年scorecard表：Year/Fund-of-Funds各占一个block）
    header_blocks: 表头block列表（如 ['Year', 'Fund-of-Funds A', ..., 'S&P Index Fund']）
    data_text: 数据文本（如 '2008 -16.5% -22.3% ... 2017 21.1% ...'）
    summary_text: 汇总行文本（如 'Final Gain 21.7% ... Average Annual Gain 2.0% ...'）
    """
    rows = []
    # 表头行
    headers = [h.strip() for h in header_blocks if h.strip()]
    if len(headers) >= 2:
        rows.append(headers)
    
    # 确定列数
    num_cols = len(headers)
    
    # 解析数据行：按年份分割（4位年份开头）
    year_pattern = re.compile(r'(\d{4})\s+')
    segments = year_pattern.split(data_text)
    # segments格式：[前缀, 年份1, 数据1, 年份2, 数据2, ...]
    for si in range(1, len(segments), 2):
        year = segments[si].strip()
        data = segments[si + 1] if si + 1 < len(segments) else ''
        # 提取数值（包括负数百分比）
        values = re.findall(r'[\-]?\d+\.?\d*%|N/?A', data)
        values = [v.strip() for v in values if v.strip()]
        row = [year] + values[:num_cols - 1]
        # 补齐空列
        while len(row) < num_cols:
            row.append('')
        rows.append(row)
    
    # 解析汇总行（Final Gain / Average Annual Gain）
    if summary_text:
        # 按关键词分割
        summary_parts = re.split(r'(?=Final\s+Gain|Average\s+Annual)', summary_text)
        for sp in summary_parts:
            sp = sp.strip()
            if not sp: continue
            label_match = re.match(r'(Final\s+Gain|Average\s+Annual\s+Gain)\s*', sp)
            if label_match:
                label = label_match.group(1)
                after = sp[label_match.end():]
                values = re.findall(r'[\-]?\d+\.?\d*%', after)
                values = [v.strip() for v in values if v.strip()]
                row = [label] + values[:num_cols - 1]
                while len(row) < num_cols:
                    row.append('')
                rows.append(row)
    
    return rows if len(rows) >= 3 else None

def _parse_col_aligned_table(header_text, data_text, total_text=None):
    """解析列对齐格式的表格（如Yearend Ownership表）
    格式：公司名 XX.X% $ NNN NNN 公司名 XX.X% $ NNN NNN ...
    """
    rows = []
    # 解析表头 - 用多种方式分割
    header_parts = re.split(r'\s{2,}', header_text)
    header_parts = [p.strip() for p in header_parts if p.strip()]
    # 过滤纯数字和单位
    data_header = [p for p in header_parts if not re.match(r'^[\d\(\)]+$', p)]
    
    # 如果双空格分割只得到1个元素，尝试用关键词分割
    if len(data_header) <= 1:
        # Yearend Ownership格式：Berkshire's Share (in millions) Company Dividends(1) Retained Earnings(2)
        # 注意：不分割 "Premium Volume" 和 "Percentage Decrease" 等组合列名
        kw_split = re.split(r'(?=(?:Company|Dividends\(\d\)|Retained\s+Earnings|Earnings\(\d\)|Yearend\s+Ownership))\b', header_text)
        kw_split = [p.strip() for p in kw_split if p.strip()]
        # 清理：移除括号中的单位说明
        cleaned = []
        for p in kw_split:
            p = re.sub(r'^\((?:in\s+)?[\w\s,]+\)\s*', '', p).strip()
            if p:
                cleaned.append(p)
        if len(cleaned) >= 2:
            data_header = cleaned
        else:
            # 最后手段：按空格分割为单词
            data_header = header_text.split()
    
    # 解析数据行用的正则（提前定义，后面多处引用）
    # 匹配公司名+百分比，数值部分用findall从剩余文本中提取
    company_label_pattern = re.compile(r"([A-Z][A-Za-z\s.'\u2019\&\*,\-]+?)\s+([\d.]+%)")

    if data_header:
        # 先添加表头，数据解析后再根据实际列数合并
        rows.append(data_header)

    # 解析数据行：按公司名模式分割
    # 模式：公司名(可能含.和,) + 百分比 + ($数字 数字)+
    label_matches = list(company_label_pattern.finditer(data_text))
    for li in range(len(label_matches)):
        company = label_matches[li].group(1).strip().rstrip('.')
        pct = label_matches[li].group(2)
        # 数值区域：从当前匹配结束到下一个匹配开始
        val_start = label_matches[li].end()
        val_end = label_matches[li + 1].start() if li + 1 < len(label_matches) else len(data_text)
        vals_str = data_text[val_start:val_end]
        nums = re.findall(r'[\$]?\s*[\d,]+|\([\d,]+\)', vals_str)
        nums = [n.strip() for n in nums if n.strip()]
        rows.append([company, pct] + nums)
    
    # 如果没有匹配到公司模式，检测数据格式
    if len(label_matches) == 0:
        # 检测是否包含日期范围格式（如 "March 1973-January 1975"）
        has_date_range = bool(re.search(r'[A-Z][a-z]+\s+\d{4}\s*[-–]', data_text))
        
        if has_date_range:
            # 按日期范围分割（如Period/High/Low格式）
            date_pattern = re.compile(
                r'((?:[A-Z][a-z]+\s+)?\d{1,4}(?:/\d{1,2})?(?:/\d{2,4})?'
                r'(?:\s*[-–]\s*(?:[A-Z][a-z]+\s+)?\d{1,4}(?:/\d{1,2})?(?:/\d{2,4})?))'
            )
            date_matches = list(date_pattern.finditer(data_text))
            if len(date_matches) >= 2:
                for di in range(len(date_matches)):
                    label = date_matches[di].group(1).strip()
                    val_start = date_matches[di].end()
                    val_end = date_matches[di + 1].start() if di + 1 < len(date_matches) else len(data_text)
                    val_region = data_text[val_start:val_end]
                    vals = re.findall(r'[\$]?\s*[\d,]+(?:\.\d+)?%?|\([^)]+\)', val_region)
                    vals = [v.strip() for v in vals if v.strip()]
                    if vals:
                        rows.append([label] + vals)
        
        if not has_date_range or len(rows) <= 1:
            # 按年份分割（如Year Premium Volume Float表）
            # 按年份分割：1970 $ 39 $ 39 1980 185 237 ...
            # 使用非贪婪匹配，遇到下一个4位年份就停止
            year_pattern = re.compile(r'(\d{4})\s+((?:\$?\s*[\d,]+(?:\s+(?!\d{4}\s))*)+)')
            year_matches = year_pattern.findall(data_text)
            # 如果非贪婪匹配失败，用split方式
            if not year_matches or len(year_matches) < 2:
                # 按年份位置分割
                year_positions = [(m.start(), m.group(1)) for m in re.finditer(r'(?<!\d)(\d{4})(?!\d)', data_text)]
                for yi in range(len(year_positions)):
                    year = year_positions[yi][1]
                    start = year_positions[yi][0] + 4
                    end = year_positions[yi + 1][0] if yi + 1 < len(year_positions) else len(data_text)
                    vals_str = data_text[start:end]
                    nums = re.findall(r'[\$]?\s*[\d,]+', vals_str)
                    nums = [n.strip() for n in nums if n.strip()]
                    rows.append([year] + nums)
            else:
                for year, vals_str in year_matches:
                    nums = re.findall(r'[\$]?\s*[\d,]+', vals_str)
                    nums = [n.strip() for n in nums if n.strip()]
                    rows.append([year] + nums)

    # 数据解析完成后，根据实际数据列数合并表头
    if len(rows) >= 2 and len(rows[0]) > 1:
        header = rows[0]
        # 计算数据行的实际列数（取众数）
        col_counts = {}
        for r in rows[1:]:
            c = len(r)
            col_counts[c] = col_counts.get(c, 0) + 1
        if col_counts:
            data_cols = max(col_counts, key=col_counts.get)
        else:
            data_cols = len(header)
        
        # 如果表头列数比数据列数多，智能合并
        while len(header) > data_cols and len(header) > 2:
            merged = False
            known_pairs = [
                ('Percentage', 'Decrease'),
                ('Retained', 'Earnings'),
                ('Premium', 'Volume'),
                ('Yearly', 'Change'),
                ('Policy-holder', 'Dividends'),
            ]
            for p1, p2 in known_pairs:
                for hi in range(len(header) - 1):
                    if header[hi] == p1 and header[hi + 1] == p2:
                        header[hi] = p1 + ' ' + p2
                        header.pop(hi + 1)
                        merged = True
                        break
                if merged:
                    break
            if not merged:
                last = len(header) - 1
                header[last - 1] = header[last - 1] + ' ' + header[last]
                header.pop(last)
        rows[0] = header
    
    # Yearend Ownership表特殊处理：移除跨列标题，重排列顺序
    if len(rows) >= 2 and rows[0]:
        h_texts = [str(c) for c in rows[0]]
        if any('Yearend Ownership' in h for h in h_texts) and any('Company' in h for h in h_texts):
            # 移除 "Berkshire's Share" 跨列标题
            header = [h for h in rows[0] if 'Berkshire' not in str(h)]
            # 重排：Company放第一列，Yearend Ownership放第二列
            company_idx = next((i for i, h in enumerate(header) if 'Company' in str(h) and 'Dividends' not in str(h)), None)
            yearend_idx = next((i for i, h in enumerate(header) if 'Yearend' in str(h)), None)
            if company_idx is not None and yearend_idx is not None:
                # 移除Company和Yearend，然后在前面插入
                company_val = header.pop(company_idx)
                yearend_val = header.pop(yearend_idx - (1 if yearend_idx > company_idx else 0))
                header.insert(0, company_val)
                header.insert(1, yearend_val)
            # 分割 "Dividends(1) Retained Earnings(2)" 如果合并了
            final_header = []
            for h in header:
                if 'Dividends' in str(h) and 'Retained' in str(h):
                    # 分割为两个
                    parts = re.split(r'\s+(?=Retained)', str(h))
                    final_header.extend(parts)
                else:
                    final_header.append(h)
            rows[0] = final_header

    # 解析Total行
    if total_text:
        total_nums = re.findall(r'\$?\s*[\d,]+|\([\d,.]+\)', total_text)
        total_label = re.match(r'(Total[^\d]*)', total_text)
        if total_label and total_nums:
            total_row = [total_label.group(1).strip()]
            # 根据数据行列数对齐
            data_cols = max(len(r) for r in rows[1:]) if len(rows) > 1 else len(total_nums) + 1
            # Total行通常第一列是标签，后面是数值
            # 如果数值比数据列少，在标签后补空列
            empty = data_cols - 1 - len(total_nums)
            total_row.extend([''] * max(0, empty))
            total_row.extend([n.strip() for n in total_nums])
            rows.append(total_row)
    
    return rows if len(rows) >= 3 else None

def parse_table_from_text(text):
    """将点号引导的表格文本解析为结构化数据"""
    rows = []
    text = re.sub(r'\.{4,}', ' . . . . ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 检查是否以表头关键词开头（如 "Shares Company" 或 "Percentage of Company Owned"）
    header_keywords = ['Shares', 'Company', 'Percentage', 'Cost', 'Market', 'No.', 'Name']
    header_line = None
    num_header_cols = 0  # 表头列数，用于Others/Total行对齐
    remaining = text
    
    # 尝试提取表头行（在数据之前）
    # 模式：表头关键词 + 可选的单位行 + 数据行
    # 表头行通常以大写字母开头，不包含点号
    lines = text.split('\n')
    if len(lines) == 1:
        # 单行文本，尝试从中分离表头和数据
        # 查找第一个数据行的开始位置（以数字开头或包含点号+数字）
        data_start = None
        for m in re.finditer(r'(?:^|\s)(\d{1,3}(?:,\d{3})+(?:\.\d+)?)\s+[A-Z]', text):
            pos = m.start()
            if pos > 10:  # 表头至少有10个字符
                data_start = pos
                break
        if data_start is None:
            # 尝试查找 "Shares" 或 "Company" 后面的数据开始
            for kw in ['Shares', 'Company']:
                idx = text.find(kw)
                if idx >= 0:
                    # 查找这个关键词后面的空格+数字模式
                    rest = text[idx + len(kw):]
                    m = re.search(r'\s+(\d{1,3}(?:,\d{3})+)\s', rest)
                    if m:
                        data_start = idx + len(kw) + m.start()
                        break
        
        if data_start:
            potential_header = text[:data_start].strip()
            # 检查是否包含表头关键词
            if any(kw in potential_header for kw in header_keywords):
                header_line = potential_header
                remaining = text[data_start:].strip()
    
    if header_line:
        # 解析表头：分离日期、列名和单位
        # 先尝试按双空格分割
        header_parts = re.split(r'\s{2,}', header_line)
        header_parts = [p.strip() for p in header_parts if p.strip()]
        # 过滤掉纯数字
        header_parts = [p for p in header_parts if not re.match(r'^[\d\(\)]+$', p)]
        
        if len(header_parts) <= 2:
            # 没有双空格分割，用关键词分割
            # 提取日期（如 12/31/21）
            date_match = re.match(r'^(\d{1,2}/\d{1,2}/\d{2,4})\s*', header_line)
            date_text = date_match.group(1) if date_match else ''
            rest = header_line[date_match.end():].strip() if date_match else header_line
            
            # 提取单位（如 (in millions)）
            unit_match = re.search(r'\(in\s+millions?\)', rest, re.I)
            unit_text = unit_match.group(0) if unit_match else ''
            if unit_text:
                rest = rest.replace(unit_text, '').strip()
            
            # 分离列名关键词
            # 已知关键词：Shares, Company, Percentage of Company Owned, Cost*, Market
            # 注意：有些年份表头用 "Cost" 而非 "Cost*"，用 "No. of Shares" 而非 "Shares"
            col_names = []
            # 按位置排序的关键词（长词优先，避免短词误匹配）
            kw_list = ['Percentage of Company Owned', 'No. of Shares or Share Equiv.',
                       'No. of Shares', 'Company', 'Shares', 'Cost*', 'Cost', 'Market']
            pos = 0
            for kw in kw_list:
                idx = rest.find(kw, pos)
                if idx >= 0:
                    col_names.append(kw)
                    pos = idx + len(kw)
            
            if col_names:
                rows.append(col_names)
                num_header_cols = len(col_names)  # 记录表头列数，用于Others/Total行对齐
            if unit_text:
                rows.append([unit_text])
            if date_text:
                rows.insert(0, [date_text])
        else:
            # 有双空格分割，分离单位行和列名行
            unit_parts = [p for p in header_parts if re.match(r'^\(.*\)$', p)]
            data_header_parts = [p for p in header_parts if not re.match(r'^\(.*\)$', p)]
            # 列名行：作为第一行
            if data_header_parts:
                rows.append(data_header_parts)
                num_header_cols = len(data_header_parts)  # 记录表头列数
            # 单位行：作为第二行（如果有）
            if unit_parts:
                rows.append(unit_parts)
    
    # 解析数据行
    # 方法1：先用两步法按点号序列分割，然后判断每行格式
    # 适用于所有点号引导的表格，包括Investment持仓表
    normalized = re.sub(r' \.', '·', remaining)
    normalized = re.sub(r'·{3,}', ' /// ', normalized)
    segments = normalized.split(' /// ')
    segments = [s.strip() for s in segments if s.strip()]
    
    # 数字提取正则：匹配 $1,234 / 1,234 / 1,234.56 / (1,234) / 19.9% 等
    # 关键：避免匹配独立的逗号（如 "Communications, Inc." 中的逗号）
    num_pattern = re.compile(r'\$?\s*\d{1,3}(?:,\d{3})+(?:\.\d{0,2})?%?|\$?\s*\d+(?:\.\d{0,2})?%?|\(\d{1,3}(?:,\d{3})+\)')
    
    if segments:
        # 判断格式：检查第一个segment是否以数字开头（Investment格式）
        first_seg = segments[0]
        is_shares_format = bool(re.match(r'^[\d,]+\s+[A-Z]', first_seg))
        
        # 检查是否是年份格式的表格（如Insurance统计表：1972 . . . 10.2 10.9 96.2）
        is_year_format = bool(re.match(r'^\d{4}\s', first_seg))
        
        if is_shares_format:
            # Investment格式：Shares Company . . . Percentage Cost Market
            current_row = None
            for seg in segments:
                m = re.match(r'^([\d,]+)\s+([A-Za-z][\w\s\.\'\&\*,]+)', seg)
                if m:
                    if current_row:
                        rows.append(current_row)
                    shares = m.group(1)
                    company = m.group(2).strip().rstrip('.')
                    current_row = [shares, company]
                elif current_row:
                    nums = num_pattern.findall(seg)
                    # 检查segment中是否包含 Others/Total 等汇总关键词
                    others_match = re.search(r'(Others\*{0,3}|Total\s+\w+|Common\s+Stocks?)\s*', seg)
                    if others_match and nums:
                        # 将关键词之前的数字加到当前行
                        before_text = seg[:others_match.start()]
                        before_nums = num_pattern.findall(before_text)
                        current_row.extend([n.strip() for n in before_nums])
                        rows.append(current_row)
                        # 关键词+后面的数字作为新行
                        label = others_match.group(1).strip()
                        after_text = seg[others_match.end():]
                        after_nums = num_pattern.findall(after_text)
                        # 对齐到表头列数：Others/Total行没有Shares和Percentage
                        # 格式：['', label, '', val1, val2, ...]
                        if num_header_cols > 0 and num_header_cols > len(after_nums) + 1:
                            # 表头有Shares和Percentage列，Others/Total行这些列为空
                            nhc = num_header_cols
                            new_row = ['']  # Shares为空
                            new_row.append(label)  # Company
                            # 填充空列（Percentage等）
                            empty_cols = nhc - 1 - len(after_nums) - 1
                            new_row.extend([''] * max(0, empty_cols))
                            new_row.extend([n.strip() for n in after_nums])
                            current_row = new_row
                        else:
                            current_row = [label] + [n.strip() for n in after_nums]
                        continue
                    # 检查segment文本中是否有大整数后跟公司名的模式（行边界）
                    # 搜索所有 "大数字(7+字符) + 空格 + 大写字母" 的位置
                    boundary_found = False
                    for bm in re.finditer(r'([\d,]{7,})\s+([A-Z][A-Za-z\s\.\'\&\*,\-]{2,})', seg):
                        b_num = bm.group(1)
                        b_company = bm.group(2).strip().rstrip('.')
                        # 验证这个大数字确实是Shares（后面跟着合理的公司名）
                        if len(b_company) < 3:
                            continue
                        # 从nums中找到这个数字的位置
                        for ni in range(len(nums) - 1, -1, -1):
                            if b_num in nums[ni]:
                                # 这个数字及之后的所有数字属于下一行
                                current_row.extend([n.strip() for n in nums[:ni]])
                                rows.append(current_row)
                                current_row = [b_num, b_company]
                                # 添加这个数字之后的其他数字
                                remaining_after = seg[bm.end():]
                                remaining_nums = num_pattern.findall(remaining_after)
                                valid_remaining = []
                                for rn in remaining_nums:
                                    rn_strip = rn.strip()
                                    if re.match(r'^\d{1,3}$', rn_strip) and int(rn_strip) < 1000:
                                        continue
                                    valid_remaining.append(rn_strip)
                                current_row.extend(valid_remaining)
                                boundary_found = True
                                break
                        if boundary_found:
                            break
                    if boundary_found:
                        continue
                    current_row.extend([n.strip() for n in nums])
                else:
                    label_match = re.match(r'^([A-Za-z\*][\w\s\.\'\&\*,\-]+?)\s+(\$?\s*[\d,]+)', seg)
                    if label_match:
                        label = label_match.group(1).strip().rstrip('.')
                        rest = seg[label_match.start(2):]
                        nums = num_pattern.findall(rest)
                        current_row = [label] + [n.strip() for n in nums]
                    else:
                        # 检查是否是纯数字segment（如 "26,629 39,972"）
                        # 可能是Others/Total行的数值
                        nums = num_pattern.findall(seg)
                        if nums and current_row and len(nums) <= 3:
                            # 如果当前行已经有5列（完整的Shares+Company+3值），开始新行
                            if len(current_row) >= 5:
                                rows.append(current_row)
                                current_row = nums
                            else:
                                current_row.extend([n.strip() for n in nums])
            if current_row:
                rows.append(current_row)
            # 后处理：对齐Others/Total行到表头列数
            if num_header_cols > 0:
                for ri in range(len(rows)):
                    r = rows[ri]
                    r_text = ' '.join(str(c) for c in r).strip()
                    if re.match(r'^(Others\*{0,3}|Total\s+\w+|Total\s+Equity)', r_text):
                        # Others/Total行：Shares为空，Company=标签，然后对齐Cost/Market
                        label = r[0] if r else ''
                        # 找到标签位置（可能在r[0]或r[1]）
                        label_idx = 0
                        for li, c in enumerate(r):
                            if c and re.match(r'^(Others\*{0,3}|Total)', str(c).strip()):
                                label = str(c).strip()
                                label_idx = li
                                break
                        # 标签之后的数值
                        vals = []
                        for c in r[label_idx+1:]:
                            if c and c.strip():
                                vals.append(c.strip())
                        aligned = ['']  # Shares为空
                        aligned.append(label)  # Company
                        # 空列数 = num_header_cols - 2(label) - len(vals)
                        empty = num_header_cols - 2 - len(vals)
                        aligned.extend([''] * max(0, empty))
                        aligned.extend(vals)
                        rows[ri] = aligned
            if len(rows) >= 2:
                return rows
        elif is_year_format:
            # 年份格式表格（如Insurance统计表）
            for seg in segments:
                seg = seg.strip()
                if not seg: continue
                # 提取年份
                year_match = re.match(r'^(\d{4})', seg)
                if not year_match:
                    year_match = re.match(r'^(\d{4})\s*\(', seg)
                if not year_match:
                    continue
                year = year_match.group(1)
                rest = seg[year_match.end():]
                # 提取数值
                values = re.findall(r'[\d.]+%?|\([\d.]+\)', rest)
                if values:
                    row = [year] + [v.strip() for v in values]
                    rows.append(row)
            if len(rows) >= 2:
                return rows
        else:
            # 普通格式：Label . . . . Numbers
            pending_label = None  # 等待匹配的标签（来自没有数字的segment）
            for seg in segments:
                seg = seg.strip()
                if not seg: continue
                has_num = bool(num_pattern.search(seg))
                
                if not has_num:
                    # 纯文本segment，保存为待匹配标签
                    pending_label = seg.strip().rstrip('.')
                    continue
                
                # 尝试label_match（标签+数字格式）
                label_match = re.match(r'^([A-Za-z\*][\w\s\.\'\&\*,\-]+?)\s+(\$?\s*[\d,]+)', seg)
                if label_match:
                    label = label_match.group(1).strip().rstrip('.')
                    rest = seg[label_match.start(2):]
                    nums = num_pattern.findall(rest)
                    if nums:
                        row = [label] + [n.strip() for n in nums]
                        rows.append(row)
                    pending_label = None
                    continue
                
                # 使用pending_label
                if pending_label:
                    label = pending_label
                    pending_label = None
                else:
                    # 备用：找最后一个非数字字符的位置
                    num_match = re.search(r'(\$?\s*[\d,]+(?:\.\d{0,2})?|\([\d,]+\))\s*$', seg)
                    if num_match:
                        num_start = num_match.start()
                        label = seg[:num_start].strip().rstrip('.')
                    else:
                        label = None
                
                if label:
                    nums = num_pattern.findall(seg)
                    if nums:
                        row = [label] + [n.strip() for n in nums]
                        rows.append(row)
                        # 检查nums之后是否有文本（可能是下一个标签）
                        last_num_end = 0
                        for nm in num_pattern.finditer(seg):
                            last_num_end = nm.end()
                        after_nums = seg[last_num_end:].strip()
                        if after_nums and not num_pattern.search(after_nums):
                            pending_label = after_nums.strip().rstrip('.')
            if len(rows) >= 2:
                return rows
    
    # 备用模式2：按 " . . " 分割
    rows = []
    if header_line:
        rows.append(header_line)
    segments = re.split(r' \. \. \.+ ', remaining)
    for seg in segments:
        seg = seg.strip()
        if not seg or len(seg) < 3: continue
        label_match = re.match(r'^([\w\s,\'\.\-]+?)\s+(\$?[\d,\(\)\.]+)', seg)
        if label_match:
            label = label_match.group(1).strip().rstrip(',')
            rest = seg[label_match.start(2):]
            nums = re.findall(r'\$?\s*[\d,]+(?:\.\d{0,2})?|\([\d,]+\)', rest)
            if nums:
                row = [label] + [n.strip() for n in nums]
                rows.append(row)
                continue
        nums = re.findall(r'[\d,]+(?:\.\d{0,2})?|\([\d,]+\)', seg)
        if len(nums) >= 2:
            rows.append(nums)
    return rows if len(rows) >= 2 else None

def split_separator(text, html):
    """将文本中的 * * * 分隔符分离出来"""
    results = []
    pattern = r'(\* (?:\* )+\*)'
    parts = re.split(pattern, text)
    for part in parts:
        part = part.strip()
        if not part: continue
        if re.match(r'^\* (\* )+\*$', part):
            results.append({'type':'separator','text':part,'html':part})
        elif len(part) >= 5:
            results.append({'type':'text','text':part,'html':part})
    return results

def esc(t): return html_mod.escape(t or '')

def _parse_html_table(tbl):
    """解析HTML表格，正确处理colspan，过滤空行和空列"""
    rows_data=[]
    max_cols=0
    for tr in tbl.find_all('tr'):
        cells=[]
        for td in tr.find_all(['th','td']):
            text=td.get_text(strip=True)
            colspan=int(td.get('colspan',1))
            # 跳过超链接内的内容（通常是页脚链接）
            skip=False
            for a in td.find_all('a'):
                if a.get_text(strip=True) in ['1','2','3','4','5','Next']:
                    skip=True
                    break
            if skip:
                continue
            a_tags = td.find_all('a')
            if a_tags and len(a_tags)==1:
                text = a_tags[0].get_text(strip=True)
            cells.append((text,colspan))
        if cells:
            expanded=[]
            for text,colspan in cells:
                expanded.append(text)
                for _ in range(colspan-1):
                    expanded.append('')
            rows_data.append(expanded)
            max_cols=max(max_cols,len(expanded))
    for i in range(len(rows_data)):
        while len(rows_data[i])<max_cols:
            rows_data[i].append('')
    # 过滤空行
    rows_data=[row for row in rows_data if any(c.strip() for c in row)]
    # 过滤空列（所有行在该列都为空的列）
    if rows_data and max_cols>0:
        non_empty_cols=[]
        for col_idx in range(len(rows_data[0]) if rows_data else 0):
            if any(row[col_idx].strip() if col_idx<len(row) else False for row in rows_data):
                non_empty_cols.append(col_idx)
        if non_empty_cols:
            rows_data=[[row[col_idx] if col_idx<len(row) else '' for col_idx in non_empty_cols] for row in rows_data]
    return rows_data

def parse_html_source(fp):
    """解析HTML源文件 - 按照文档中的实际位置顺序处理所有元素"""
    soup=BeautifulSoup(read_file_auto(fp),'html.parser')
    for t in soup(['script','style','noscript']): t.decompose()
    blocks=[]
    
    # 收集所有需要处理的顶级元素，按文档位置排序
    # 这样HTML表格不会全部出现在<pre>内容之前
    all_elements=[]
    for tbl in soup.find_all('table'):
        in_pre=False
        parent=tbl.parent
        while parent:
            if parent.name=='pre': in_pre=True; break
            parent=parent.parent
        if in_pre: continue
        all_elements.append((tbl,'table'))
    for el in soup.find_all(['p','div','h1','h2','h3','h4','h5','h6','li','blockquote']):
        parent=el.parent
        in_pre=False
        while parent:
            if parent.name=='pre': in_pre=True; break
            parent=parent.parent
        if in_pre: continue
        all_elements.append((el,'element'))
    for pre in soup.find_all('pre'):
        all_elements.append((pre,'pre'))
    
    # 按文档位置排序：使用sourceline属性
    all_elements.sort(key=lambda x: getattr(x[0],'sourceline',0) if hasattr(x[0],'sourceline') else 0)
    
    for el_obj, el_type in all_elements:
        if el_type=='table':
            tbl=el_obj
            rows_data=_parse_html_table(tbl)
            rows_with_numbers=sum(1 for row in rows_data if any(c.replace('$','').replace(',','').replace('.','').replace('-','').isdigit() for c in row if c))
            has_enough_numbers=rows_with_numbers>=len(rows_data)*0.2 if rows_data else False
            if rows_data and len(rows_data)>=2 and has_enough_numbers:
                # 检查空单元格比例，如果超过40%则保留为pre格式
                total_cells=sum(len(r) for r in rows_data)
                empty_cells=sum(1 for r in rows_data for c in r if not c.strip())
                empty_ratio=empty_cells/max(total_cells,1)
                if empty_ratio > 0.4:
                    # 复杂表格：保留原始HTML格式
                    orig_html=str(tbl)
                    # 清理HTML
                    orig_html=re.sub(r'<font[^>]*>','',orig_html,flags=re.I)
                    orig_html=re.sub(r'</font>','',orig_html,flags=re.I)
                    orig_html=re.sub(r'<p[^>]*>','',orig_html,flags=re.I)
                    orig_html=re.sub(r'</p>','',orig_html,flags=re.I)
                    orig_html=re.sub(r'<center>','',orig_html,flags=re.I)
                    orig_html=re.sub(r'</center>','',orig_html,flags=re.I)
                    orig_html=re.sub(r'<b>','<b>',orig_html)
                    orig_html=re.sub(r'</b>','</b>',orig_html)
                    plain_text=' '.join(rows_data[0][:3])  # 取表头作为描述
                    blocks.append({'type':'pre_table','text':plain_text,'html':f'<div style="overflow-x:auto">{orig_html}</div>'})
                else:
                    th='<table>'
                    for i,row in enumerate(rows_data):
                        tag='th' if i==0 else 'td'
                        th+='<tr>'
                        for cell in row:
                            cell=(cell or "").strip()
                            if not cell: cell=''
                            th+=f'<{tag}>{html_mod.escape(cell)}</{tag}>'
                        th+='</tr>'
                    th+='</table>'
                    tt=" ".join([" ".join(r) for r in rows_data])
                    blocks.append({'type':'table','text':tt,'html':th,'table_data':rows_data})
        elif el_type=='element':
            el=el_obj
            # 跳过包含<table>的元素（避免与table处理重复）
            if el.find('table'):
                continue
            text=el.get_text(separator=' ',strip=True)
            if not text or len(text)<10: continue
            if is_separator(text): continue
            
            # 检查是否是See's Candy表格（表头在<I>标签内）
            is_sees_table = ('See' in text and 'Candy' in text and 'December 31' in text)
            if is_sees_table:
                full_text = el.get_text(separator='\n', strip=True)
                lines = full_text.split('\n')
                table_data = _parse_sees_candy_table(lines, full_text)
                if table_data:
                    th = table_to_html(table_data)
                    tt = ' '.join([' '.join(r) for r in table_data])
                    blocks.append({'type':'table','text':tt,'html':th,'table_data':table_data})
                    continue
            
            hs=''
            for ch in el.children:
                if isinstance(ch,NavigableString): hs+=str(ch).strip()+' '
                elif isinstance(ch,Tag):
                    if ch.name in('b','strong','i','em'):
                        inn=ch.get_text(strip=True)
                        if inn: hs+=f'<b>{inn}</b> '
                    else: hs+=ch.get_text(strip=True)+' '
            hs=' '.join(hs.split())
            if not hs or len(hs)<10: continue
            plain=re.sub(r'<[^>]+>','',hs)
            insurance_kws = ['Combined Ratio', 'Premium Written', 'Premium Earned', 'Policyholder Dividends']
            is_ins = any(kw in text for kw in insurance_kws)
            if is_ins and re.search(r'\d{4}', text):
                table_data = _parse_insurance_table(text.split('\n'), text)
                if table_data:
                    th = table_to_html(table_data)
                    tt = ' '.join([' '.join(r) for r in table_data])
                    blocks.append({'type':'table','text':tt,'html':th,'table_data':table_data})
                    continue
            if is_table_block(plain):
                table_data=parse_table_from_text(plain)
                if table_data:
                    th=table_to_html(table_data)
                    blocks.append({'type':'table','text':plain,'html':th,'table_data':table_data})
                    continue
            blocks.append({'type':'heading' if el.name in('h1','h2','h3','h4','h5','h6') else 'paragraph','text':text,'html':hs})
        elif el_type=='pre':
            pre=el_obj
            text=pre.get_text(separator='\n')
            if not text or len(text)<20: continue
            # 按空行分割段落
            paragraphs=re.split(r'\n\s*\n',text)
            # 预处理：合并表头段落和后续数据段落
            merged_paras = []
            skip_next = False
            for pi, para in enumerate(paragraphs):
                if skip_next:
                    skip_next = False
                    continue
                para = para.strip()
                if not para or len(para)<15: continue
                if is_separator(para): continue
                lines = para.split('\n')
                dot_lines = [l for l in lines if ' . ' in l or '....' in l or
                             (re.match(r'^\s*[\d,]+\s', l) and
                              (re.search(r'\$[\s\d,]+', l) or re.search(r'\.{3,}', l) or
                               re.search(r'\s{3,}\S', l) or len(re.findall(r'[\d,]+', l)) >= 3))]
                # 检查是否是表头段落（需要与下一个数据段落合并）
                is_header_para = False
                # See's Candy表格特殊处理：包含Candy/Stores Open + December 31
                # 必须在table_header_kws检测之前，因为See's表格包含"After Tax"
                is_sees_header = (
                    ('Candy' in para or 'pounds of' in para.lower() or 'Stores Open' in para) and
                    'December 31' in para and
                    len(lines) < 10
                )
                if is_sees_header:
                    # See's表格表头：直接与下一个数据段落合并并解析
                    if pi + 1 < len(paragraphs):
                        next_para = paragraphs[pi + 1].strip()
                        if next_para and re.search(r'\b(198\d|197\d)\s', next_para):
                            merged = para + '\n' + next_para
                            table_data = _parse_sees_candy_table(merged.split('\n'), merged)
                            if table_data:
                                th = table_to_html(table_data)
                                tt = ' '.join([' '.join(r) for r in table_data])
                                blocks.append({'type':'table','text':tt,'html':th,'table_data':table_data})
                                skip_next = True
                                continue
                # 持仓表头：包含Shares/Company/Cost/Market但没有足够数据行
                has_equity = any(kw in para for kw in ['Shares', 'Company', 'Cost', 'Market'])
                if has_equity and len(dot_lines) < 3:
                    is_header_para = True
                # 复杂表格表头：包含表格关键词（Net Earnings, Income Taxes等）且下一个段落是复杂表格
                # 排除See's表格（已单独处理）
                table_header_kws = ['Net Earnings', 'Earnings Before', 'Income Taxes', 'Berkshire Share']
                has_table_header = any(kw in para for kw in table_header_kws)
                if has_table_header and len(dot_lines) < 3 and not has_equity and not is_sees_header:
                    is_header_para = True
                # Insurance行业统计表头：包含Combined Ratio/Premium等关键词
                _ins_kws = ['Combined Ratio', 'Premium Written', 'Premium Earned', 'Policyholder Dividends']
                has_ins_header = any(kw in para for kw in _ins_kws)
                if has_ins_header and len(dot_lines) < 3:
                    # Insurance表头：与下一个数据段落合并，但不立即解析
                    # 让后面的统一处理循环来解析，以保持顺序
                    if pi + 1 < len(paragraphs):
                        next_para = paragraphs[pi + 1].strip()
                        if next_para and re.search(r'\d{4}', next_para):
                            merged = para + '\n' + next_para
                            merged_paras.append(merged)
                            skip_next = True
                            continue
                    # 如果没有下一个段落或解析失败，仍然标记为表头
                    is_header_para = True
                if is_header_para and pi + 1 < len(paragraphs):
                    next_para = paragraphs[pi + 1].strip()
                    next_lines = next_para.split('\n')
                    next_dot = [l for l in next_lines if ' . ' in l or '....' in l or
                                (re.match(r'^\s*[\d,]+\s', l) and
                                 (re.search(r'\$[\s\d,]+', l) or re.search(r'\.{3,}', l) or
                                  re.search(r'\s{3,}\S', l) or len(re.findall(r'[\d,]+', l)) >= 3))]
                    if len(next_dot) >= 3:
                        # 合并表头和数据段落
                        merged = para + '\n' + next_para
                        merged_paras.append(merged)
                        skip_next = True
                        continue
                merged_paras.append(para)
        
            for pi, para in enumerate(merged_paras):
                if skip_next:
                    skip_next = False
                    continue
                para=para.strip()
                if not para or len(para)<15: continue
                if is_separator(para): continue
                # 检测粗体和斜体（保留HTML标签）
                hs=para
                for b in pre.find_all('b'):
                    inn=b.get_text(strip=True)
                    # 跳过单个字母的粗体（避免<b>o</b>问题）
                    if inn and len(inn) > 1:
                        hs=hs.replace(inn,f'<b>{inn}</b>')
                    elif inn:
                        hs=hs.replace(inn,inn)  # 单个字母不加粗标签
                for i in pre.find_all('i'):
                    inn=i.get_text(strip=True)
                    if inn: hs=hs.replace(inn,f'<i>{inn}</i>')
                # 保留换行符用于表格检测（plain_with_nl），显示用空格合并（hs）
                plain_with_nl=re.sub(r'<[^>]+>','',hs)
                hs=' '.join(hs.split())
                plain=re.sub(r'<[^>]+>','',hs)
                # 优先检查持仓表格特征（在is_table_block之前）
                lines = para.split('\n')
                dot_lines = [l for l in lines if ' . ' in l or '...' in l or
                             (re.match(r'^\s*[\d,]+\s', l) and
                              (re.search(r'\$[\s\d,]+', l) or re.search(r'\.{3,}', l) or
                               re.search(r'\s{3,}\S', l) or len(re.findall(r'[\d,]+', l)) >= 3))]
                has_equity_header = any(kw in para for kw in ['Shares', 'Company', 'Cost', 'Market'])
                # 区分持仓表头（Shares Company Cost Market）和普通表头（Berkshire Share）
                # 持仓表头要求 "Shares" 和 "Company" 同时出现，或 "Cost" 和 "Market" 同时出现
                is_equity_table = ('Shares' in para and 'Company' in para) or ('Cost' in para and 'Market' in para)
            
                # 检查是否是复杂的缩进表格（如1978年Net Earnings表）
                # 特征：多行、有缩进层级（4+空格）、有跨行公司名、有点号引导
                # 必须在hs被合并成一行之前检查
                indented_lines = [l for l in lines if re.match(r'^\s{2,}', l) and re.search(r'\d', l)]
                deep_indented = [l for l in lines if re.match(r'^\s{4,}', l) and l.strip()]
                is_complex_table = (len(indented_lines) >= 3 and len(deep_indented) >= 2 
                                     and len(dot_lines) >= 3 and not is_equity_table)
                if is_complex_table:
                    # 复杂缩进表格，保留为pre格式，不翻译（保持原始格式）
                    pre_html = '<pre style="font-size:0.85em;overflow-x:auto;white-space:pre">' + html_mod.escape(para) + '</pre>'
                    plain_text = ' '.join(para.split())
                    blocks.append({'type':'pre_table','text':plain_text,'html':pre_html})
                    continue
            
                if is_equity_table and len(dot_lines) >= 2:
                    table_data = _parse_equity_table(lines)
                    if table_data:
                        th=table_to_html(table_data)
                        tt=' '.join([' '.join(r) for r in table_data])
                        blocks.append({'type':'table','text':tt,'html':th,'table_data':table_data})
                        continue
                # See's Candy表格检测（固定宽度格式）- 使用hs（包含HTML标签）检测
                # 注意：这个检测必须在is_equity_table之前，因为整个文档可能包含Shares/Cost等词
                # 检测条件：包含Candy/Stores Open + December 31（数据可能在后续段落）
                is_sees_header = (
                    ('Candy' in hs or 'pounds of' in hs.lower() or 'Stores Open' in hs) and
                    'December 31' in para and
                    len(lines) < 10  # 表头段落通常较短
                )
                if is_sees_header:
                    # 查找后续段落中的数据
                    if pi + 1 < len(merged_paras):
                        next_para = merged_paras[pi + 1].strip()
                        # 检查下一个段落是否包含年份数据（1984, 1983等）
                        if re.search(r'\b(198\d|197\d)\s', next_para):
                            merged = para + '\n' + next_para
                            table_data = _parse_sees_candy_table(merged.split('\n'), merged)
                            if table_data:
                                th = table_to_html(table_data)
                                tt = ' '.join([' '.join(r) for r in table_data])
                                blocks.append({'type':'table','text':tt,'html':th,'table_data':table_data})
                                # 跳过下一个段落（已合并）
                                skip_next = True
                                continue
            
                # Insurance行业统计表检测（Yearly Change in Premium, Combined Ratio等）
                is_insurance_table = (
                    ('Combined Ratio' in para or 
                     ('Premium' in para and ('Written' in para or 'Earned' in para)) or
                     'Policyholder' in para) and
                    len(dot_lines) >= 3
                )
                if is_insurance_table and not is_equity_table:
                    # 检查是否已有相同的Insurance表（避免与<I>标签路径重复）
                    already_has = any('Combined Ratio' in b.get('text', '') for b in blocks)
                    if already_has:
                        continue
                    table_data = _parse_insurance_table(lines, para)
                    if table_data:
                        th = table_to_html(table_data)
                        tt = ' '.join([' '.join(r) for r in table_data])
                        blocks.append({'type':'table','text':tt,'html':th,'table_data':table_data})
                        continue
                if is_table_block(plain):
                    table_data=parse_table_from_text(plain)
                    if table_data:
                        th=table_to_html(table_data)
                        blocks.append({'type':'table','text':plain,'html':th,'table_data':table_data})
                        continue
                # 尝试按行分割为表格（通用多行数据）
                # 使用收紧版dot_lines避免普通段落被误判
                if len(dot_lines) >= 3:
                    table_rows = _parse_pre_table(lines)
                    if len(table_rows) >= 3 and not all(len(row) == 1 for row in table_rows):
                        th=table_to_html(table_rows)
                        tt=' '.join([' '.join(r) for r in table_rows])
                        blocks.append({'type':'table','text':tt,'html':th,'table_data':table_rows})
                        continue
                elif len(lines) >= 3 and sum(1 for l in lines if re.search(r'\d', l)) >= 3:
                    # 额外检查：段落中是否有表格结构特征，避免纯文本被误判
                    has_table_structure = (
                        any(re.search(r'\$[\s\d,]+', l) for l in lines) or
                        any(re.search(r'\.{3,}', l) for l in lines) or
                        any(re.search(r'\s{3,}\S', l) for l in lines) or
                        sum(1 for l in lines if re.search(r'\d', l)) > len(lines) * 0.6
                    )
                    if has_table_structure:
                        table_rows = _parse_pre_table(lines)
                        if len(table_rows) >= 3 and not all(len(row) == 1 for row in table_rows):
                            th=table_to_html(table_rows)
                            tt=' '.join([' '.join(r) for r in table_rows])
                            blocks.append({'type':'table','text':tt,'html':th,'table_data':table_rows})
                            continue
                blocks.append({'type':'paragraph','text':plain,'html':hs})
    # 去重：只删除连续的重复段落（保留非连续的重复，如附录标题）
    unique_blocks = []
    prev_text = None
    for block in blocks:
        text = block.get('text', '').strip()
        # 只跳过与前一个段落完全相同的（连续重复）
        if text == prev_text:
            continue
        prev_text = text
        unique_blocks.append(block)
    return unique_blocks

def _parse_insurance_table(lines, full_text):
    """解析Insurance行业统计表（Yearly Change in Premium, Combined Ratio等）
    
    特征：
    - 多行表头（可能跨多行，如"Yearly Change in Premium Written (%)"）
    - 数据行以4位年份开头，后跟点号和数值
    - 列之间用点号或空格分隔
    
    注意：HTML源中表头可能在<I>标签内（多行被合并为一行），
    数据行在<I>标签外。full_text是合并后的完整文本。
    """
    import html as html_mod
    
    # Step 1: 从full_text中分离表头和数据
    # 表头关键词
    header_kws = ['Combined Ratio', 'Premium', 'Policyholder', 'Yearly Change',
                  'Incurred Losses', 'Inflation Rate', 'GNP Deflator', 'Float Cost']
    
    # 找到第一个年份行的位置
    first_year_match = re.search(r'(?:^|\s)(\d{4})\s', full_text)
    
    header_text = ''
    data_text = ''
    if first_year_match:
        header_text = full_text[:first_year_match.start()].strip()
        data_text = full_text[first_year_match.start():].strip()
    else:
        # 没有找到年份，尝试从分隔线分割
        sep_match = re.search(r'[-=]{5,}', full_text)
        if sep_match:
            header_text = full_text[:sep_match.start()].strip()
            data_text = full_text[sep_match.end():].strip()
        else:
            data_text = full_text
    
    # Step 2: 解析数据行
    data_lines = data_text.split('\n')
    # 也尝试按年份分割（如果数据在一行中）
    if len(data_lines) <= 2:
        # 数据可能在一行中，用年份作为分隔符
        data_lines = re.split(r'(?=\b\d{4}\s)', data_text)
    
    table_rows = []
    for dline in data_lines:
        stripped = dline.strip()
        if not stripped: continue
        # 跳过分隔线
        if re.match(r'^[-=]+$', stripped.replace(' ', '')): continue
        # 跳过表头文本
        if any(kw in stripped for kw in header_kws) and not re.match(r'^\d{4}', stripped):
            continue
        
        # 提取年份（支持1981 (Rev.) 和 1982 (Est.) 格式）
        year_match = re.match(r'^(\d{4})(?:\s*\([^)]+\))?', stripped)
        if not year_match:
            continue
        
        year = year_match.group(0).strip()  # 包含年份和可能的标记，如 "1981 (Rev.)"
        rest = stripped[year_match.end():]
        
        # 移除点号和多余空格
        rest = re.sub(r'\.{3,}', ' ', rest)
        rest = re.sub(r'\s+', ' ', rest).strip()
        
        # 提取数值（包括小数、百分号、括号负数）
        all_nums = []
        for m in re.finditer(r'[\d.]+%?|\([\d.]+\)', rest):
            all_nums.append(m.group())
        
        if all_nums:
            row = [year] + all_nums
            table_rows.append(row)
    
    if not table_rows:
        return None
    
    # Step 3: 确定列数
    max_cols = max(len(r) for r in table_rows)
    
    # Step 4: 解析表头
    header = ['Year']
    
    if header_text:
        # 尝试从表头文本中提取列名
        # 表头可能包含多行文本（被合并为一行），需要按位置或关键词分割
        
        # 方法1：按已知关键词提取列名
        # 常见列名模式：
        # "Yearly Change in Premium Written (%)" 
        # "Yearly Change in Premium Earned (%)"
        # "Combined Ratio after Policyholder Dividends"
        # "Yearly Change in Incurred Losses (%)"
        # "Inflation Rate Measured by GNP Deflator (%)"
        
        # 找到所有数值列（数据行中的列数 - 1 = 表头列数）
        num_data_cols = max_cols - 1  # 减去Year列
        
        # 尝试从header_text中提取有意义的列名
        # 按位置分割：找到连续的文本块
        # 先清理：移除分隔线
        clean_header = re.sub(r'[-=]{3,}', ' ', header_text)
        clean_header = re.sub(r'\s+', ' ', clean_header).strip()
        
        # 尝试按大写单词起始位置分割列名
        # 找到所有"列起始"位置（大写字母或数字后面跟空格的位置）
        # 简化方法：使用已知模式匹配
        
        col_names = _extract_insurance_col_names(clean_header, num_data_cols)
        if col_names:
            header = ['Year'] + col_names
        else:
            # 回退：使用默认列名
            header = ['Year'] + ['Col %d' % (i+1) for i in range(num_data_cols)]
    else:
        # 没有表头，使用默认列名
        num_data_cols = max_cols - 1
        header = ['Year'] + ['Col %d' % (i+1) for i in range(num_data_cols)]
    
    # 补齐数据行列数
    for row in table_rows:
        while len(row) < len(header):
            row.append('')
    
    return [header] + table_rows if len(table_rows) >= 2 else None


def _extract_insurance_col_names(header_text, num_cols):
    """从合并的表头文本中提取Insurance表的列名
    
    由于HTML源中多行表头被合并为一行，文本顺序可能打乱。
    使用关键词匹配而非位置匹配。
    """
    if num_cols <= 0:
        return None
    
    ht = header_text
    
    # 检测各列是否存在（基于关键词，不依赖顺序）
    cols = []
    
    # Yearly Change in Premium Written (%)
    # 支持跨行格式：Yearly Change + in Premiums + Written (%)
    has_yearly_change = bool(re.search(r'Yearly\s+Change', ht, re.I))
    has_premium = bool(re.search(r'Premium', ht, re.I))
    has_written = bool(re.search(r'Written', ht, re.I))
    if has_yearly_change and has_premium and has_written:
        cols.append('Yearly Change in Premium Written (%)')
    
    # Yearly Change in Premium Earned (%)
    has_earned = bool(re.search(r'Earned', ht, re.I))
    if has_yearly_change and has_premium and has_earned:
        cols.append('Yearly Change in Premium Earned (%)')
    
    # Combined Ratio after Policyholder Dividends
    has_combined = bool(re.search(r'Combined\s+Ratio', ht, re.I))
    has_policy = bool(re.search(r'Policy', ht, re.I))
    has_holder = bool(re.search(r'holder', ht, re.I))
    has_dividends = bool(re.search(r'Dividends', ht, re.I))
    if has_combined and has_policy and has_holder and has_dividends:
        cols.append('Combined Ratio after Policyholder Dividends')
    elif has_combined:
        cols.append('Combined Ratio')
    
    # Yearly Change in Incurred Losses (%)
    # 支持跨行格式：in Incurred + Losses (%)
    has_incurred = bool(re.search(r'Incurred', ht, re.I))
    has_losses = bool(re.search(r'Losses', ht, re.I))
    if has_yearly_change and has_incurred and has_losses:
        cols.append('Yearly Change in Incurred Losses (%)')
    
    # Inflation Rate Measured by GNP/GDP Deflator (%)
    if re.search(r'Inflation\s+Rate.*(?:GNP|GDP)\s+Deflator', ht, re.I):
        cols.append('Inflation Rate Measured by GNP Deflator (%)')
    elif re.search(r'Inflation\s+Rate', ht, re.I):
        cols.append('Inflation Rate')
    
    # Float Cost of Funds (%)
    if re.search(r'Float\s+Cost\s+of\s+Funds', ht, re.I):
        cols.append('Float Cost of Funds (%)')
    
    if len(cols) >= num_cols:
        return cols[:num_cols]
    elif len(cols) > 0:
        # 补齐
        while len(cols) < num_cols:
            cols.append('Col %d' % (len(cols) + 1))
        return cols
    
    # 回退：按位置分割
    phrases = re.findall(r'[A-Z][A-Za-z\s()%-]+', ht)
    if len(phrases) >= num_cols:
        return [p.strip() for p in phrases[:num_cols]]
    
    return None

def _parse_sees_candy_table(lines, full_text):
    """解析See's Candy业绩表格（固定宽度格式）
    
    特征：
    - 表头跨多行（Year/Ended About/Sales/Operating等）
    - 数据行用点号引导（1984 .............. $135,946,000...）
    - 可能有(53 weeks)标记
    - 列：Year, Sales Revenues, Operating Profits, Pounds of Candy, Stores Open
    
    返回: list of lists (table_data) 或 None
    """
    # 检查是否是See's表格（Candy/Stores Open + December 31）
    # 注意：'See'可能在上一段，所以不检查'See'
    if not (('Candy' in full_text or 'pounds' in full_text.lower() or 'Stores Open' in full_text) and
            'December 31' in full_text):
        return None
    
    # 找到See's表格的起始位置（包含"December 31"的行）
    table_start = -1
    table_end = -1
    for i, line in enumerate(lines):
        if 'December 31' in line and table_start == -1:
            # 向前查找表头开始（包含"Week Year"或"Sales"等）
            for j in range(max(0, i-3), i):
                if 'Week' in lines[j] or 'Sales' in lines[j] or 'Operating' in lines[j]:
                    table_start = j
                    break
            if table_start == -1:
                table_start = max(0, i-2)
        
        # 表格结束：遇到空行或新段落（不以年份开头）
        if table_start != -1 and i > table_start + 3:
            # 如果当前行不以年份开头，且下一行也不以年份开头，则表格结束
            if not re.match(r'^\d{4}\s', line.strip()):
                # 检查是否是最后一行数据（1972）
                if '1972' not in line:
                    table_end = i
                    break
    
    if table_start == -1:
        return None
    
    if table_end == -1:
        table_end = len(lines)
    
    # 提取表格相关的行
    table_lines = lines[table_start:table_end]
    
    # 清理并解析行
    clean_lines = []
    for line in table_lines:
        line = line.rstrip()
        if not line:
            continue
        # 跳过分隔线
        if re.match(r'^[-=]+$', line.replace(' ', '')):
            continue
        clean_lines.append(line)
    
    if len(clean_lines) < 5:
        return None
    
    # 找到表头行和数据行的分界
    header_lines = []
    data_lines = []
    
    for i, line in enumerate(clean_lines):
        # 数据行特征：以年份开头（如1984, 1983）
        if re.match(r'^\d{4}\s', line):
            data_lines = clean_lines[i:]
            header_lines = clean_lines[:i]
            break
    
    if not data_lines or len(header_lines) < 2:
        return None
    
    # 构建列标题
    headers = ['Year', 'Sales Revenues', 'Operating Profits After Taxes', 
               'Number of Pounds of Candy Sold', 'Number of Stores Open at Year End']
    
    table_data = [headers]
    
    # 解析数据行
    for line in data_lines:
        # 数据行格式：1984 .............. $135,946,000 $13,380,000 24,759,000 214
        # 或：1983 (53 weeks) ... $133,531,000 $13,699,000 24,651,000 207
        
        # 提取年份（可能包含53 weeks标记）
        year_match = re.match(r'^(\d{4}(?:\s*\(\s*53\s*weeks?\s*\))?)', line)
        if not year_match:
            continue
        
        year = year_match.group(1).strip()
        rest = line[len(year_match.group(0)):].strip()
        
        # 移除点号
        rest = re.sub(r'^\.+', '', rest).strip()
        
        # 按空格分割剩余部分
        parts = rest.split()
        
        # 应该有4个数值列
        if len(parts) >= 4:
            row = [year, parts[0], parts[1], parts[2], parts[3]]
            table_data.append(row)
    
    if len(table_data) >= 3:  # 表头 + 至少2行数据
        return table_data
    
    return None

def _parse_equity_table(lines):
    """解析持仓表格（No. of Shares, Company, Cost, Market格式）"""
    table_rows = []
    header_row = None
    unit_row = None
    
    # 第一遍：收集所有行，合并续行
    merged_lines = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if is_separator(line): continue
        # 检测表头行（支持多种格式：Shares/No. of Sh./Number of Shares等）
        is_header_line = (
            ('Shares' in line or 'Sh.' in line or 'Number' in line) and 
            ('Company' in line or 'Cost' in line or 'Market' in line)
        ) or ('No.' in line and 'Shares' in line)
        if is_header_line:
            merged_lines.append(('header', line))
            continue
        # 检测单位行
        if 'omitted' in line.lower() or (re.match(r'^\s*\(', line) and '000' in line):
            unit_row = line.strip()
            continue
        # 检测分隔线
        if re.match(r'^[-=]+$', line.replace(' ', '')):
            continue
        # 检测小计行（只有数字和逗号/美元符号，没有字母文本）
        stripped = line.replace(' ', '')
        if re.match(r'^[\$,\d]+$', stripped) and len(re.findall(r'[\d,]+', line)) >= 2:
            merged_lines.append(('subtotal', line))
            continue
        # 数据行：以数字开头，或包含点号
        starts_num = bool(re.match(r'^[\d,]+', line))
        has_dots = ' . ' in line or '...' in line
        has_dollar = '$' in line
        
        if starts_num or has_dots:
            # 检查是否是续行：以数字开头但不含$也不含点号
            # 续行特征：只有Shares数字和公司名，没有Cost/Market数字
            # 且上一行也是不完整的（没有$和点号），说明公司名跨行
            is_continuation = False
            if starts_num and not has_dots and not has_dollar and merged_lines and merged_lines[-1][0] == 'data':
                prev_line = merged_lines[-1][1]
                prev_has_dots = ' . ' in prev_line or '...' in prev_line
                prev_has_dollar = '$' in prev_line
                # 只有上一行也不完整（没有$和点号）时，当前行才是续行
                if not prev_has_dots and not prev_has_dollar:
                    nums_in_line = re.findall(r'[\d,]+', line)
                    text_after_first_num = re.sub(r'^[\d,]+\s+', '', line)
                    has_more_nums = bool(re.search(r'\d', text_after_first_num))
                    if len(nums_in_line) <= 1 and not has_more_nums:
                        # 如果当前行只有$数字（小计行），不作为续行
                        if re.match(r'^[\s\$,\d]+$', line.replace(' ', '')) and '$' in line:
                            is_continuation = False
                        else:
                            is_continuation = True
            
            if is_continuation:
                # 续行：合并到上一行
                prev_type, prev_line = merged_lines[-1]
                merged_lines[-1] = (prev_type, prev_line + ' ' + line)
            else:
                merged_lines.append(('data', line))
        elif merged_lines and merged_lines[-1][0] == 'data':
            # 以空格/字母开头的续行
            # 但如果是Total/Summary行（包含$或Total关键词），不合并
            is_summary = bool(re.search(r'Total|All\s+Other', line, re.I))
            has_values = '$' in line and re.search(r'\d', line)
            if is_summary or has_values:
                merged_lines.append(('data', line))
            else:
                prev_type, prev_line = merged_lines[-1]
                merged_lines[-1] = (prev_type, prev_line + ' ' + line)
    
    # 第二遍：解析每行
    for ltype, line in merged_lines:
        if ltype == 'header':
            if header_row is None:
                header_row = []
            parts = re.split(r'\s{2,}', line)
            parts = [p.strip() for p in parts if p.strip()]
            parts = [p for p in parts if not re.match(r'^[-=]+$', p)]
            header_row.extend(parts)
            continue

        if ltype == 'subtotal':
            # 小计行：提取Cost和Market值
            nums = re.findall(r'\$?\s*[\d,]+', line)
            if len(nums) >= 2:
                table_rows.append(['', '', nums[-2].strip(), nums[-1].strip()])
            continue
        
        # 解析数据行
        # 按点号分割（支持3个及以上点号）
        dot_parts = re.split(r' \. \. \.+ | \.{3,} ', line)
        dot_parts = [p.strip() for p in dot_parts if p.strip()]
        
        if len(dot_parts) >= 2:
            # 点号分隔的行
            first = dot_parts[0]
            # 尝试从第一部分提取 Shares 和 Company
            m = re.match(r'^([\d,]+)\s+(.+)', first)
            if m:
                shares = m.group(1)
                company = m.group(2).strip().rstrip(',').rstrip('.')
                # 后续部分包含 Cost 和 Market
                values = []
                for p in dot_parts[1:]:
                    nums = re.findall(r'\$?\s*[\d,]+', p)
                    values.extend([n.strip() for n in nums])
                # 检查是否是汇总行（All Other, Total等）
                if re.search(r'All\s+Other|Total\s+Common|Total\s+Equit', company, re.I):
                    # 汇总行：shares可能是小计数字，需要重新解析
                    # 从company中提取纯文本标签
                    label_match = re.search(r'([A-Za-z][\w\s]+)', company)
                    if label_match:
                        label = label_match.group(1).strip().rstrip('.')
                        # values already extracted from dot_parts
                        if len(values) >= 2:
                            table_rows.append([label, '', values[-2], values[-1]])
                        elif len(values) == 1:
                            table_rows.append([label, '', values[0], ''])
                        continue
                if len(values) >= 2:
                    table_rows.append([shares, company, values[-2], values[-1]])
                elif len(values) == 1:
                    table_rows.append([shares, company, values[0], ''])
                else:
                    table_rows.append([shares, company, '', ''])
            else:
                # 没有Shares数字，可能是Total行或续行
                company = first.strip().rstrip('.').rstrip(',')
                values = []
                for p in dot_parts[1:]:
                    nums = re.findall(r'\$?\s*[\d,]+', p)
                    values.extend([n.strip() for n in nums])
                if company.lower() in ('total', 'all other holdings', 'total equities'):
                    if len(values) >= 2:
                        table_rows.append([company, '', values[-2], values[-1]])
                    else:
                        table_rows.append([company] + values)
                elif values:
                    # 续行数据（如Common Stock），检查上一行是否有Shares
                    if table_rows:
                        last = table_rows[-1]
                        # 如果上一行的Company不完整（没有Cost/Market），合并
                        if len(last) >= 2 and not last[2]:
                            last[1] = last[1] + ' ' + company
                            if values:
                                last[2] = values[-2] if len(values) >= 2 else values[0]
                                last[3] = values[-1] if len(values) >= 2 else ''
                            continue
                    table_rows.append(['', company] + values[:3])
        else:
            # 非点号分隔的行
            # 尝试匹配 Total/Summary 行
            m = re.match(r'^([\w\s]+?)\s{2,}(\$?[\d,]+)\s+(\$?[\d,]+)', line)
            if m:
                label = m.group(1).strip()
                cost = m.group(2).strip()
                market = m.group(3).strip()
                table_rows.append([label, '', cost, market])
            elif re.match(r'^[\d,]+\s', line):
                # 以数字开头但没有点号：可能是 Shares + Company + Cost + Market
                # 或 Shares + Company（没有Cost/Market）
                nums = re.findall(r'[\d,]+', line)
                if len(nums) >= 3:
                    # Shares + Company + Cost + Market
                    m = re.match(r'^([\d,]+)\s+(.+)', line)
                    if m:
                        shares = m.group(1)
                        rest = m.group(2).strip()
                        # 从右边提取最后两个数字作为Cost和Market
                        last_two = nums[-2:]
                        # 找到最后两个数字在rest中的位置
                        cost, market = last_two
                        # Company是去掉最后两个数字后的文字
                        company = rest
                        for n in reversed(last_two):
                            idx = company.rfind(n)
                            if idx >= 0:
                                company = company[:idx].strip()
                        company = company.strip().rstrip('.').rstrip(',')
                        table_rows.append([shares, company, cost, market])
                else:
                    # 只有Shares + Company
                    m = re.match(r'^([\d,]+)\s+(.+)', line)
                    if m:
                        shares = m.group(1)
                        company = m.group(2).strip()
                        table_rows.append([shares, company, '', ''])
    
    if not table_rows:
        return None
    
    # 构建完整表格
    result = []
    if header_row:
        while len(header_row) < 4:
            header_row.append('')
        result.append(header_row[:4])
    if unit_row:
        result.append([unit_row, '', '', ''])
    result.extend(table_rows)

    # 如果表头没有"Company"列，添加它并调整数据行顺序
    if result and result[0]:
        header = result[0]
        has_company = any('Company' in str(h) for h in header)
        if not has_company:
            # 在表头最前面添加"Company"
            header.insert(0, 'Company')
            # 调整数据行：把公司名（当前在第2列）移到第1列
            for r in result[1:]:
                if len(r) >= 4:
                    # 当前格式：[shares, company, cost, market]
                    # 目标格式：[company, shares, cost, market]
                    r[0], r[1] = r[1], r[0]
                elif len(r) >= 3:
                    r[0], r[1] = r[1], r[0]

    # 确保所有行列数一致
    max_cols = max(len(r) for r in result) if result else 0
    for r in result:
        while len(r) < max_cols:
            r.append('')
    
    return result if len(result) >= 2 else None

def _parse_pre_table(lines):
    """通用<pre>表格解析"""
    table_rows = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if is_separator(line): continue
        # 跳过分隔线
        if re.match(r'^[-=]+$', line.replace(' ', '')):
            continue
        # 按点号分割
        if ' . ' in line or '...' in line:
            parts = re.split(r' \. \. \.+ | \.{3,} ', line)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 2:
                table_rows.append(parts)
        elif re.match(r'^[\w\s\-\(\)]+$', line) and len(line) < 80:
            table_rows.append([line])
    return table_rows

def _parse_financial_table(text):
    """解析财务报表类表格（BNSF/BHE Earnings, Balance Sheet, Earnings Statement等）
    
    特征：
    - 行标签后跟点号引导（....）
    - 数值列包含$符号和逗号分隔数字
    - 可能有多年份列（2016, 2015, 2014）
    - 可能有副标题/小计行
    
    返回: list of lists (table_data) 或 None
    """
    # 检查是否是财务表格
    # 特征：包含点号引导行 + $符号 + 多个数字
    dot_lines = re.findall(r'.*?\.{3,}.*', text)
    if len(dot_lines) < 3:
        return None
    
    # 检查是否有$符号
    if '$' not in text:
        return None
    
    # 检查是否有足够的数字
    nums = re.findall(r'\$[\s\d,]+|[\d,]+\.\d{0,2}\b|\([\d,]+\)', text)
    if len(nums) < 3:
        return None

    # 检查是否是After-Tax Earnings双面板格式
    # 特征：包含 "After-Tax Earnings" 和 "Operations" 和 "Gains"
    if 'After-Tax Earnings' in text or ('Operations' in text and 'Gains' in text and 'Capital' in text):
        return _parse_after_tax_earnings(text)
    
    # 按行分割
    lines = text.split('\n')
    if len(lines) == 1:
        # 单行文本，尝试按点号序列分割为多行
        # 每个点号序列前面可能有行标签
        segments = re.split(r'\.{3,}', text)
        lines = []
        for seg in segments:
            seg = seg.strip()
            if seg:
                lines.append(seg)
    
    # 分离表头和数据
    header_lines = []
    data_lines = []
    in_header = True
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # 表头行特征：不包含点号引导的数据，不以$或数字开头
        has_dots = bool(re.search(r'\.{3,}', stripped))
        starts_with_num = bool(re.match(r'^[\$\d\(\[]', stripped))
        
        if in_header:
            if has_dots and starts_with_num:
                in_header = False
                data_lines.append(stripped)
            elif has_dots and re.search(r'\d', stripped):
                in_header = False
                data_lines.append(stripped)
            else:
                header_lines.append(stripped)
        else:
            data_lines.append(stripped)
    
    if not data_lines:
        return None
    
    # 解析表头
    header = _parse_financial_header(header_lines, data_lines)
    
    # 解析数据行
    table_rows = [header]
    for dline in data_lines:
        row = _parse_financial_row(dline, len(header))
        if row:
            table_rows.append(row)
    
    return table_rows if len(table_rows) >= 3 else None


def _parse_multiline_header(header_lines, data_lines):
    """解析跨行对齐的表头（如Underwriting Results表格）
    
    格式示例：
        Underwriting Results       Corrected Figures
        as Reported to You         After One Year's
        Year   Experience          Experience
        ----   --------------------  -----------------
    
    每行按位置分割为多个列，然后垂直合并同一列的文本。
    """
    if len(header_lines) < 2:
        return None
    
    # 过滤掉分隔线（如 "----   ---..."）
    clean_lines = []
    for line in header_lines:
        stripped = line.strip()
        # 跳过分隔线
        if re.match(r'^[-=\s]+$', stripped):
            continue
        clean_lines.append(stripped)
    
    if len(clean_lines) < 2:
        return None
    
    # 尝试按列位置分割每行
    # 策略：找到每行中双空格（或多空格）的位置作为列分隔点
    all_splits = []
    for line in clean_lines:
        # 找到所有多空格（2个或以上）的位置
        splits = []
        for m in re.finditer(r'\s{2,}', line):
            splits.append(m.start())
        all_splits.append(splits)
    
    if not all_splits:
        return None
    
    # 找到共同的列分隔位置（取各行的交集附近）
    # 使用第一行的分隔位置作为基准
    ref_splits = all_splits[0]
    if not ref_splits:
        return None
    
    # 对每行按基准位置分割
    columns = [[] for _ in range(len(ref_splits) + 1)]
    for li, line in enumerate(clean_lines):
        splits = all_splits[li]
        # 使用该行自己的分隔位置
        if not splits:
            # 没有多空格分隔，整行作为第一列
            columns[0].append(line.strip())
            continue
        
        # 按该行的分隔位置分割
        parts = []
        prev_end = 0
        for sp in splits:
            parts.append(line[prev_end:sp].strip())
            prev_end = sp
        parts.append(line[prev_end:].strip())
        
        # 对齐到columns：如果该行的parts数和columns数不同，尝试合并
        if len(parts) == len(columns):
            for ci, part in enumerate(parts):
                if part:
                    columns[ci].append(part)
        elif len(parts) < len(columns):
            # 该行列数较少，可能是合并列
            for ci, part in enumerate(parts):
                if part:
                    columns[ci].append(part)
        else:
            # 该行列数较多，尝试映射
            for ci, part in enumerate(parts):
                if ci < len(columns) and part:
                    columns[ci].append(part)
    
    # 合并每列的文本
    header = []
    for col_parts in columns:
        combined = ' '.join(col_parts).strip()
        if combined:
            header.append(combined)
    
    if len(header) >= 2:
        return header
    return None


def _parse_financial_header(header_lines, data_lines):
    """从表头行中提取列名"""
    if not header_lines:
        # 没有表头，从数据行推断
        # 检查第一行数据来确定列数
        first_data = data_lines[0] if data_lines else ''
        nums = re.findall(r'\$?\s*[\d,]+(?:\.\d{0,2})?%?|\([\d,]+\)', first_data)
        return ['Item'] + ['Col %d' % (i+1) for i in range(len(nums))]

    # 检查是否是跨行表头格式（如Underwriting Results表格）
    # 特征：多行表头，每行有多个垂直对齐的列名
    if len(header_lines) >= 2:
        # 尝试按列位置对齐多行表头
        # 检测模式：每行中有多个用空格分隔的文本块，且各行的块数相同
        # 例如：
        #   "Underwriting Results       Corrected Figures"
        #   "as Reported to You         After One Year's"
        #   "Year   Experience          Experience"
        aligned_header = _parse_multiline_header(header_lines, data_lines)
        if aligned_header:
            return aligned_header

    # 合并所有表头行
    combined_header = ' '.join(header_lines)
    
    # 提取年份（如2016, 2015, 2014）
    years = re.findall(r'\b(20\d{2}|19\d{2})\b', combined_header)
    
    # 提取非年份、非数字的文本作为第一列名
    # 移除年份、数字、括号内容
    clean_header = re.sub(r'\b(20\d{2}|19\d{2})\b', '', combined_header)
    clean_header = re.sub(r'\(.*?\)', '', clean_header)
    clean_header = re.sub(r'[\d,]+\.?\d*%?', '', clean_header)
    clean_header = re.sub(r'\s+', ' ', clean_header).strip()
    
    # 检查是否是双面板布局（如Balance Sheet: Assets | Liabilities）
    # 特征：表头包含 "Assets" 和 "Liabilities" 或类似关键词
    is_balance_sheet = bool(re.search(r'Assets.*Liabilities|Liabilities.*Assets', combined_header, re.I))
    
    if is_balance_sheet:
        # Balance Sheet格式：第一列是项目名，第二列是数值
        return ['Item', 'Amount']
    
    if years:
        # 有年份列的表格
        # 第一列是项目名
        first_col = clean_header if clean_header else 'Item'
        # 年份作为列名
        year_cols = years
        return [first_col] + year_cols
    else:
        # 没有年份，检查是否有分类列名
        # 如 "Underwriting Profit" / "Yearend Float"
        parts = re.split(r'\s{2,}', combined_header)
        parts = [p.strip() for p in parts if p.strip() and not re.match(r'^[\d\(\)\$]+$', p)]
        if len(parts) >= 2:
            return parts
        return ['Item', 'Amount']


def _parse_financial_row(line, num_cols):
    """解析财务表格的数据行
    
    格式：Label ..... $value1 value2 value3
    或：Label ..... value1 value2 value3
    """
    # 分离标签和数值
    dot_match = re.search(r'\.{3,}', line)
    if dot_match:
        label = line[:dot_match.start()].strip()
        values_text = line[dot_match.end():].strip()
    else:
        # 没有点号，尝试按空格分割
        parts = line.split()
        if not parts:
            return None
        # 第一个非数字部分是标签
        label_parts = []
        value_parts = []
        in_label = True
        for p in parts:
            if in_label and not re.match(r'^[\$\d\(\[]', p):
                label_parts.append(p)
            else:
                in_label = False
                value_parts.append(p)
        label = ' '.join(label_parts)
        values_text = ' '.join(value_parts)
    
    if not label:
        return None
    
    # 提取数值
    values = re.findall(r'\$?\s*[\d,]+(?:\.\d{0,2})?%?|\([\d,]+\)', values_text)
    values = [v.strip() for v in values]
    
    if not values:
        return None
    
    row = [label] + values
    # 补齐列数
    while len(row) < num_cols:
        row.append('')
    
    return row


def _parse_after_tax_earnings(text):
    """解析After-Tax Earnings双面板表格
    
    格式：
    Capital Year Operations (1) Gains (2)    Year Operations (1) Gains (2)
    1999   0.67   0.89                     2008   9.64   (4.65)
    ...
    """
    # 移除脚注文本（以(1)或(2)开头的行）
    text = re.sub(r'\n\(\d\)\s+.*$', '', text, flags=re.DOTALL)
    # 移除表头文本
    text = re.sub(r'After-Tax Earnings.*?\n', '', text)
    text = re.sub(r'Year\s+Operations.*?\n', '', text)
    text = re.sub(r'Capital\s+Gains.*?\n', '', text)
    
    # 提取所有年份行：年份 + 2个数值（可能包含负数括号）
    # 使用非贪婪匹配，每个年份只匹配到下一个年份之前
    year_pattern = re.compile(r'(\d{4})\s+([\d.\s()]+?)(?=\d{4}\s|$)')
    matches = year_pattern.findall(text)
    
    if len(matches) < 4:
        return None
    
    header = ['Year', 'Operations (1)', 'Capital Gains (2)']
    rows = [header]
    for year, values_text in matches:
        values = re.findall(r'[\d.]+|\([\d.]+\)', values_text)
        if len(values) >= 2:
            row = [year, values[0], values[1]]
            rows.append(row)
        elif len(values) == 1:
            row = [year, values[0], '']
            rows.append(row)
    
    return rows if len(rows) >= 5 else None


def _merge_financial_tables(blocks):
    """后处理：合并财务表格的表头block和数据block

    扫描blocks，找到财务表格的表头block，然后合并后续的数据block，
    重新解析为正确的表格。
    """
    # 财务表头关键词模式
    fin_header_patterns = [
        # After-Tax Earnings
        (r'After-Tax Earnings', 'after_tax'),
        # Underwriting Profit / Float
        (r'Underwriting Profit.*Yearend Float', 'underwriting'),
        # BNSF Earnings（精确匹配表头格式）
        (r'^BNSF\s+Earnings\s+\(in millions\)', 'bnsf'),
        # Berkshire Hathaway Energy Earnings（精确匹配表头格式）
        (r'^Berkshire Hathaway Energy\s*\(.*?\)\s+Earnings\s+\(in millions\)', 'bhe'),
        # Balance Sheet（精确匹配，避免误匹配正文中提到的"balance sheet"）
        (r'^Balance Sheet\s', 'balance_sheet'),
        # Earnings Statement（精确匹配表头格式）
        (r'^Earnings Statement\s+\(in millions\)', 'earnings_stmt'),
        # Finance-related companies
        (r'finance-related companies', 'finance'),
    ]

    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b['type'] != 'paragraph':
            i += 1
            continue

        text = b['text']
        matched_type = None
        for pattern, table_type in fin_header_patterns:
            if re.search(pattern, text, re.I):
                matched_type = table_type
                break

        if not matched_type:
            i += 1
            continue

        # 找到匹配的表头block，开始合并后续block
        merged_text = text
        header_end = i
        data_start = i + 1

        # 收集后续的数据block
        j = i + 1
        while j < len(blocks):
            nb = blocks[j]
            nt = nb['text']
            ntype = nb['type']

            # 停止条件：遇到非数据block
            if ntype == 'heading':
                break
            # 停止条件：遇到另一个财务表头（不同类型）
            if ntype == 'paragraph':
                _other_header = False
                for _pat, _ttype in fin_header_patterns:
                    if _ttype != matched_type and re.search(_pat, nt, re.I):
                        _other_header = True
                        break
                if _other_header:
                    break
            if ntype == 'paragraph' and len(nt) > 100:
                # 长段落可能是正文，不是表格数据
                # 但检查是否包含表格数据特征
                # 对于特殊类型（after_tax等），放宽条件
                if matched_type == 'after_tax' and re.search(r'\d{4}\s+[\d.\s()]+', nt):
                    pass  # will be handled below
                elif not re.search(r'\.{3,}', nt) and not re.search(r'\$\s*[\d,]+', nt):
                    break
            # 对于所有财务表格类型，如果paragraph block包含表格数据特征（点号或$符号），继续合并
            if ntype == 'paragraph':
                if re.search(r'\.{3,}', nt) or re.search(r'\$\s*[\d,]+', nt):
                    merged_text += '\n' + nt
                    j += 1
                    continue
                elif re.match(r'^[\$\d\(\)\s,\.]+$', nt.strip()):
                    # 纯数字/符号行（如合计行）
                    merged_text += '\n' + nt
                    j += 1
                    continue
                elif matched_type == 'after_tax':
                    # After-Tax Earnings: 合并所有短block（表头行和数据行）
                    if len(nt) < 200:
                        merged_text += '\n' + nt
                        j += 1
                        continue
                    elif re.search(r'\d{4}\s+[\d.\s()]+', nt):
                        merged_text += '\n' + nt
                        j += 1
                        continue
                    else:
                        break
                elif matched_type == 'balance_sheet' and len(nt) < 200:
                    # Balance Sheet: 合并短block（如"Assets Liabilities and Equity"）
                    merged_text += '\n' + nt
                    j += 1
                    continue
                elif matched_type == 'finance' and len(nt) < 50:
                    # Finance: 合并短注释block（如"(in millions)"）
                    merged_text += '\n' + nt
                    j += 1
                    continue
                else:
                    break

            # 合并数据block
            if ntype in ('table', 'data', 'paragraph'):
                merged_text += '\n' + nt
                j += 1
            else:
                break

        # 尝试解析合并后的文本
        table_data = _parse_merged_financial(merged_text, matched_type)

        if table_data and len(table_data) >= 3:
            # 替换原始blocks
            th = table_to_html(table_data)
            tt = ' '.join([' '.join(r) for r in table_data])
            new_block = {'type':'table','text':tt,'html':th,'table_data':table_data}
            blocks[i:j] = [new_block]
            i = i + 1  # 跳过已合并的blocks
        else:
            i += 1

    return blocks


def _split_merged_rows(text):
    """将PDF提取中合并到单行的多行表格数据拆分为独立行

    PDF提取经常将多个表格行合并为一个block，例如：
    'Revenues.... $19,829 $21,967 Operating expenses.... 13,144 14,264'

    本函数通过检测 "标签+点号" 模式来拆分这些行。
    """
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Check if this line contains multiple dot-leader patterns
        # Pattern: text... (dots followed by value, then another label...)
        # We split before each "label..." pattern that follows a numeric value
        # The label must start with a letter (not $ or digit) and contain dots later
        parts = re.split(r'(?<=[\d\)])\s+(?=[A-Za-z\(].*?\.{3,})', stripped)
        if len(parts) > 1:
            for p in parts:
                p = p.strip()
                if p:
                    result.append(p)
        else:
            result.append(stripped)
    return result


def _parse_merged_financial(text, table_type):
    """根据表格类型分派到专用解析器"""
    if table_type == 'after_tax':
        return _parse_after_tax_earnings(text)
    elif table_type == 'underwriting':
        return _parse_underwriting_table(text)
    elif table_type in ('bnsf', 'bhe'):
        return _parse_earnings_waterfall(text)
    elif table_type == 'balance_sheet':
        return _parse_balance_sheet_table(text)
    elif table_type == 'earnings_stmt':
        return _parse_earnings_stmt_table(text)
    elif table_type == 'finance':
        return _parse_finance_table(text)
    return None


def _parse_underwriting_table(text):
    """解析Underwriting Profit / Yearend Float表

    格式：
    Underwriting Profit Yearend Float (in millions) Insurance Operations 2016 2015 2016 2015
    BH Reinsurance .... $ 822 $ 421 $ 45,081 $ 44,108
    ...
    """
    lines = _split_merged_rows(text)
    data_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        if re.search(r'\.{3,}', stripped) and re.search(r'\d', stripped):
            data_lines.append(stripped)
        elif re.match(r'^\$\s*[\d,]+', stripped):
            # Totals row
            data_lines.append(stripped)

    if len(data_lines) < 2:
        return None

    header = ['Insurance Operations', 'Underwriting Profit 2016', 'Underwriting Profit 2015',
              'Yearend Float 2016', 'Yearend Float 2015']
    rows = [header]

    for dline in data_lines:
        # Separate label from values
        dot_match = re.search(r'\.{3,}', dline)
        if dot_match:
            label = dline[:dot_match.start()].strip()
            rest = dline[dot_match.end():].strip()
        else:
            # Totals row: starts with $
            label = 'Total'
            rest = dline

        # Extract all numeric values (including $ prefixed)
        values = re.findall(r'\$?\s*([\d,]+)', rest)
        values = [v.strip() for v in values if v.strip()]

        if values and len(values) >= 4:
            row = [label] + values[:4]
            rows.append(row)
        elif values and label == 'Total':
            # Pad totals
            while len(values) < 4:
                values.append('')
            row = [label] + values[:4]
            rows.append(row)

    return rows if len(rows) >= 3 else None


def _parse_earnings_waterfall(text):
    """解析BNSF/BHE Earnings瀑布表

    格式：
    BNSF Earnings (in millions) 2016 2015 2014
    Revenues.... $ 19,829 $ 21,967 $ 23,239
    Operating expenses .... 13,144 14,264 16,237
    ...
    """
    lines = _split_merged_rows(text)

    # Extract years from header
    years = re.findall(r'\b(20\d{2})\b', text)
    if len(years) < 2:
        return None
    # Deduplicate preserving order
    seen = set()
    unique_years = []
    for y in years:
        if y not in seen:
            seen.add(y)
            unique_years.append(y)
    years = unique_years[:4]  # Max 4 year columns

    header = ['Item'] + years
    rows = [header]

    for line in lines:
        stripped = line.strip()
        if not stripped: continue

        # Skip header lines
        if re.match(r'^(BNSF|Berkshire)', stripped) and 'Earnings' in stripped:
            continue
        if re.match(r'^\(in millions\)', stripped):
            continue
        if re.match(r'^20\d{2}\s', stripped):
            continue

        # Data line: has dot leaders and numbers
        has_dots = bool(re.search(r'\.{3,}', stripped))
        has_nums = bool(re.search(r'\d', stripped))

        if not (has_dots and has_nums):
            continue

        # Separate label from values
        dot_match = re.search(r'\.{3,}', stripped)
        if dot_match:
            label = stripped[:dot_match.start()].strip()
            rest = stripped[dot_match.end():].strip()
        else:
            continue

        # Extract numeric values
        values = re.findall(r'\$?\s*([\d,]+(?:\.\d+)?)', rest)
        values = [v.strip() for v in values if v.strip()]

        if values and label:
            row = [label] + values
            # Pad or trim to match header
            while len(row) < len(header):
                row.append('')
            rows.append(row)

    return rows if len(rows) >= 3 else None


def _parse_earnings_stmt_table(text):
    """解析Earnings Statement表

    格式：
    Earnings Statement (in millions)
    2016 2015 2014
    Revenues.... $120,059 $107,825 $97,689
    ...
    """
    # Same format as earnings_waterfall, reuse
    return _parse_earnings_waterfall(text)


def _parse_balance_sheet_table(text):
    """解析Balance Sheet双栏表

    格式：
    Balance Sheet 12/31/16 (in millions)
    Assets Liabilities and Equity
    Cash and equivalents.... $ 8,073 Notes payable.... $ 2,054
    ...
    """
    lines = _split_merged_rows(text)
    rows = [['Item', 'Amount']]

    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        if 'Balance Sheet' in stripped: continue
        if 'Assets' in stripped and 'Liabilities' in stripped: continue

        # Split by $ to find value pairs
        # Each line may have: Label...$value Label2...$value2
        parts = re.split(r'(?=\$)', stripped)

        for part in parts:
            part = part.strip()
            if not part: continue

            # Extract value
            val_match = re.search(r'\$?\s*([\d,]+(?:\.\d+)?)', part)
            if not val_match: continue
            value = val_match.group(1)

            # Extract label (before the value)
            before = part[:val_match.start()].strip()
            if re.search(r'\.{3,}', before):
                dot_m = re.search(r'\.{3,}', before)
                label = before[:dot_m.start()].strip()
            else:
                label = before.strip()

            if label and value:
                rows.append([label, value])

    return rows if len(rows) >= 3 else None


def _parse_finance_table(text):
    """解析finance-related companies表

    格式：
    2016 2015 2014
    (in millions)
    Berkadia (our 50% share) .... $ 91 $ 74 $ 122
    Clayton .... 744 706 558
    ...
    """
    lines = _split_merged_rows(text)

    # Extract years
    years = re.findall(r'\b(20\d{2})\b', text)
    seen = set()
    unique_years = []
    for y in years:
        if y not in seen:
            seen.add(y)
            unique_years.append(y)
    years = unique_years[:4]

    if not years:
        return None

    header = ['Company'] + years
    rows = [header]

    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        if re.match(r'^\(in millions\)', stripped): continue
        if re.match(r'^20\d{2}\s', stripped): continue
        if re.match(r'^\*\s', stripped): continue  # footnote
        if re.match(r'^\$', stripped): continue  # totals row (handle separately)

        # Data line
        has_dots = bool(re.search(r'\.{3,}', stripped))
        has_nums = bool(re.search(r'\d', stripped))

        if not (has_dots and has_nums) and not has_dots:
            continue

        # Separate label from values
        dot_match = re.search(r'\.{3,}', stripped)
        if dot_match:
            label = stripped[:dot_match.start()].strip()
            rest = stripped[dot_match.end():].strip()
        else:
            continue

        # Extract numeric values
        values = re.findall(r'\$?\s*([\d,]+(?:\.\d+)?)', rest)
        values = [v.strip() for v in values if v.strip()]

        if values and label:
            row = [label] + values
            while len(row) < len(header):
                row.append('')
            rows.append(row)

    # Handle totals row
    for line in lines:
        stripped = line.strip()
        if re.match(r'^\$\s*[\d,]+', stripped):
            values = re.findall(r'\$?\s*([\d,]+)', stripped)
            values = [v.strip() for v in values if v.strip()]
            if len(values) >= 3:
                rows.append(['Total'] + values[:len(years)])

    return rows if len(rows) >= 3 else None


def extract_pdf_blocks(fp):
    """提取PDF文本块，检测表格、数据行、分隔符"""
    doc=fitz.open(fp); raw_blocks=[]
    for page in doc:
        for b in page.get_text('dict')['blocks']:
            if 'lines' not in b: continue
            parts=[]
            for line in b['lines']:
                for span in line['spans']:
                    t=span['text'].strip()
                    if not t: continue
                    if 'Bold' in span['font'] and 'BoldItalic' not in span['font'] and 'bold' in span['font'].lower():
                        if len(t) <= 1 and t.isalpha():
                            parts.append(t)  # 单个字母不加粗
                        else:
                            parts.append(f'<b>{t}</b>')
                    else: parts.append(t)
            ft=' '.join(parts); ft=re.sub(r'\s+',' ',ft).strip()
            if not ft or len(ft)<5: continue
            plain_text = re.sub(r'<[^>]+>','',ft)
            if is_separator(plain_text): continue
            raw_blocks.append({'text':plain_text,'html':ft,'page':page.number})
    doc.close()

    # 后处理：合并连续的年份+点号+数字行为Performance表格
    blocks = []
    i = 0
    while i < len(raw_blocks):
        rb = raw_blocks[i]
        text = rb['text']
        html = rb['html']

        # 分离 * * * 分隔符
        sub_blocks = split_separator(text, html)
        if len(sub_blocks) > 1:
            for sb in sub_blocks:
                if sb['type'] == 'separator':
                    blocks.append(sb)
                else:
                    st, sh = sb['text'], sb['html']
                    # 先检测Performance表格（避免被is_table_block拦截）
                    yl = re.findall(r'\b(19\d{2}|20\d{2})\s', st)
                    if len(yl) >= 10 and ('Compounded' in st or 'Overall' in st or 'S&P' in st):
                        # 简单的perf_table检测（单block情况）
                        perf_rows = []
                        co_rows = []
                        remaining = st
                        co_pattern = r'(Compounded Annual Gain.*?)(?=Overall Gain|$)'
                        co_matches = re.findall(co_pattern, remaining, re.DOTALL)
                        for co_text in co_matches:
                            remaining = remaining.replace(co_text, ' ')
                            dot_pos = co_text.find(' . ')
                            if dot_pos >= 0:
                                after = co_text[dot_pos:]
                                values = re.findall(r'\([\d,]+\)|[\d,]+\.[\d]+%?|[\d,]+%?', after)
                                values = [v for v in values if not re.match(r'^\.+$', v)]
                                label = co_text[:dot_pos].strip()
                                co_rows.append([label] + values + [''] * max(0, 2 - len(values)))
                        overall_match = re.search(r'(Overall Gain.*)', remaining)
                        if overall_match:
                            ot = overall_match.group(1)
                            remaining = remaining.replace(ot, ' ')
                            dot_pos = ot.find(' . ')
                            if dot_pos >= 0:
                                after = ot[dot_pos:]
                                values = re.findall(r'\([\d,]+\)|[\d,]+\.[\d]+%?|[\d,]+%?', after)
                                values = [v for v in values if not re.match(r'^\.+$', v)]
                                label = ot[:dot_pos].strip()
                                co_rows.append([label] + values + [''] * max(0, 2 - len(values)))
                        segments = re.split(r'(?=\b(?:19\d{2}|20\d{2})\s)', remaining)
                        for seg in segments:
                            seg = seg.strip()
                            if not seg: continue
                            m = re.match(r'^(\d{4})\s', seg)
                            if m:
                                year_str = m.group(1)
                                values = re.findall(r'\([\d,]+\.[\d]+%?\)|[\d,]+\.[\d]+%?|[\d,]+%?', seg)
                                values = [v for v in values if not re.match(r'^\.+$', v) and not re.match(r'^\d{4}$', v)]
                                if len(values) >= 2:
                                    perf_rows.append([year_str] + values[:4])
                                elif len(values) == 1:
                                    perf_rows.append([year_str, values[0], ''])
                        perf_rows.extend(co_rows)
                        if len(perf_rows) >= 5:
                            perf_headers = _detect_perf_headers(raw_blocks, i)
                            col_names = _extract_col_names(perf_headers)
                            first_data = perf_rows[0] if perf_rows else []
                            num_vals = len(first_data) - 1
                            if not col_names:
                                col_names = _default_col_names(num_vals)
                            elif len(col_names) < num_vals:
                                col_names = _default_col_names(num_vals)
                            header = ['Year'] + col_names
                            for row in perf_rows:
                                while len(row) < len(header):
                                    row.append('')
                            table_data = [header] + perf_rows
                            th = table_to_html(table_data)
                            tt = ' '.join([' '.join(r) for r in table_data])
                            blocks.append({'type':'perf_table','text':tt,'html':th,'table_data':table_data})
                            _remove_perf_header_blocks(blocks)
                            continue
                    # 财务表格检测（BNSF/BHE Earnings, Balance Sheet, Underwriting等）
                    fin_td = _parse_financial_table(st)
                    if fin_td:
                        th = table_to_html(fin_td)
                        tt = ' '.join([' '.join(r) for r in fin_td])
                        blocks.append({'type':'table','text':tt,'html':th,'table_data':fin_td})
                    elif is_data_row(st):
                        blocks.append({'type':'data','text':st,'html':sh})
                    elif is_table_block(st):
                        td = parse_table_from_text(st)
                        if td:
                            blocks.append({'type':'table','text':st,'html':table_to_html(td),'table_data':td})
                        else:
                            blocks.append(_make_para(st, sh))
                    else:
                        blocks.append(_make_para(st, sh))
            i += 1
            continue

        # 检测大block中的Performance表格（整个表格在一个block中，如2022/2023年PDF，或2008-2013年PDF）
        year_lines = re.findall(r'\b(19\d{2}|20\d{2})\s', text)
        # 条件1：当前block包含Compounded/Overall/S&P（如2022/2023）
        # 条件2：当前block有10+年份且下一个block包含Compounded/Overall（如2008-2013）
        next_has_co = False
        if i + 1 < len(raw_blocks):
            next_text = raw_blocks[i + 1]['text']
            next_has_co = 'Compounded' in next_text or 'Overall' in next_text
        if len(year_lines) >= 10 and ('Compounded' in text or 'Overall' in text or 'S&P' in text or next_has_co):
                # DEBUG
                import sys as _sys
                perf_rows = []
                co_rows = []  # 暂存Compounded/Overall行
                # 收集Compounded/Overall文本（可能在当前block或下一个block）
                co_text_source = text
                if next_has_co and 'Compounded' not in text:
                    co_text_source = text + ' ' + raw_blocks[i + 1]['text']
                remaining = co_text_source
                co_pattern = r'(Compounded Annual Gain.*?)(?=Overall Gain|$)'
                co_matches = re.findall(co_pattern, remaining, re.DOTALL)
                for co_text in co_matches:
                    remaining = remaining.replace(co_text, ' ')
                    dot_pos = co_text.find(' . ')
                    if dot_pos >= 0:
                        after = co_text[dot_pos:]
                        values = re.findall(r'\([\d,]+\)|[\d,]+\.[\d]+%?|[\d,]+%?', after)
                        values = [v for v in values if not re.match(r'^\.+$', v)]
                        label = co_text[:dot_pos].strip()
                        co_rows.append([label] + values + [''] * max(0, 2 - len(values)))
                overall_match = re.search(r'(Overall Gain.*)', remaining)
                if overall_match:
                    ot = overall_match.group(1)
                    remaining = remaining.replace(ot, ' ')
                    dot_pos = ot.find(' . ')
                    if dot_pos >= 0:
                        after = ot[dot_pos:]
                        values = re.findall(r'\([\d,]+\)|[\d,]+\.[\d]+%?|[\d,]+%?', after)
                        values = [v for v in values if not re.match(r'^\.+$', v)]
                        label = ot[:dot_pos].strip()
                        co_rows.append([label] + values + [''] * max(0, 2 - len(values)))
                # 对剩余文本按年份分割
                segments = re.split(r'(?=\b(?:19\d{2}|20\d{2})\s)', remaining)
                for seg in segments:
                    seg = seg.strip()
                    if not seg: continue
                    m = re.match(r'^(\d{4})\s', seg)
                    if m:
                        year_str = m.group(1)
                        values = re.findall(r'\([\d,]+\.[\d]+%?\)|[\d,]+\.[\d]+%?|[\d,]+%?', seg)
                        values = [v for v in values if not re.match(r'^\.+$', v) and not re.match(r'^\d{4}$', v)]
                        if len(values) >= 2:
                            perf_rows.append([year_str] + values[:4])
                        elif len(values) == 1:
                            perf_rows.append([year_str, values[0], ''])
                # 将Compounded/Overall行添加到末尾
                perf_rows.extend(co_rows)
                if len(perf_rows) >= 5:
                    perf_headers = _detect_perf_headers(raw_blocks, i)
                    col_names = _extract_col_names(perf_headers)
                    # 确定实际数据列数
                    first_data = perf_rows[0] if perf_rows else []
                    num_vals = len(first_data) - 1  # 减去Year列
                    if not col_names:
                        col_names = _default_col_names(num_vals)
                    elif len(col_names) < num_vals:
                        # 表头识别不完整，用默认列名补全
                        col_names = _default_col_names(num_vals)
                    header = ['Year'] + col_names
                    for row in perf_rows:
                        while len(row) < len(header):
                            row.append('')
                    table_data = [header] + perf_rows
                    th = table_to_html(table_data)
                    tt = ' '.join([' '.join(r) for r in table_data])
                    blocks.append({'type':'perf_table','text':tt,'html':th,'table_data':table_data})
                    _remove_perf_header_blocks(blocks)
                    # 如果Compounded/Overall在下一个block中，跳过它
                    i += 2 if next_has_co else 1
                    continue

        # 检测4行/年份格式的Performance表格（2008-2013年PDF）
        # 特征：一个block包含大量年份行（每行只有年份+点号），后续block包含数值
        if re.match(r'^\d{4}\s', text) and re.search(r'\.{5,}', text) and not re.search(r'\$[\d,]', text):
            # 检查是否是年份行block（只有年份和点号，没有数字值）
            year_only_lines = re.findall(r'^(\d{4})\s', text, re.MULTILINE)
            if len(year_only_lines) >= 10:
                # 这是年份行block，检查后续block是否是数值行
                perf_rows = []
                year_list = year_only_lines
                # 检查后续block：可能有Relative Results行 + 数值行
                val_block_idx = i + 1
                # 跳过Relative Results等表头行
                while val_block_idx < len(raw_blocks):
                    vbt = raw_blocks[val_block_idx]['text']
                    if re.match(r'^(Relative|To Date|\()', vbt, re.I):
                        val_block_idx += 1
                        continue
                    break
                # 收集数值block
                if val_block_idx < len(raw_blocks):
                    val_text = raw_blocks[val_block_idx]['text']
                    # 数值行应该是纯数字（可能带括号负数）
                    val_lines = val_text.strip().split('\n')
                    val_lines = [l.strip() for l in val_lines if l.strip()]
                    # 每个年份对应若干数值行
                    if len(val_lines) >= len(year_list):
                        # 确定每个年份对应几行数值
                        # 先检查是否有3列（Book Value, S&P, Relative Results）
                        # 通过检查后续是否有Compounded/Overall来判断
                        has_compounded = False
                        for ci in range(val_block_idx + 1, min(val_block_idx + 5, len(raw_blocks))):
                            ct = raw_blocks[ci]['text']
                            if 'Compounded' in ct or 'Overall' in ct:
                                has_compounded = True
                                break
                        # 尝试2列和3列
                        num_cols_per_year = 2  # 默认2列
                        if has_compounded:
                            # 检查数值行数量是否能被年份*3整除
                            if len(val_lines) >= len(year_list) * 3:
                                num_cols_per_year = 3
                        # 解析
                        for yi, year_str in enumerate(year_list):
                            start_idx = yi * num_cols_per_year
                            end_idx = start_idx + num_cols_per_year
                            if end_idx <= len(val_lines):
                                vals = []
                                for vi in range(start_idx, end_idx):
                                    v = val_lines[vi].strip()
                                    if v:
                                        vals.append(v)
                                perf_rows.append([year_str] + vals)
                        # 处理Compounded/Overall
                        co_idx = val_block_idx + 1
                        while co_idx < len(raw_blocks):
                            cot = raw_blocks[co_idx]['text']
                            if 'Compounded' in cot:
                                # Compounded行通常跨多个block
                                co_label = 'Compounded Annual Gain'
                                co_vals = []
                                # 收集Compounded相关的数值
                                for cci in range(co_idx, min(co_idx + 3, len(raw_blocks))):
                                    cct = raw_blocks[cci]['text']
                                    if 'Overall' in cct:
                                        break
                                    nums = re.findall(r'[\d,]+\.[\d]+%?|\([\d,]+\.[\d]+%?\)', cct)
                                    co_vals.extend(nums)
                                if co_vals:
                                    perf_rows.append([co_label] + co_vals[:num_cols_per_year] + [''] * max(0, num_cols_per_year - len(co_vals)))
                                co_idx += 1
                                break
                            elif 'Overall' in cot:
                                break
                            co_idx += 1
                        # Overall Gain
                        for oi in range(co_idx, min(co_idx + 5, len(raw_blocks))):
                            ot = raw_blocks[oi]['text']
                            if 'Overall' in ot:
                                o_label = 'Overall Gain'
                                o_vals = []
                                for ooi in range(oi, min(oi + 3, len(raw_blocks))):
                                    oot = raw_blocks[ooi]['text']
                                    if 'Compounded' in oot:
                                        break
                                    nums = re.findall(r'[\d,]+\.[\d]+%?|\([\d,]+\.[\d]+%?\)', oot)
                                    o_vals.extend(nums)
                                if o_vals:
                                    perf_rows.append([o_label] + o_vals[:num_cols_per_year] + [''] * max(0, num_cols_per_year - len(o_vals)))
                                break
                        if len(perf_rows) >= 5:
                            perf_headers = _detect_perf_headers(raw_blocks, i)
                            col_names = _extract_col_names(perf_headers)
                            if not col_names:
                                col_names = _default_col_names(num_cols_per_year)
                            elif len(col_names) < num_cols_per_year:
                                col_names = _default_col_names(num_cols_per_year)
                            header = ['Year'] + col_names
                            for row in perf_rows:
                                while len(row) < len(header):
                                    row.append('')
                            table_data = [header] + perf_rows
                            th = table_to_html(table_data)
                            tt = ' '.join([' '.join(r) for r in table_data])
                            blocks.append({'type':'perf_table','text':tt,'html':th,'table_data':table_data})
                            _remove_perf_header_blocks(blocks)
                            i = val_block_idx + 1
                            continue

        # 检测Performance表格：连续的年份+点号+数字行
        if re.match(r'^\d{4}\s', text) and is_data_row(text):
            perf_rows = []
            j = i
            while j < len(raw_blocks):
                rt = raw_blocks[j]['text']
                if re.match(r'^\d{4}\s', rt) and is_data_row(rt):
                    year_str = rt[:4]
                    values = re.findall(r'\([\d,]+\.[\d]+%?\)|[\d,]+\.[\d]+%?|[\d,]+%?', rt)
                    values = [v for v in values if not re.match(r'^\.+$', v) and not re.match(r'^\d{4}$', v)]
                    if len(values) >= 2:
                        perf_rows.append([year_str] + values[:4])
                    elif len(values) == 1:
                        perf_rows.append([year_str, values[0], ''])
                    else:
                        perf_rows.append([year_str, '', ''])
                    j += 1
                elif re.match(r'^(Year|Total|Cumulative)', rt, re.I):
                    dot_pos = rt.find(' . ')
                    if dot_pos >= 0:
                        after_dots = rt[dot_pos:]
                        values = re.findall(r'\([\d,]+\)|[\d,]+\.[\d]+%?|[\d,]+%?', after_dots)
                        values = [v for v in values if not re.match(r'^\.+$', v)]
                        label = rt[:dot_pos].strip()
                        perf_rows.append([label] + values + [''] * (2 - len(values)))
                    j += 1
                else:
                    break
            for k in range(j, min(j+3, len(raw_blocks))):
                kt = raw_blocks[k]['text']
                if re.match(r'^(Compounded|Overall)', kt, re.I):
                    dot_pos = kt.find(' . ')
                    if dot_pos >= 0:
                        after = kt[dot_pos:]
                        values = re.findall(r'\([\d,]+\)|[\d,]+\.[\d]+%?|[\d,]+%?', after)
                        values = [v for v in values if not re.match(r'^\.+$', v)]
                        label = kt[:dot_pos].strip()
                        perf_rows.append([label] + values + [''] * max(0, 2 - len(values)))
                    j = k + 1
                else:
                    break
            if len(perf_rows) >= 3:
                perf_headers = _detect_perf_headers(raw_blocks, i)
                col_names = _extract_col_names(perf_headers)
                first_data = perf_rows[0] if perf_rows else []
                num_vals = len(first_data) - 1
                if not col_names:
                    col_names = _default_col_names(num_vals)
                elif len(col_names) < num_vals:
                    col_names = _default_col_names(num_vals)
                header = ['Year'] + col_names
                for row in perf_rows:
                    while len(row) < len(header):
                        row.append('')
                table_data = [header] + perf_rows
                th = table_to_html(table_data)
                tt = ' '.join([' '.join(r) for r in table_data])
                blocks.append({'type':'perf_table','text':tt,'html':th,'table_data':table_data})
                _remove_perf_header_blocks(blocks)
                i = j
                continue
            blocks.append({'type':'data','text':text,'html':html})
            i += 1
            continue

        # 表头+表格数据合并：当当前block是表头行，后续block是表格数据时合并
        header_kws = ['Shares', 'Company', 'Percentage', 'Cost', 'Market', 'No. of']
        is_header = any(kw in text for kw in header_kws) and not re.search(r'\.{3,}', text)
        is_date = bool(re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', text))
        if (is_header or is_date):
            # 向后查找表格数据block（最多看5个block）
            data_idx = None
            for look in range(1, min(6, len(raw_blocks) - i)):
                lt = raw_blocks[i + look]['text']
                if is_table_block(lt) or (re.search(r'\.{5,}', lt) and len(re.findall(r'\d{1,3}(?:,\d{3})+', lt)) >= 3):
                    # 排除Performance表格（包含大量年份）
                    lt_year_count = len(re.findall(r'\b(19\d{2}|20\d{2})\s', lt))
                    if lt_year_count >= 10:
                        break  # 这是Performance表格，不要合并
                    data_idx = i + look
                    break
                # 如果遇到普通段落（不是表头/日期/单位），停止
                lt_is_header = any(kw in lt for kw in header_kws) and not re.search(r'\.{3,}', lt)
                lt_is_date = bool(re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', lt))
                lt_is_unit = bool(re.search(r'\(.*millions?\)', lt, re.I))
                if not (lt_is_header or lt_is_date or lt_is_unit):
                    break
            if data_idx is not None:
                # 收集连续的表头行（从当前到数据block之前）
                header_parts = []
                for hi in range(i, data_idx):
                    ht = raw_blocks[hi]['text']
                    header_parts.append(ht)
                # 也向前回溯
                hi = i - 1
                while hi >= 0:
                    ht = raw_blocks[hi]['text']
                    h_is_header = any(kw in ht for kw in header_kws) and not re.search(r'\.{3,}', ht)
                    h_is_date = bool(re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', ht))
                    h_is_unit = bool(re.search(r'\(.*in\s+\$.*\)', ht) or re.search(r'\(.*millions?\)', ht, re.I))
                    if h_is_header or h_is_date or h_is_unit:
                        header_parts.insert(0, ht)
                        hi -= 1
                    else:
                        break
                # 合并表头+数据
                data_text = raw_blocks[data_idx]['text']
                data_html = raw_blocks[data_idx]['html']
                merged_text = ' '.join(header_parts) + ' ' + data_text
                merged_html = ' '.join(header_parts) + ' ' + data_html
                # 检查数据block后面是否有Total/Summary行（如 "Total Equity Investments Carried at Market"）
                skip_end = data_idx + 1
                if skip_end < len(raw_blocks):
                    next_after = raw_blocks[skip_end]['text']
                    if re.search(r'Total\s+\w+.*Market|Total\s+Equity|Total\s+Investment', next_after) and re.search(r'\.\s*\.', next_after):
                        merged_text += ' ' + next_after
                        merged_html += ' ' + next_after
                        skip_end += 1
                td = parse_table_from_text(merged_text)
                if td and len(td) >= 3:
                    blocks.append({'type':'table','text':merged_text,'html':table_to_html(td),'table_data':td})
                    i = skip_end  # 跳过所有表头行、数据行和Total行
                    continue

        # 列对齐表格检测（如Yearend Ownership表：表头+数据在相邻block中，无点号引导）
        # 特征：当前block包含列名关键词，下一个block包含$和多个数字或%和数字
        # 排除Performance表格（包含大量年份）
        year_count = len(re.findall(r'\b(19\d{2}|20\d{2})\s', text))
        if year_count < 5:
            col_align_kws = ['Dividends', 'Retained', 'Earnings', 'Ownership', 'Yearend',
                              'Berkshire\'s Share', 'Percentage', 'Investments']
            # 允许"$"出现在"$ millions"上下文中
            has_kw = any(kw in text for kw in col_align_kws)
            dollar_in_context = '$' in text and re.search(r'\$\s*millions?', text, re.I)
            is_col_header = has_kw and (not '$' in text or dollar_in_context) and not re.search(r'\.{3,}', text)
            # 通用列对齐检测：当前block是短文本+包含多个大写单词（列名特征），下一个block有大量数字
            # 排除Performance表头（包含Annual Percentage Change等）
            perf_kws = ['Annual Percentage Change', 'Compounded Annual', 'Overall Gain', 'S&P 500']
            is_perf_header = any(kw in text for kw in perf_kws)
            # 排除Performance表头：如果is_perf_header为True，不设置is_col_header
            if is_perf_header:
                is_col_header = False
            # 排除：下一个block包含大量年份（Performance数据特征）
            next_year_count = 0
            if i + 1 < len(raw_blocks):
                next_year_count = len(re.findall(r'\b(19\d{2}|20\d{2})\s', raw_blocks[i + 1]['text']))
            if not is_col_header and not is_perf_header and next_year_count < 10 and len(text) < 80 and '$' not in text and not re.search(r'\.{3,}', text):
                # 检查是否像列名行：多个大写开头的单词，没有句号
                words = text.split()
                cap_words = [w for w in words if w[0].isupper() and len(w) > 2]
                has_period = text.rstrip().endswith('.')
                if len(cap_words) >= 2 and not has_period and len(text) < 50:
                    is_col_header = True
            if is_col_header and i + 1 < len(raw_blocks):
                next_text = raw_blocks[i + 1]['text']
                next_dollar_count = next_text.count('$')
                next_num_count = len(re.findall(r'[\$]?\s*[\d,]+(?:\.\d+)?%?', next_text))
                # 条件：至少2个$符号，或者至少5个数字（含%）
                is_data_block = (next_dollar_count >= 2 and next_num_count >= 4) or (next_num_count >= 8)
                if is_data_block:
                    # 合并表头+数据
                    merged_text = text + ' ' + next_text
                    # 检查是否还有Total行
                    skip_end = i + 2
                    if skip_end < len(raw_blocks):
                        after_text = raw_blocks[skip_end]['text']
                        if re.search(r'^Total', after_text) and '$' in after_text:
                            merged_text += ' ' + after_text
                            skip_end += 1
                    # 列对齐格式专用解析
                    td = _parse_col_aligned_table(text, next_text, raw_blocks[skip_end-1]['text'] if skip_end > i + 2 else None)
                    if td and len(td) >= 3:
                        blocks.append({'type':'table','text':merged_text,'html':table_to_html(td),'table_data':td})
                        i = skip_end
                        continue

        # Scorecard表格特殊检测（如2017年 "Here's the final scorecard for the bet:" 后面跟基金名称）
        if 'scorecard' in text.lower() and i + 1 < len(raw_blocks):
            sc_headers = []
            sc_end = i + 1
            while sc_end < len(raw_blocks):
                vt = raw_blocks[sc_end]['text']
                if len(vt) < 50 and not re.search(r'\.{3,}', vt) and not re.match(r'^\d{4}\s', vt):
                    sc_headers.append(vt)
                    sc_end += 1
                else:
                    break
            if len(sc_headers) >= 4 and sc_end < len(raw_blocks):
                data_block = raw_blocks[sc_end]['text']
                pct_count = len(re.findall(r'[\-]?\d+\.?\d*%', data_block))
                if pct_count >= 6:
                    # Add "Year" as first header if not present
                    all_headers = ['Year'] + sc_headers
                    merged = text + ' ' + ' '.join(sc_headers) + ' ' + data_block
                    skip_end = sc_end + 1
                    if skip_end < len(raw_blocks):
                        na = raw_blocks[skip_end]['text']
                        if re.search(r'Final\s+Gain|Average\s+Annual', na):
                            merged += ' ' + na
                            skip_end += 1
                    td = _parse_vertical_header_table(all_headers, data_block,
                                                       raw_blocks[skip_end-1]['text'] if skip_end > sc_end + 1 else None)
                    if td and len(td) >= 3:
                        blocks.append({'type':'table','text':merged,'html':table_to_html(td),'table_data':td})
                        i = skip_end
                        continue

        # 垂直表头表格检测（如2017年scorecard表：Year/Fund-of-Funds A/B/C/D/E/S&P各占一个block，后面跟数据block）
        # 特征：当前block和后续连续block都是短文本（<40字符），后面跟着一个包含大量%或数字的大block
        # 排除Performance表头（Annual Percentage Change, Year, in Per-Share...）
        _vperf_kws = ['Annual Percentage', 'Per-Share', 'Compounded Annual', 'Overall Gain']
        _is_vperf = any(kw in text for kw in _vperf_kws)
        if len(text) < 40 and not re.search(r'\.{3,}', text) and not _is_vperf:
            # 收集连续的短block作为表头
            vheader_blocks = [text]
            vheader_end = i + 1
            while vheader_end < len(raw_blocks):
                vt = raw_blocks[vheader_end]['text']
                _vt_is_perf = any(kw in vt for kw in _vperf_kws)
                if len(vt) < 40 and not re.search(r'\.{3,}', vt) and not re.match(r'^\d{4}\s', vt) and not _vt_is_perf:
                    vheader_blocks.append(vt)
                    vheader_end += 1
                else:
                    break
            # 检查后面的数据block是否包含大量%或数字（表格特征）
            if vheader_end < len(raw_blocks) and len(vheader_blocks) >= 3:
                data_block = raw_blocks[vheader_end]['text']
                # 排除Performance数据block（包含大量年份如1965-2023）
                data_year_count = len(re.findall(r'\b(19\d{2}|20\d{2})\s', data_block))
                if data_year_count >= 10:
                    pass  # 这是Performance数据，不触发垂直表头检测
                else:
                    pct_count = len(re.findall(r'[\-]?\d+\.?\d*%', data_block))
                    num_count = len(re.findall(r'[\$]?\s*[\d,]+(?:\.\d+)?', data_block))
                    is_table_data = pct_count >= 6 or (num_count >= 10 and pct_count >= 3)
                    if is_table_data:
                        # 合并表头+数据
                        header_line = ' | '.join(vheader_blocks)
                        merged_text = header_line + ' ' + data_block
                        # 检查后面是否有Final Gain/Average等汇总行
                        skip_end = vheader_end + 1
                        if skip_end < len(raw_blocks):
                            next_after = raw_blocks[skip_end]['text']
                            if re.search(r'Final\s+Gain|Average\s+Annual|Total\s+\$', next_after):
                                merged_text += ' ' + next_after
                                skip_end += 1
                        # 解析垂直表头表格
                        td = _parse_vertical_header_table(vheader_blocks, data_block, 
                                                           raw_blocks[skip_end-1]['text'] if skip_end > vheader_end + 1 else None)
                        if td and len(td) >= 3:
                            blocks.append({'type':'table','text':merged_text,'html':table_to_html(td),'table_data':td})
                            i = skip_end
                            continue

        # 财务表格检测（BNSF/BHE Earnings, Balance Sheet, Underwriting, Finance-related等）
        fin_td = _parse_financial_table(text)
        if fin_td:
            th = table_to_html(fin_td)
            tt = ' '.join([' '.join(r) for r in fin_td])
            blocks.append({'type':'table','text':tt,'html':th,'table_data':fin_td})
            i += 1
            continue

        # 多行表格检测
        # 检查是否是财务表头的后续数据block（如BNSF Earnings表头后的数据行）
        # 使用精确匹配，避免正文中提及的"BNSF"等关键词误匹配
        _fin_header_patterns = [
            r'^After-Tax Earnings',
            r'^Underwriting Profit',
            r'^BNSF\s+Earnings\s+\(',
            r'^Berkshire Hathaway Energy\s*\(',
            r'^Balance Sheet\s+\d',
            r'^Earnings Statement\s+\(',
            r'finance-related companies',
        ]
        _prev_is_fin_header = False
        for _back in range(1, min(6, len(blocks))):
            _prev_b = blocks[-_back] if len(blocks) >= _back else None
            if _prev_b and _prev_b['type'] == 'paragraph':
                _prev_text = _prev_b['text'].strip()
                if any(re.match(p, _prev_text, re.I) for p in _fin_header_patterns):
                    _prev_is_fin_header = True
                    break
            if _prev_b and _prev_b['type'] not in ('paragraph', 'table', 'data'):
                break
        if _prev_is_fin_header and (re.search(r'\.{3,}', text) or re.search(r'\$\s*[\d,]+', text) or re.match(r'^[\$\d\(\)\s,\.]+$', text.strip())):
            # 包含表格数据特征，保留为paragraph，让_merge_financial_tables处理
            blocks.append({'type':'paragraph','text':text,'html':html})
            i += 1
            continue
        if is_table_block(text):
            td = parse_table_from_text(text)
            if td:
                blocks.append({'type':'table','text':text,'html':table_to_html(td),'table_data':td})
                i += 1
                continue

        # 单行数据行
        if is_data_row(text):
            blocks.append({'type':'data','text':text,'html':html})
            i += 1
            continue

        # 普通段落
        blocks.append(_make_para(text, html))
        i += 1

    # 后处理：合并财务表格
    blocks = _merge_financial_tables(blocks)

    return blocks

def _detect_perf_headers(raw_blocks, i):
    """向前查找Performance表头block"""
    perf_headers = []
    for hj in range(i-1, max(i-12, -1), -1):
        prev_text = raw_blocks[hj]['text']
        prev_plain = re.sub(r'<[^>]+>', '', prev_text)
        if any(kw in prev_plain for kw in ['Annual Percentage Change', 'in Per-Share', 'S&P 500', 'Relative Results', 'Market Value', 'Book Value', 'Dividends']):
            perf_headers.insert(0, prev_plain)
        elif re.match(r'^\d{4}\s', prev_plain) or ('Compounded' in prev_plain):
            break
        elif perf_headers:
            # 如果已经找到了表头，继续向前看是否有更多
            if any(kw in prev_plain for kw in ['Performance', 'vs.', 'Corporate']):
                perf_headers.insert(0, prev_plain)
            else:
                break
        else:
            break
    return perf_headers

def _extract_col_names(perf_headers):
    """从表头block中提取列名（处理跨block分割的表头）"""
    # 先将所有表头block合并为一个文本，便于跨block匹配
    combined = ' | '.join(perf_headers)
    
    col_names = []
    
    # 匹配 "in Per-Share Book Value of Berkshire" 格式
    in_matches = re.findall(r'in\s+Per-Share\s+\w+(?:\s+\w+)*(?:\s+of\s+\w+)?', combined)
    col_names.extend(in_matches)
    
    # 匹配 "in S&P 500 with Dividends Included" 格式（可能跨block分割）
    # 先尝试完整匹配
    sp_full = re.findall(r'in\s+S&P\s+500\s+with\s+Dividends\s+Included', combined)
    col_names.extend(sp_full)
    if not sp_full:
        # 跨block分割：尝试匹配部分
        sp_partial = re.findall(r'in\s+S&P\s+500', combined)
        div_partial = re.findall(r'with\s+Dividends\s+Included', combined)
        if sp_partial and div_partial:
            col_names.append('in S&P 500 with Dividends Included')
        elif sp_partial:
            col_names.append('in S&P 500 with Dividends Included')
    
    if 'Relative Results' in combined:
        col_names.append('Relative Results')
    
    # 去重
    seen = set()
    unique = []
    for c in col_names:
        key = c.strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    
    return unique

def _default_col_names(num_vals):
    """根据列数生成默认列名"""
    if num_vals >= 3:
        return ['in Per-Share Book Value of Berkshire (%)', 'in S&P 500 with Dividends Included (%)', 'Relative Results (%)']
    elif num_vals >= 2:
        return ['in Per-Share Book Value of Berkshire (%)', 'in S&P 500 with Dividends Included (%)']
    else:
        return ['in Per-Share Book Value of Berkshire (%)']

def _remove_perf_header_blocks(blocks):
    """清除perf_table前面的描述行（避免重复）"""
    perf_idx = len(blocks) - 1
    remove_indices = []
    for bi in range(perf_idx - 1, -1, -1):
        bl = blocks[bi]
        lt = bl.get('text', '')
        if bl['type'] in ('paragraph', 'heading'):
            # 删除包含Performance表头关键词的行
            if any(kw in lt for kw in ['Annual Percentage Change', 'in Per-Share', 'S&P 500', 'Relative Results',
                                        'Performance vs.', 'Corporate Performance', 'Berkshire\'s Performance',
                                        'Berkshire\'s Corporate Performance']):
                remove_indices.append(bi)
            elif re.match(r'^\d{4}\s', lt) or ('Compounded' in lt):
                break
            elif remove_indices:
                # 已经在删除表头行，继续检查是否还有相关描述
                if any(kw in lt for kw in ['Year', 'Book Value', 'Market Value']):
                    remove_indices.append(bi)
                else:
                    break
            else:
                break
        else:
            break
    for bi in sorted(remove_indices, reverse=True):
        blocks.pop(bi)

def _make_para(text, html):
    hb = '<b>' in html and len(html) < 200
    return {'type':'heading' if hb else 'paragraph','text':text,'html':html}

def translate_table(table,cache,kp,is_perf=False):
    tr=[]
    for ri,row in enumerate(table):
        nr=[]
        for ci,cell in enumerate(row):
            cell=(cell or "").strip()
            # 公司名保护：去除(a)(b)等前缀后检查是否是公司名
            cell_clean = re.sub(r'^\([a-z]\)\s+', '', cell)
            if cell and _is_company_name(cell_clean):
                nr.append(cell)
            elif cell and _is_company_name(cell):
                nr.append(cell)
            elif is_perf and ri==0:
                # Performance表格：翻译表头
                if cell and not is_pure_number(cell):
                    nr.append(translate_text(cell,cache,text_hash(cell)))
                else:
                    nr.append(cell)
            elif cell and not is_pure_number(cell) and not is_data_row(cell):
                # 保护年份标记（如1981 (Rev.), 1982 (Est.)）
                year_marker_match = re.match(r'^(\d{4})(\s*\([^)]+\))?$', cell)
                if year_marker_match:
                    year = year_marker_match.group(1)
                    marker = year_marker_match.group(2) or ''
                    # 只翻译年份部分，保留标记
                    translated_year = translate_text(year, cache, text_hash(year))
                    nr.append(translated_year + marker)
                else:
                    nr.append(translate_text(cell,cache,text_hash(cell)))
            else:
                nr.append(cell)
        tr.append(nr)
    return tr

def table_to_html(table):
    if not table or len(table)<1: return ""
    # 过滤全空的列：检查每列是否所有行都为空
    if len(table) > 0:
        num_cols = max(len(row) for row in table)
        # 找出非空列的索引
        non_empty_cols = []
        for ci in range(num_cols):
            col_has_content = False
            for row in table:
                cell = (row[ci] if ci < len(row) else "").strip()
                if cell:
                    col_has_content = True
                    break
            if col_has_content:
                non_empty_cols.append(ci)
        # 如果有空列被过滤，重建表格
        if len(non_empty_cols) < num_cols:
            filtered_table = []
            for row in table:
                filtered_row = [(row[ci] if ci < len(row) else "") for ci in non_empty_cols]
                filtered_table.append(filtered_row)
            table = filtered_table
    h='<table>'
    for i,row in enumerate(table):
        tag='th' if i==0 else 'td'
        h+='<tr>'
        for cell in row:
            cell=(cell or "").strip()
            if not cell: cell=''
            h+=f'<{tag}>{html_mod.escape(cell)}</{tag}>'
        h+='</tr>'
    h+='</table>'; return h

def _perf_table_html(table_data):
    """生成Performance表格HTML，带colspan大列标题，支持动态列数"""
    if not table_data or len(table_data)<2: return table_to_html(table_data)
    num_cols = len(table_data[0])  # 动态列数
    h='<table>'
    # 检查是否已翻译
    first_header = table_data[0][1] if len(table_data[0]) > 1 else ''
    if re.search(r'[\u4e00-\u9fff]', str(first_header)):
        big_col = '年度百分比变化'
    else:
        big_col = 'Annual Percentage Change'
    h+=f'<tr><th rowspan="2">Year</th><th colspan="{num_cols-1}">{esc(big_col)}</th></tr>'
    # 小列标题行
    h+='<tr>'
    for ci in range(1, len(table_data[0])):
        h+=f'<th>{esc(table_data[0][ci])}</th>'
    h+='</tr>'
    # 数据行
    for row in table_data[1:]:
        h+='<tr>'
        for ci, cell in enumerate(row):
            cell=(cell or "").strip()
            if not cell: cell=''
            h+=f'<td>{esc(cell)}</td>'
        h+='</tr>'
    h+='</table>'
    return h

def clean_paragraphs(content):
    cleaned=[]
    i = 0
    while i < len(content):
        b = content[i]
        t=b.get('text','').strip()
        if not t or len(t)<5:
            i += 1
            continue
        if re.match(r'^\d{1,3}$',t):
            i += 1
            continue
        # 检查是否是表头描述行（如 "(in $ millions) 2023 2022"）
        if b['type'] in ('paragraph', 'heading') and i+1 < len(content):
            next_b = content[i+1]
            if next_b['type'] == 'table':
                # 检查当前行是否包含年份和单位信息
                year_matches = re.findall(r'\b(19\d{2}|20\d{2})\b', t)
                has_unit = bool(re.search(r'\(?\s*in\s+\$?\s*(millions?|billions?)\s*\)?', t, re.I) or
                               re.search(r'\(?\s*\d*000s?\s*omitted\s*\)?', t, re.I) or
                               re.search(r'\(?\s*in\s+\$?\s*\d*000s?\s*\)?', t, re.I))
                if year_matches and has_unit:
                    # 这是表头行，需要智能拆分
                    td = next_b.get('table_data', [])
                    if td:
                        # 提取单位信息
                        unit_match = re.search(r'\(?\s*(in\s+\$?\s*(?:millions?|billions?)|\d*000s?\s*omitted)\s*\)?', t, re.I)
                        unit_text = unit_match.group(0).strip() if unit_match else ''
                        # 提取年份和其他列名
                        remaining = t.replace(unit_text, '').strip()
                        # 按空格分割
                        header_parts = remaining.split()
                        header_parts = [p.strip() for p in header_parts if p.strip()]
                        # 如果单位文本存在，作为第一行
                        if unit_text:
                            if header_parts:
                                # 第一行：单位文本（合并所有列）
                                num_cols = len(td[0]) if td else len(header_parts) + 1
                                td.insert(0, [unit_text] + [''] * (num_cols - 1))
                                # 第二行：年份列头
                                td.insert(1, [''] + header_parts + [''] * (num_cols - 1 - len(header_parts)))
                            else:
                                td.insert(0, [unit_text])
                        else:
                            if header_parts:
                                td.insert(0, [''] + header_parts)
                        next_b['table_data'] = td
                        next_b['html'] = table_to_html(td)
                        next_b['text'] = t + ' ' + next_b.get('text', '')
                    cleaned.append(next_b)
                    i += 2
                    continue
                # 也检查没有年份但有单位的行（如 "(in $ millions)" 独立一行）
                elif has_unit and not year_matches:
                    td = next_b.get('table_data', [])
                    if td:
                        unit_match = re.search(r'\(?\s*(in\s+\$?\s*(?:millions?|billions?)|\d*000s?\s*omitted)\s*\)?', t, re.I)
                        unit_text = unit_match.group(0).strip() if unit_match else ''
                        if unit_text:
                            # 检查第一行是否已经有年份列头
                            if td and td[0]:
                                first_row = td[0]
                                # 如果第一行有数字（年份），在前面插入单位行
                                if any(re.match(r'^\d{4}$', c) for c in first_row):
                                    # 创建单位行：空列 + 单位
                                    unit_row = [''] * len(first_row)
                                    unit_row[0] = unit_text
                                    td.insert(0, unit_row)
                                else:
                                    # 第一行就是表头，在前面加单位
                                    td.insert(0, [unit_text])
                            else:
                                td.insert(0, [unit_text])
                            next_b['table_data'] = td
                            next_b['html'] = table_to_html(td)
                            next_b['text'] = t + ' ' + next_b.get('text', '')
                        cleaned.append(next_b)
                        i += 2
                        continue
                # 检查是否是表头关键词行（如 "Shares Company" 或 "12/31/21"）
                header_kws = ['Shares', 'Company', 'Percentage', 'Cost', 'Market', 'No. of']
                is_header = any(kw in t for kw in header_kws)
                is_date = bool(re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', t))
                if is_header or is_date:
                    # 收集连续的表头行
                    header_lines = [t]
                    skip = 1
                    j = i - 1
                    while j >= 0 and content[j]['type'] in ('paragraph', 'heading'):
                        prev_t = content[j].get('text', '').strip()
                        prev_is_header = any(kw in prev_t for kw in header_kws)
                        prev_is_date = bool(re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', prev_t))
                        prev_is_unit = bool(re.search(r'\(.*in\s+\$.*\)', prev_t) or re.search(r'\(.*millions?\)', prev_t, re.I))
                        if prev_is_header or prev_is_date or prev_is_unit:
                            header_lines.insert(0, prev_t)
                            skip += 1
                            j -= 1
                        else:
                            break
                    # 检查表格是否已经包含了这些表头信息（避免重复）
                    td = next_b.get('table_data', [])
                    if td:
                        # 检查表格所有行是否已经包含日期或表头关键词
                        all_rows_text = ' '.join(' '.join(r) for r in td)
                        already_has_date = is_date and any(hl in all_rows_text for hl in header_lines if re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', hl))
                        already_has_header = any(kw in all_rows_text for kw in header_kws)
                        if already_has_date or already_has_header:
                            # 表格已经包含了表头信息，跳过
                            cleaned.append(next_b)
                            i += 1 + skip
                            continue
                        # 将表头行合并到表格中
                        for hl in reversed(header_lines):
                            hl_parts = re.split(r'\s{2,}', hl)
                            hl_parts = [p.strip() for p in hl_parts if p.strip()]
                            if hl_parts:
                                td.insert(0, hl_parts)
                        next_b['table_data'] = td
                        next_b['html'] = table_to_html(td)
                        next_b['text'] = ' '.join(header_lines) + ' ' + next_b.get('text', '')
                    cleaned.append(next_b)
                    i += 1 + skip
                    continue
        # 注释换行处理：在 ** 和 *** 前插入 <br>
        if b['type'] == 'paragraph' and re.search(r'\*{2,3}', b.get('html', '')):
            # 英文格式：空格+**+空格；中文格式：句号+空格+**（后面可能没有空格）
            b['html'] = re.sub(r'(\s)(\*{2,3}\s)', r'<br>\2', b['html'])
            b['html'] = re.sub(r'([。.！!？?])\s+(\*{2,3})', r'\1<br>\2', b['html'])
        cleaned.append(b)
        i += 1
    return cleaned

def generate_index_html(yd,fd):
    yw=sorted(yd.keys(),key=int); ay=[str(y) for y in range(1977,2025)]; fy=sorted(fd.keys()); tp=sum(yd.values())
    grid=''
    for y in ay:
        if int(y) in yw: grid+=f'<a href="letters/{y}.html" class="yc has"><span class="yn">{y}</span><span class="yi">{yd[int(y)]}段</span></a>'
        else: grid+=f'<div class="yc no"><span class="yn">{y}</span><span class="yi">暂无</span></div>'
    def d(k): return ','.join([f'["{y}",{fd[y].get(k,0)}]' for y in fy])
    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>巴菲特致股东信 1977-2024</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif;background:#f5f5f0;color:#333}}
.hd{{background:linear-gradient(135deg,#1a365d,#2d5a87);color:#fff;padding:40px 20px;text-align:center}}
.hd h1{{font-size:2.2em;margin-bottom:8px;letter-spacing:2px}}.hd p{{font-size:1.1em;opacity:.85}}
.ctn{{max-width:1200px;margin:0 auto;padding:30px 20px}}
.st{{font-size:1.4em;margin:30px 0 15px;padding-bottom:8px;border-bottom:3px solid #1a365d;color:#1a365d}}
.yg{{display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:8px;margin:20px 0}}
.yc{{display:flex;flex-direction:column;align-items:center;padding:12px 6px;border-radius:8px;text-decoration:none;transition:all .2s}}
.yc.has{{background:#fff;color:#1a365d;box-shadow:0 2px 6px rgba(0,0,0,.08)}}
.yc.has:hover{{background:#1a365d;color:#fff;transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.15)}}
.yc.no{{background:#e8e8e3;color:#999;cursor:default}}.yn{{font-size:1.2em;font-weight:700}}.yi{{font-size:.7em;margin-top:3px;opacity:.7}}
.cg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:20px;margin:20px 0}}
.cb{{background:#fff;border-radius:10px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.cb h3{{font-size:.95em;color:#555;margin-bottom:10px}}.cc{{width:100%;height:320px}}
.ss{{display:flex;gap:15px;flex-wrap:wrap;margin:20px 0}}
.sc{{background:#fff;border-radius:10px;padding:18px;flex:1;min-width:160px;box-shadow:0 2px 8px rgba(0,0,0,.06);text-align:center}}
.sc .n{{font-size:1.8em;font-weight:700;color:#1a365d}}.sc .l{{font-size:.85em;color:#777;margin-top:4px}}
.ft{{text-align:center;padding:30px;color:#999;font-size:.85em}}
.hint{{background:#e8f5e9;border:1px solid #a5d6a7;border-radius:8px;padding:15px 20px;margin:20px 0;font-size:.9em;color:#2e7d32}}
</style></head><body>
<div class="hd"><h1>巴菲特致股东信</h1><p>Warren Buffett's Shareholder Letters · 1977-2024 · 中英双语对照</p></div>
<div class="ctn">
<div class="hint">📖 <strong>使用说明：</strong>点击年份进入阅读。每段英文原文与中文翻译并排显示。本页面为完全独立的静态网站，可离线使用。</div>
<div class="ss">
<div class="sc"><div class="n">48</div><div class="l">年信件</div></div>
<div class="sc"><div class="n">{len(yw)}</div><div class="l">年已收录</div></div>
<div class="sc"><div class="n">{tp:,}</div><div class="l">总段落数</div></div>
</div>
<h2 class="st">📅 选择年份阅读</h2><div class="yg">{grid}</div>
<h2 class="st">📊 财务数据概览</h2><div class="cg">
<div class="cb"><h3>总收入与净收益 (百万美元)</h3><div id="c1" class="cc"></div></div>
<div class="cb"><h3>总资产与股东权益 (百万美元)</h3><div id="c2" class="cc"></div></div>
<div class="cb"><h3>保险浮存金 (百万美元)</h3><div id="c3" class="cc"></div></div>
</div></div><div class="ft">数据来源：berkshirehathaway.com</div>
<script>
var fy={json.dumps(fy)};
echarts.init(document.getElementById('c1')).setOption({{tooltip:{{trigger:'axis'}},legend:{{data:['总收入','净收益']}},grid:{{left:60,right:20,bottom:40}},xAxis:{{type:'category',data:fy,axisLabel:{{rotate:45}}}},yAxis:{{type:'value'}},series:[{{name:'总收入',type:'bar',data:[{d("总收入(百万美元)")}],itemStyle:{{color:'#2d5a87'}}}},{{name:'净收益',type:'bar',data:[{d("净收益(百万美元)")}],itemStyle:{{color:'#e8a838'}}}}]}});
echarts.init(document.getElementById('c2')).setOption({{tooltip:{{trigger:'axis'}},legend:{{data:['总资产','股东权益']}},grid:{{left:60,right:20,bottom:40}},xAxis:{{type:'category',data:fy,axisLabel:{{rotate:45}}}},yAxis:{{type:'value'}},series:[{{name:'总资产',type:'line',data:[{d("总资产(百万美元)")}],smooth:true,lineStyle:{{width:3}},areaStyle:{{opacity:.1}},itemStyle:{{color:'#1a365d'}}}},{{name:'股东权益',type:'line',data:[{d("股东权益(百万美元)")}],smooth:true,lineStyle:{{width:3}},areaStyle:{{opacity:.1}},itemStyle:{{color:'#4a90d9'}}}}]}});
echarts.init(document.getElementById('c3')).setOption({{tooltip:{{trigger:'axis'}},grid:{{left:60,right:20,bottom:40}},xAxis:{{type:'category',data:fy,axisLabel:{{rotate:45}}}},yAxis:{{type:'value'}},series:[{{name:'保险浮存金',type:'bar',data:[{d("保险浮存金(百万美元)")}],itemStyle:{{color:'#5ba85b'}}}}]}});
window.addEventListener('resize',function(){{['c1','c2','c3'].forEach(function(id){{try{{echarts.getInstanceByDom(document.getElementById(id)).resize()}}catch(e){{}}}})}});
</script></body></html>'''

def _verify_and_fix_translations(year_contents, cache):
    """验证所有段落的翻译完整性，补充未翻译的段落"""
    import re as _re
    total_missing = 0
    total_fixed = 0
    
    for year, content in year_contents.items():
        if not content: continue
        missing = []
        for i, item in enumerate(content):
            if item['type'] not in ('paragraph', 'heading'): continue
            text = item.get('text', '')
            if len(text) < 30: continue
            key = text_hash(text)
            cached = cache.get(key, '')
            if not cached or not _re.search(r'[\u4e00-\u9fff]', cached):
                missing.append((i, text, key))
        
        if missing:
            total_missing += len(missing)
            print(f"  [{year}] {len(missing)} 个未翻译段落，补充翻译中...",flush=True)
            for idx, text, key in missing:
                tr = translate_text(text, cache, key)
                if tr != text and _re.search(r'[\u4e00-\u9fff]', tr):
                    total_fixed += 1
                else:
                    print(f"    仍然失败: {text[:50]}...",flush=True)
    
    if total_missing > 0:
        save_cache(cache)
        print(f"  验证完成: 缺失 {total_missing}, 修复 {total_fixed}",flush=True)
        # 重新生成HTML
        yw = set(year_contents.keys())
        for year, content in year_contents.items():
            if not content: continue
            try:
                # 构建fd: year -> {first, last}
                first_para = content[0].get('text', '') if content else ''
                last_para = content[-1].get('text', '') if content else ''
                fd_local = {str(year): {'first': first_para, 'last': last_para}}
                html = generate_letter_html(year, content, cache, fd_local, yw)
                with open(os.path.join(LETTERS_DIR, f"{year}.html"), 'w', encoding='utf-8') as f:
                    f.write(html)
            except Exception as e:
                print(f"    [{year}] HTML生成失败: {e}",flush=True)
        print("  HTML已重新生成",flush=True)
    else:
        print("  所有段落翻译完整 ✓",flush=True)

def generate_letter_html(year,content,cache,fd,yw):
    ys=str(year); fin=fd.get(ys,{})
    py,ny=str(year-1),str(year+1)
    np_=f'<a href="{py}.html" class="nb">← {py}</a>' if int(py) in yw else '<span class="nb dis">← 上一年</span>'
    nn_=f'<a href="{ny}.html" class="nb">{ny} →</a>' if int(ny) in yw else '<span class="nb dis">下一年 →</span>'
    fc=''
    for k,lb,cl in [("总收入(百万美元)","总收入","#2d5a87"),("净收益(百万美元)","净收益","#e8a838"),("总资产(百万美元)","总资产","#1a365d"),("股东权益(百万美元)","股东权益","#4a90d9"),("保险浮存金(百万美元)","浮存金","#5ba85b"),("运营收益(百万美元)","运营收益","#d94f4f")]:
        v=fin.get(k)
        if v is not None: fc+=f'<div class="fi"><span class="fl">{lb}</span><span class="fv" style="color:{cl}">{abs(v):,}{"(" if v<0 else ""}{" )" if v<0 else ""}</span></div>'
    rows=''; tidx=0; total=len(content)
    # 清理嵌套的<b>标签的辅助函数（如<b><b>o</b></b>）
    import re as _re
    def _clean_nested_bold(html_str):
        prev = None
        while prev != html_str:
            prev = html_str
            html_str = _re.sub(r'<b>(<b>[^<]*</b>)</b>', r'\1', html_str)
        return html_str
    for i,item in enumerate(content):
        if i>0 and i%10==0: print(f"  [{year}] {i}/{total}",flush=True)
        # 清理嵌套的<b>标签
        if 'html' in item and '<b>' in item.get('html',''):
            item['html'] = _clean_nested_bold(item['html'])

        if item['type'] in ('table','perf_table'):
            td=item.get('table_data',[])
            if td:
                tt=translate_table(td,cache,f"{year}_table_{tidx}",is_perf=(item['type']=='perf_table')); tidx+=1
                if item['type']=='perf_table':
                    # Performance表格：英文版保留英文列名，中文版翻译列名
                    zh = _perf_table_html(tt)
                    en = _perf_table_html(td)  # 英文版用原始列名
                else:
                    # 修复持仓表格空表头：如果表头有空列且文本包含Shares/Company关键词
                    if td and any('Shares' in str(c) or 'Company' in str(c) for c in td[0]):
                        empty_hdr = [i for i,c in enumerate(td[0]) if not c.strip()]
                        if empty_hdr and len(empty_hdr) >= 2:
                            # 检查数据行中是否有$符号的数字（Cost/Market列的特征）
                            has_dollar = any('$' in str(c) for row in td[1:] for c in row)
                            if has_dollar:
                                for idx in empty_hdr[:2]:
                                    if idx < len(td[0]):
                                        td[0][idx] = 'Cost' if td[0].count('Cost') == 0 else 'Market'
                    en = table_to_html(td)  # 使用修复后的td生成英文HTML
                    zh=table_to_html(tt)
            else:
                zh=item['html']
                en=item['html']
            css='row perf-table-row' if item['type']=='perf_table' else 'row table-row'
            rows+=f'<div class="{css}"><div class="en">{en}</div><div class="zh">{zh}</div></div>\n'

        elif item['type']=='data':
            rows+=f'<div class="row data-row"><div class="en">{item["html"]}</div><div class="zh"></div></div>\n'

        elif item['type']=='separator':
            rows+=f'<div class="row sep-row"><div class="en sep-cell">{item["html"]}</div><div class="zh sep-cell"></div></div>\n'

        elif item['type']=='pre_table':
            # 复杂缩进表格（如Net Earnings），中英文两侧分别显示原文和翻译截图
            img_path_en = item.get('image_path_en', '')
            img_path_zh = item.get('image_path_zh', '')
            
            if img_path_en and os.path.exists(img_path_en) and img_path_zh and os.path.exists(img_path_zh):
                img_rel_en = os.path.relpath(img_path_en, os.path.dirname(os.path.join(OUTPUT_DIR, 'letters', f'{year}.html')))
                img_rel_zh = os.path.relpath(img_path_zh, os.path.dirname(os.path.join(OUTPUT_DIR, 'letters', f'{year}.html')))
                rows+=f'<div class="row"><div class="en" style="padding:5px 10px"><img src="{img_rel_en}" style="max-width:100%;height:auto" alt="table"></div><div class="zh" style="padding:5px 10px"><img src="{img_rel_zh}" style="max-width:100%;height:auto" alt="表格"></div></div>\n'
            elif img_path_en and os.path.exists(img_path_en):
                # 只有原文截图时，两侧都显示原文
                img_rel = os.path.relpath(img_path_en, os.path.dirname(os.path.join(OUTPUT_DIR, 'letters', f'{year}.html')))
                rows+=f'<div class="row"><div class="en" style="padding:5px 10px"><img src="{img_rel}" style="max-width:100%;height:auto" alt="table"></div><div class="zh" style="padding:5px 10px"><img src="{img_rel}" style="max-width:100%;height:auto" alt="表格"></div></div>\n'
            else:
                # 无截图时，中英文两侧都显示原始<pre>格式表格
                rows+=f'<div class="row"><div class="en" style="padding:0">{item["html"]}</div><div class="zh" style="padding:0">{item["html"]}</div></div>\n'

        else:
            key=text_hash(item['text']); tr=translate_text(item['text'],cache,key)
            # 中文脚注换行处理：在 ** 和 *** 前插入 <br>
            tr=re.sub(r'([。.！!？?])\s+(\*{2,3})', r'\1<br>\2', tr)
            # 先进行HTML转义
            zh=esc(tr)
            # 再处理<b>标签：找到原文中的<b>内容，在中文翻译中也加粗
            bp=re.findall(r'<b>(.*?)</b>',item['html'])
            if bp:
                for b in bp:
                    bc=re.sub(r'<[^>]+>','',b).strip()
                    if bc and len(bc)>2:
                        bt=translate_text(bc,cache,f"{text_hash(bc)}")
                        if bt and bt!=bc:
                            # 在转义后的中文中查找并加粗
                            bt_esc = esc(bt)
                            if bt_esc in zh:
                                zh=zh.replace(bt_esc,f"<b>{bt_esc}</b>")
            css='row heading-row' if item['type']=='heading' else 'row'
            # 对英文内容进行HTML转义，但保留<b>等格式标签
            en_html = item["html"]
            rows+=f'<div class="{css}"><div class="en">{en_html}</div><div class="zh">{zh}</div></div>\n'

    if total>0 and total%10!=0: print(f"  [{year}] {total}/{total}",flush=True)
    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>巴菲特致股东信 {year}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif;background:#f5f5f0;color:#333}}
.tb{{background:linear-gradient(135deg,#1a365d,#2d5a87);color:#fff;padding:12px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.15)}}
.tb a{{color:#fff;text-decoration:none}}.yt{{font-size:1.4em;font-weight:700}}
.nb{{display:inline-block;padding:8px 18px;border-radius:6px;background:#1a365d;color:#fff;text-decoration:none;font-size:.9em;transition:background .2s}}
.nb:hover{{background:#2d5a87}}.nb.dis{{background:#ccc;cursor:default;pointer-events:none}}
.nv{{display:flex;justify-content:space-between;align-items:center;padding:10px 20px;background:#fff;border-bottom:1px solid #ddd}}
.fb{{background:#fff;padding:10px 20px;border-bottom:1px solid #eee;display:flex;gap:18px;flex-wrap:wrap}}
.fi{{display:flex;flex-direction:column;align-items:center;min-width:110px}}.fl{{font-size:.7em;color:#888}}.fv{{font-size:1em;font-weight:700}}
.row{{display:flex;border-bottom:1px solid #f0f0f0}}.row:hover{{background:#fafafa}}
.en{{flex:1;padding:10px 15px;border-right:2px solid #ddd;font-size:.9em;line-height:1.75;color:#444}}
.zh{{flex:1;padding:10px 15px;font-size:.93em;line-height:1.85;color:#333}}
.heading-row{{background:#f0f4f8}}.heading-row .en{{font-weight:bold;color:#1a365d}}.heading-row .zh{{font-weight:bold;color:#8b6914}}
.data-row{{background:#fafaf5}}.data-row .en{{font-family:"Courier New",monospace;font-size:.85em;white-space:pre;color:#555}}.data-row .zh{{background:#fafaf5}}
.sep-row{{border-bottom:1px solid #e0e0e0;background:#f0f0f0}}
.sep-cell{{text-align:center;color:#999;font-size:.85em;letter-spacing:4px}}
.table-row table,.perf-table-row table{{width:100%;border-collapse:collapse;margin:5px 0;font-size:.85em}}
.table-row table th,.table-row table td,.perf-table-row table th,.perf-table-row table td{{padding:4px 8px;border:1px solid #ddd;text-align:right}}
.table-row table th:first-child,.table-row table td:first-child,.perf-table-row table th:first-child,.perf-table-row table td:first-child{{text-align:left}}
.table-row table th,.perf-table-row table th{{background:#f5f5f0;font-weight:bold}}
.perf-table-row{{background:#f8f8f5}}
</style></head><body>
<div class="tb"><a href="../index.html">← 返回目录</a><span class="yt">{year} 年致股东信</span><span style="font-size:.85em;opacity:.8">中英双语</span></div>
<div class="nv">{np_}<span style="color:#888;font-size:.85em">{total} 段落</span>{nn_}</div>
{"<div class='fb'>"+fc+"</div>" if fc else ""}
{rows}</body></html>'''

def generate_empty_year(year,yw):
    py,ny=str(year-1),str(year+1)
    np_=f'<a href="{py}.html" class="nb">← {py}</a>' if year-1 in yw else '<span class="nb dis">←</span>'
    nn_=f'<a href="{ny}.html" class="nb">{ny} →</a>' if year+1 in yw else '<span class="nb dis">→</span>'
    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{year}</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:-apple-system,sans-serif;background:#f5f5f0;color:#333}}
.tb{{background:linear-gradient(135deg,#1a365d,#2d5a87);color:#fff;padding:12px 20px}}.tb a{{color:#fff;text-decoration:none}}
.nv{{display:flex;justify-content:space-between;padding:10px 20px;background:#fff;border-bottom:1px solid #ddd}}
.nb{{display:inline-block;padding:8px 18px;border-radius:6px;background:#1a365d;color:#fff;text-decoration:none;font-size:.9em}}
.nb.dis{{background:#ccc;cursor:default;pointer-events:none}}
.em{{text-align:center;padding:100px 20px;color:#999}}</style></head><body>
<div class="tb"><a href="../index.html">← 返回目录</a></div>
<div class="nv">{np_}<span>{year}</span>{nn_}</div>
<div class="em"><h2>📄 {year} 年信件暂未收录</h2><p>请访问 <a href="https://www.berkshirehathaway.com/letters/letters.html" style="color:#1a365d">berkshirehathaway.com</a></p></div></body></html>'''

def _generate_pre_table_images(year_contents, cache):
    """为所有pre_table块生成截图（原文和翻译），并将图片路径存入block"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright未安装，跳过截图",flush=True)
        return
    
    img_dir = os.path.join(OUTPUT_DIR, 'images')
    os.makedirs(img_dir, exist_ok=True)
    
    img_count = 0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            
            for year, content in year_contents.items():
                if not content: continue
                for block_idx, block in enumerate(content):
                    if block.get('type') != 'pre_table': continue
                    
                    html = block.get('html', '')
                    m = re.search(r'<pre[^>]*>(.*?)</pre>', html, re.DOTALL)
                    if not m: continue
                    pre_text = html_mod.unescape(m.group(1))
                    
                    # 生成原文截图
                    tmp_html_en = f'''<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>body{{margin:8px;padding:0;background:#fff;font-family:"Courier New",monospace;font-size:13px;line-height:1.4}}
pre{{white-space:pre;margin:0}}</style></head>
<body><pre>{html_mod.escape(pre_text)}</pre></body></html>'''
                    
                    try:
                        page.set_content(tmp_html_en)
                        height = page.evaluate('document.body.scrollHeight')
                        page.set_viewport_size({'width': 800, 'height': height + 20})
                        img_bytes = page.screenshot(full_page=True)
                        
                        img_filename = f'table_{year}_{block_idx}_en.png'
                        img_path_en = os.path.join(img_dir, img_filename)
                        with open(img_path_en, 'wb') as f:
                            f.write(img_bytes)
                        block['image_path_en'] = img_path_en
                        img_count += 1
                    except Exception as e:
                        print(f"  [{year}] 原文截图失败: {e}",flush=True)
                    
                    # 生成翻译后截图
                    # 翻译表格文本：保留数字和格式，翻译文本部分
                    translated_text = _translate_table_text(pre_text, cache)
                    
                    tmp_html_zh = f'''<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>body{{margin:8px;padding:0;background:#fff;font-family:"Courier New",monospace;font-size:13px;line-height:1.4}}
pre{{white-space:pre;margin:0}}</style></head>
<body><pre>{html_mod.escape(translated_text)}</pre></body></html>'''
                    
                    try:
                        page.set_content(tmp_html_zh)
                        height = page.evaluate('document.body.scrollHeight')
                        page.set_viewport_size({'width': 800, 'height': height + 20})
                        img_bytes = page.screenshot(full_page=True)
                        
                        img_filename = f'table_{year}_{block_idx}_zh.png'
                        img_path_zh = os.path.join(img_dir, img_filename)
                        with open(img_path_zh, 'wb') as f:
                            f.write(img_bytes)
                        block['image_path_zh'] = img_path_zh
                        img_count += 1
                    except Exception as e:
                        print(f"  [{year}] 翻译截图失败: {e}",flush=True)
            
            browser.close()
    except Exception as e:
        print(f"  Playwright启动失败，跳过截图: {e}",flush=True)
    print(f"  共生成 {img_count} 张截图",flush=True)

def _translate_table_text(text, cache):
    """翻译表格文本，保留数字和格式
    
    策略：
    1. 按行处理
    2. 识别数字列和文本列
    3. 只翻译文本部分，保留数字和格式
    """
    lines = text.split('\n')
    translated_lines = []
    
    for line in lines:
        # 检查是否是纯数字行或分隔线
        if re.match(r'^[\d\s\$\,\.\-\(\)\%]+$', line.strip()) or \
           re.match(r'^[\-\=\.\s]+$', line.strip()):
            translated_lines.append(line)
            continue
        
        # 检查是否是表头行（包含多个单词但没有点号引导）
        if ' . ' not in line and '...' not in line:
            # 翻译整行
            translated = translate_text(line.strip(), cache, text_hash(line))
            # 尝试保持原始对齐
            if len(translated) <= len(line):
                translated_lines.append(translated.ljust(len(line)))
            else:
                translated_lines.append(translated)
            continue
        
        # 数据行：分离标签和数值
        # 格式：Label ............ $123,456
        match = re.match(r'^(\s*)([A-Za-z][A-Za-z\s\-\&\(\)\.]+?)(\s*\.+\s*)(.*)$', line)
        if match:
            indent = match.group(1)
            label = match.group(2).strip()
            dots = match.group(3)
            values = match.group(4)
            
            # 翻译标签
            translated_label = translate_text(label, cache, text_hash(label))
            
            # 重建行，保持对齐
            new_line = f"{indent}{translated_label}{dots}{values}"
            translated_lines.append(new_line)
            continue
        
        # 其他情况，保留原样
        translated_lines.append(line)
    
    return '\n'.join(translated_lines)

def process_year_content(year,cache,fd):
    """只处理年份内容，不生成HTML。返回content或None。"""
    sf=SOURCES.get(year)
    if not sf: return None
    fp=os.path.join(BASE_DIR,sf)
    if not os.path.exists(fp): return None
    print(f"  [{year}] {sf}",flush=True)
    if sf.endswith('.html'): content=parse_html_source(fp)
    elif sf.endswith('.pdf'): content=extract_pdf_blocks(fp)
    else: return None
    content=clean_paragraphs(content)
    if not content: return None
    print(f"  [{year}] {len(content)} 块",flush=True)
    return content

def main():
    print("="*50,flush=True); print("巴菲特股东信构建 v4",flush=True); print("="*50,flush=True)
    cache=load_cache(); print(f"缓存: {len(cache)} 条",flush=True)
    fd={}
    if os.path.exists(FINANCIAL_FILE):
        with open(FINANCIAL_FILE,'r',encoding='utf-8') as f: fd=json.load(f)
    os.makedirs(LETTERS_DIR,exist_ok=True)
    yw=set(); yd={}; sy=sorted(SOURCES.keys())
    # 第一遍：处理所有年份的内容
    year_contents = {}
    for year in sy:
        content = process_year_content(year, cache, fd)
        if content:
            year_contents[year] = content
            yd[year] = len(content)
            yw.add(year)
            save_cache(cache)
    # 为pre_table块生成截图
    print("\n生成表格截图...",flush=True)
    _generate_pre_table_images(year_contents, cache)
    # 生成空年份
    for y in set(range(1977,2025)):
        if y not in yw:
            year_contents[y] = None
    # 第二遍：用完整的yw生成HTML
    for year in sorted(year_contents.keys()):
        content = year_contents[year]
        if content:
            html = generate_letter_html(year, content, cache, fd, yw)
            print(f"  [{year}] ✓",flush=True)
        else:
            html = generate_empty_year(year, yw)
        with open(os.path.join(LETTERS_DIR,f"{year}.html"),'w',encoding='utf-8') as f: f.write(html)
    print("\n生成首页...",flush=True)
    # 验证并补充未翻译的段落
    print("\n验证翻译完整性...",flush=True)
    _verify_and_fix_translations(year_contents, cache)
    print("\n生成首页...",flush=True)
    with open(os.path.join(OUTPUT_DIR,'index.html'),'w',encoding='utf-8') as f: f.write(generate_index_html(yd,fd))
    print(f"完成! {len(yw)}年, {sum(yd.values())}段",flush=True)

if __name__=='__main__': main()
