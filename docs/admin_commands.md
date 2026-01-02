# 管理员调试命令手册

> 仅限 `config.json` 中配置的 `admin_qq` 使用

---

## SQL: 数据库直接操作

### 格式
```
SQL:你的SQL语句
```

### 查询示例

```sql
-- 查看所有玩家
SQL:SELECT * FROM players

-- 查看指定玩家
SQL:SELECT * FROM players WHERE qq_id = '123456'

-- 查看玩家积分排行
SQL:SELECT nickname, current_score FROM players ORDER BY current_score DESC

-- 查看玩家位置
SQL:SELECT * FROM player_positions WHERE qq_id = '123456'

-- 查看所有临时标记
SQL:SELECT p.nickname, pp.column_number, pp.position FROM player_positions pp JOIN players p ON pp.qq_id = p.qq_id WHERE pp.marker_type = 'temp'

-- 查看玩家背包
SQL:SELECT * FROM player_inventory WHERE qq_id = '123456'

-- 查看游戏状态
SQL:SELECT * FROM game_state WHERE qq_id = '123456'

-- 查看商店道具
SQL:SELECT item_id, item_name, price, unlocked FROM shop_items

-- 查看契约关系
SQL:SELECT * FROM player_contracts

-- 查看游戏设置
SQL:SELECT * FROM game_settings

-- 查看首达记录
SQL:SELECT * FROM first_achievements

-- 查看成就
SQL:SELECT * FROM player_achievements WHERE qq_id = '123456'
```

### 修改示例

```sql
-- 修改玩家积分
SQL:UPDATE players SET current_score = 500 WHERE qq_id = '123456'

-- 批量加积分
SQL:UPDATE players SET current_score = current_score + 100

-- 修改掷骰消耗
SQL:UPDATE game_settings SET setting_value = '5' WHERE setting_key = 'roll_cost'

-- 解锁道具
SQL:UPDATE shop_items SET unlocked = 1 WHERE item_id = 20

-- 解锁所有道具
SQL:UPDATE shop_items SET unlocked = 1

-- 清除玩家临时标记
SQL:DELETE FROM player_positions WHERE qq_id = '123456' AND marker_type = 'temp'

-- 重置商店销售数量
SQL:UPDATE shop_items SET global_sold = 0

-- 清除玩家锁定状态
SQL:UPDATE game_state SET lockout_until = NULL WHERE qq_id = '123456'

-- 设置玩家阵营
SQL:UPDATE players SET faction = '收养人' WHERE qq_id = '123456'

-- 删除玩家背包道具
SQL:DELETE FROM player_inventory WHERE qq_id = '123456' AND item_name = '败者○尘'

-- 清除首达记录
SQL:DELETE FROM first_achievements WHERE column_number = 7
```

---

## PY: Python 代码执行

### 格式
```
PY:Python表达式或语句
```

### 可用变量

| 变量 | 类型 | 说明 |
|------|------|------|
| `engine` | GameEngine | 游戏引擎实例 |
| `db` | Connection | 数据库连接 |
| `player_dao` | PlayerDAO | 玩家数据访问 |
| `position_dao` | PositionDAO | 位置数据访问 |
| `inventory_dao` | InventoryDAO | 背包数据访问 |
| `state_dao` | GameStateDAO | 游戏状态访问 |
| `shop_dao` | ShopDAO | 商店数据访问 |
| `achievement_dao` | AchievementDAO | 成就数据访问 |
| `settings_dao` | GameSettingsDAO | 游戏设置访问 |
| `contract_dao` | ContractDAO | 契约数据访问 |

---

### PlayerDAO 玩家管理

```python
-- 查询玩家信息
PY:player_dao.get_player('123456')

-- 获取所有玩家
PY:player_dao.get_all_players()

-- 获取所有玩家昵称列表
PY:[p.nickname for p in player_dao.get_all_players()]

-- 加积分
PY:player_dao.add_score('123456', 100)

-- 减积分
PY:player_dao.add_score('123456', -50)

-- 设置阵营
PY:player_dao.update_faction('123456', '收养人')
PY:player_dao.update_faction('123456', 'Aeonreth')

-- 删除玩家（慎用！）
PY:player_dao.delete_player('123456')

-- 查询积分最高的玩家
PY:max(player_dao.get_all_players(), key=lambda p: p.current_score)
```

