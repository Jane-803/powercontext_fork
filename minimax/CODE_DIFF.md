# 业务代码差异

完整修改前后文件分别位于 `snapshots/before/catalog.py` 和 `sample_app/catalog.py`。核心差异如下：

```diff
 def filter_places(
     places: list[Place],
     *,
     category: str | None = None,
     max_distance_m: int | None = None,
+    min_rating: float | None = None,
 ) -> list[Place]:
     if max_distance_m is not None and max_distance_m < 0:
         raise ValueError("max_distance_m must be non-negative")
+    if min_rating is not None and not 0 <= min_rating <= 5:
+        raise ValueError("min_rating must be between 0 and 5")
     return [
         place
         for place in places
         if (category is None or place["category"] == category)
         and (max_distance_m is None or place["distance_m"] <= max_distance_m)
+        and (min_rating is None or place["rating"] >= min_rating)
     ]
```
