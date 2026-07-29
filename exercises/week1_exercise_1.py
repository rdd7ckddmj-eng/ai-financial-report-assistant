"""Week 1, Exercise 1: variables and a simple financial calculation."""

# A string stores text.
company_name = "Example Retail Ltd"

# Integers store whole numbers.
revenue = 1_200_000
net_profit = 96_000

# Net profit margin = net profit / revenue.
net_profit_margin = net_profit / revenue

print("Company:", company_name)
print("Revenue:", revenue)
print("Net profit:", net_profit)
print("Net profit margin:", f"{net_profit_margin:.1%}")

# After running the file, think about these questions:
# 1. Why is net_profit_margin equal to 8.0%?
# 2. If net_profit changes to 120_000, what will the margin become?