---

### PositionDAO 位置管理

```python
-- 查询玩家所有位置
PY:position_dao.get_positions('123456')

-- 只查临时标记
PY:position_dao.get_positions('123456', 'temp')

-- 只查永久标记
PY:position_dao.get_positions('123456', 'permanent')

-- 添加临时标记（列10第3格）
PY:position_dao.add_or_update_position('123456', 10, 3, 'temp')

-- 添加永久标记（列7第5格）
PY:position_dao.add_or_update_position('123456', 7, 5, 'permanent')

-- 移动标记（同一列会自动更新位置）
PY:position_dao.add_or_update_position('123456', 10, 5, 'temp')

-- 删除指定列的临时标记
PY:position_dao.remove_position('123456', 10, 'temp')

-- 清除玩家所有临时标记
PY:position_dao.clear_temp_positions('123456')

-- 临时标记转永久
PY:position_dao.convert_temp_to_permanent('123456')

-- 指定列临时转永久
PY:position_dao.convert_temp_to_permanent_by_column('123456', 10)

-- 查看地图上所有玩家位置
PY:position_dao.get_all_positions_on_map()
```

---

### InventoryDAO 背包管理

```python
-- 查看背包
PY:inventory_dao.get_inventory('123456')

-- 查看背包道具名称列表
PY:[i.item_name for i in inventory_dao.get_inventory('123456')]

-- 添加道具
PY:inventory_dao.add_item('123456', 1, '败者○尘', 'item')
PY:inventory_dao.add_item('123456', 9103, '免费掷骰券', 'hidden_item')

-- 删除道具（按ID）
PY:inventory_dao.remove_item('123456', 1)

-- 删除道具（按名称）
PY:inventory_dao.remove_item_by_name('123456', '败者○尘')

-- 检查是否拥有道具
PY:inventory_dao.has_item('123456', 1)

-- 查询道具数量
PY:inventory_dao.get_item_count('123456', 1)
```

---

### GameStateDAO 游戏状态

```python
-- 查看玩家状态
PY:state_dao.get_state('123456')

-- 设置免费回合
PY:s=state_dao.get_state('123456'); s.free_rounds=3; state_dao.update_state(s)

-- 清除锁定
PY:s=state_dao.get_state('123456'); s.lockout_until=None; state_dao.update_state(s)

-- 设置跳过回合
PY:s=state_dao.get_state('123456'); s.skipped_rounds=2; state_dao.update_state(s)

-- 清除跳过回合
PY:s=state_dao.get_state('123456'); s.skipped_rounds=0; state_dao.update_state(s)

-- 强制结束当前轮次
PY:s=state_dao.get_state('123456'); s.current_round_active=False; s.last_dice_result=None; state_dao.update_state(s)

-- 允许开始新轮次
PY:s=state_dao.get_state('123456'); s.can_start_new_round=True; state_dao.update_state(s)

-- 设置登顶列（添加列7）
PY:s=state_dao.get_state('123456'); s.topped_columns.append(7); state_dao.update_state(s)

-- 清除登顶列
PY:s=state_dao.get_state('123456'); s.topped_columns=[]; state_dao.update_state(s)

-- 设置下次投骰双倍消耗
PY:s=state_dao.get_state('123456'); s.next_roll_double_cost=True; state_dao.update_state(s)

-- 设置陷阱免疫
PY:s=state_dao.get_state('123456'); s.immune_next_trap=1; state_dao.update_state(s)

-- 减少回合消耗（黑喵效果）
PY:s=state_dao.get_state('123456'); s.cost_reduction=2; state_dao.update_state(s)
```

---

### GameSettingsDAO 游戏设置

