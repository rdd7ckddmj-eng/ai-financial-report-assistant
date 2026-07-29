"""Week 1, Exercise 2: use if/else to make a simple decision."""

company_name = "Example Retail Ltd"
revenue = 1_200_000
net_profit = 90000

# 公司的目标净利润率是 10%。
target_margin = 0.10
net_profit_margin = net_profit / revenue

# if 检查条件是否成立；else 处理条件不成立的情况。
if net_profit_margin >= target_margin:
    result = "Target met"
else:
    result = "Below target"

print("Company:", company_name)
print("Net profit margin:", f"{net_profit_margin:.1%}")
print("Assessment:", result)

# 运行后思考：
# 1. 为什么当前结果是 Target met？
# 2. 如果把 net_profit 改为 90_000，结果会变成什么？
