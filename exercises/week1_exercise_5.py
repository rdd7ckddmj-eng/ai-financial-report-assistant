"""Week 1, Exercise 5: find a financial-logic error."""

company = {
    "name": "Example Retail Ltd",
    "revenue": 1_200_000,
    "net_profit": 120_000,
}


def calculate_net_profit_margin(revenue, net_profit):
    # 下面的计算存在一个故意设置的金融逻辑错误。
    return net_profit / revenue


reported_margin = calculate_net_profit_margin(
    company["revenue"],
    company["net_profit"],
)

print("Company:", company["name"])
print("Reported net profit margin:", f"{reported_margin:.1%}")

# 运行后思考：
# 1. 程序能否正常运行？它显示的净利润率是多少？
# 2. 为什么这个结果不合理？
# 3. 错误在哪一行？正确的计算应该怎样写？
