"""
创建测试用 SQLite 数据库，预置员工和订单数据
运行: python create_test_db.py
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "data", "test_sample.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# 如果已存在就删掉重建
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 员工表
cur.execute("""
CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    department TEXT,
    position TEXT,
    salary REAL,
    hire_date TEXT,
    email TEXT
)
""")

employees_data = [
    ("张三", "技术部", "高级工程师", 25000, "2020-03-15", "zhangsan@yg.com"),
    ("李四", "技术部", "工程师", 18000, "2021-07-01", "lisi@yg.com"),
    ("王五", "市场部", "市场经理", 22000, "2019-11-20", "wangwu@yg.com"),
    ("赵六", "财务部", "财务主管", 28000, "2018-05-10", "zhaoliu@yg.com"),
    ("孙七", "技术部", "架构师", 35000, "2017-01-08", "sunqi@yg.com"),
    ("周八", "人事部", "人事专员", 15000, "2022-09-01", "zhouba@yg.com"),
    ("吴九", "市场部", "市场专员", 12000, "2023-02-14", "wujiu@yg.com"),
    ("郑十", "技术部", "测试工程师", 16000, "2021-04-22", "zhengshi@yg.com"),
    ("钱十一", "财务部", "会计", 14000, "2022-06-30", "qianshiyi@yg.com"),
    ("陈十二", "技术部", "前端工程师", 20000, "2020-08-18", "chenshier@yg.com"),
]
cur.executemany("INSERT INTO employees (name, department, position, salary, hire_date, email) VALUES (?, ?, ?, ?, ?, ?)", employees_data)

# 订单表
cur.execute("""
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    product TEXT,
    amount REAL,
    order_date TEXT,
    status TEXT
)
""")

orders_data = [
    ("远光能源", "智能电表", 156000, "2024-01-10", "已完成"),
    ("国网电力", "运维平台", 890000, "2024-01-15", "已完成"),
    ("南方电网", "数据中台", 1200000, "2024-02-01", "进行中"),
    ("华能集团", "巡检机器人", 450000, "2024-02-20", "进行中"),
    ("大唐发电", "能效管理系统", 680000, "2024-03-05", "待确认"),
    ("远光能源", "充电桩管理", 320000, "2024-03-12", "已完成"),
    ("国网电力", "边缘计算网关", 210000, "2024-03-28", "进行中"),
    ("中广核", "安全监测平台", 950000, "2024-04-01", "待确认"),
]
cur.executemany("INSERT INTO orders (customer_name, product, amount, order_date, status) VALUES (?, ?, ?, ?, ?)", orders_data)

# 产品表
cur.execute("""
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    price REAL,
    stock INTEGER,
    description TEXT
)
""")

products_data = [
    ("智能电表", "电力设备", 1500, 2000, "三相智能电表，支持远程抄表"),
    ("运维平台", "软件系统", 89000, 999, "电力设备智能运维管理平台"),
    ("数据中台", "软件系统", 120000, 999, "企业级数据资产管理中台"),
    ("巡检机器人", "智能硬件", 45000, 50, "变电站智能巡检机器人"),
    ("充电桩管理系统", "软件系统", 32000, 999, "新能源汽车充电桩运营管理"),
    ("边缘计算网关", "电力设备", 2100, 500, "配电网边缘计算终端"),
    ("能效管理系统", "软件系统", 68000, 999, "企业能效监测与优化平台"),
    ("安全监测平台", "软件系统", 95000, 999, "核电站安全在线监测系统"),
]
cur.executemany("INSERT INTO products (name, category, price, stock, description) VALUES (?, ?, ?, ?, ?)", products_data)

conn.commit()
conn.close()
print(f"✓ 测试数据库已创建: {db_path}")
print(f"  - employees 表: 10 条记录")
print(f"  - orders 表: 8 条记录")
print(f"  - products 表: 8 条记录")
