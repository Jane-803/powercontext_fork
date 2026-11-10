# 验证样例

## 要改什么

为 `filter_places` 增加可选 `min_rating`。评分大于等于阈值才保留，阈值必须在 0..5。

## 必须保持什么

分类精确匹配、最大距离包含边界、负距离抛出 `ValueError`、省略新参数时行为不变、结果保持输入顺序。

## 必须进入上下文的来源

- 当前规格：`specs/place-filter-v2.md`，version 2
- 待改代码：`snapshots/before/catalog.py` 中的 `filter_places`
- 功能和回归测试：`tests/test_catalog.py`
- 设计约束：`docs/decision-ordering.md`
- PowerContext 状态：当前 Handoff revision、完成项、待办和下一步

## 预期结果

首次只导入 `corpus/initial.json` 时可检索 v1。随后导入 `corpus/update-v2.json`，同一任务的输出只包含当前 v2 规格。旧实现运行固定测试集退出码非零；最终实现退出码为零。保存状态、停止当前 CLI 并再次调用 `load-state` 后，仍能读回同一 Scope 的 Handoff。

详细操作和重置方法见 `README.md`。
