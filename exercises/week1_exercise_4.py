"""Week 1, Exercise 4: use a dictionary and a function."""

# 字典使用“键: 值”保存一组有名称的数据。
company = {
    "name": "Example Retail Ltd",
    "revenue": 1_200_000,
    "net_profit": 150_000,
}


# 函数把可以重复使用的计算步骤放在一起。
def calculate_net_profit_margin(revenue, net_profit):
    margin = net_profit / revenue
    return margin


net_profit_margin = calculate_net_profit_margin(
    company["revenue"],
    company["net_profit"],
)

print("Company:", company["name"])
print("Revenue:", f"{company['revenue']:,}")
print("Net profit:", f"{company['net_profit']:,}")
print("Net profit margin:", f"{net_profit_margin:.1%}")

# 运行后思考：
# 1. return margin 的作用是什么？
# 2. 如果净利润改为 150_000，函数返回的净利润率是多少？
