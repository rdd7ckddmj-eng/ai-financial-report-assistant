"""Week 1, Exercise 3: use a list and a loop."""

# 列表可以把多个相关数据保存在一起。
annual_revenues = [1_000_000, 1_200_000, 1_400_000, 1600000]

total_revenue = 0

# for 循环会依次取出列表中的每一个收入数字。
for revenue in annual_revenues:
    print("Annual revenue:", f"{revenue:,}")
    total_revenue = total_revenue + revenue

number_of_years = len(annual_revenues)
average_revenue = total_revenue / number_of_years

print("Number of years:", number_of_years)
print("Total revenue:", f"{total_revenue:,.0f}")
print("Average revenue:", f"{average_revenue:,.0f}")

# 运行后思考：
# 1. for 循环一共运行了几次？为什么？
# 2. 如果在列表末尾增加 1_600_000，新的平均收入是多少？