```python
-- 查看当前掷骰消耗
PY:settings_dao.get_roll_cost()

-- 修改掷骰消耗
PY:settings_dao.set_roll_cost(5)

-- 查看所有设置
PY:settings_dao.get_all_settings()

-- 通用设置方法
PY:settings_dao.set_setting('roll_cost', '8', '每轮掷骰消耗')

-- 获取设置值
PY:settings_dao.get_setting('roll_cost')
PY:settings_dao.get_int_setting('roll_cost', 10)
```

---

### ShopDAO 商店管理

```python
-- 查看所有道具
PY:shop_dao.get_all_items()

-- 只看已解锁道具
PY:shop_dao.get_all_items(unlocked_only=True)

-- 查看道具详情
PY:shop_dao.get_item(1)
PY:shop_dao.get_item_by_name('败者○尘')

-- 解锁道具
PY:shop_dao.unlock_item(20)

-- 记录购买（增加销售数）
PY:shop_dao.purchase_item(1)
```

---

### AchievementDAO 成就管理

```python
-- 查看玩家成就
PY:achievement_dao.get_achievements('123456')

-- 添加成就
PY:achievement_dao.add_achievement('123456', 1, '先驱者', 'normal')
PY:achievement_dao.add_achievement('123456', 101, '隐藏成就', 'hidden')
PY:achievement_dao.add_achievement('123456', 7, '列7首达', 'first_clear')

-- 检查是否有成就
PY:achievement_dao.has_achievement('123456', 1, 'normal')

-- 删除成就
PY:achievement_dao.remove_achievement('123456', '先驱者')
```

---

### ContractDAO 契约管理

```python
-- 查看契约对象
PY:engine.contract_dao.get_contract_partner('123456')

-- 检查是否有契约
PY:engine.contract_dao.has_contract('123456')

-- 检查两人是否有契约
PY:engine.contract_dao.are_contracted('123456', '654321')

-- 建立契约
PY:engine.contract_dao.create_contract('123456', '654321')

-- 解除契约
PY:engine.contract_dao.remove_contract('123456')

-- 查看所有契约
PY:engine.contract_dao.get_all_contracts()
```

---

### GameEngine 游戏引擎

```python
-- 查看玩家完整信息
PY:engine.get_player_info('123456')

-- 投骰子（会扣积分）
PY:engine.roll_dice('123456')

-- 结束轮次（保留进度）
PY:engine.end_round('123456')

-- 放弃轮次（清除临时标记）
PY:engine.abandon_round('123456')

-- 购买道具
PY:engine.buy_item('123456', '败者○尘')

-- 使用道具
PY:engine.use_item('123456', '败者○尘')
```

---

## 常用组合操作

### 重置玩家状态
```python
PY:s=state_dao.get_state('QQ'); s.current_round_active=False; s.can_start_new_round=True; s.last_dice_result=None; s.skipped_rounds=0; s.lockout_until=None; state_dao.update_state(s)
```

### 给全体玩家加积分
```sql
SQL:UPDATE players SET current_score = current_score + 100
```

### 清空玩家背包
```sql
SQL:DELETE FROM player_inventory WHERE qq_id = '123456'
```

### 查看谁在某个位置
```sql
SQL:SELECT p.nickname, pp.* FROM player_positions pp JOIN players p ON pp.qq_id = p.qq_id WHERE pp.column_number = 10 AND pp.position = 5
```

### 批量解除所有锁定
```sql
SQL:UPDATE game_state SET lockout_until = NULL
```

---

## 数据库表结构速查

| 表名 | 说明 |
|------|------|
| `players` | 玩家基础信息（QQ、昵称、阵营、积分） |
| `player_positions` | 玩家棋子位置 |
| `player_inventory` | 玩家背包 |
| `game_state` | 玩家游戏状态（轮次、效果等） |
| `shop_items` | 商店道具 |
| `player_achievements` | 玩家成就 |
| `player_contracts` | 契约关系 |
| `first_achievements` | 首达记录 |
| `game_settings` | 游戏设置 |
| `daily_limits` | 每日限制记录 |
| `gem_pools` | 宝石池沼 |
| `branch_events` | 支线活动 |
| `branch_teams` | 支线队伍 |
| `custom_commands` | 自定义口令 |
