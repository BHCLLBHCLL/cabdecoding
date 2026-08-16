"""One-shot disk patch for docs/function_gap_analysis.md (2026-08-16).

The Edit tool's file view for this path is stale (disk mtime frozen);
this script applies the four gap-sync replacements directly to disk.
"""
import io
import sys

P = "docs/function_gap_analysis.md"
src = io.open(P, "r", encoding="utf-8", newline="").read()

REPL = []

REPL.append((
    """并回写 x_t 成员），4 项测试全过（40mm 块 → 530/422 三角）。
     详见 docs/pskernel_user_guide.md §6.9。""",
    """并回写 x_t 成员），测试全过（40mm 块 → 530/422 三角）。
     详见 docs/pskernel_user_guide.md §6.9。**Edit Solid「Delete faces」
     亦已接 PK_FACE_delete_2**（2026-08-16：picked 三角→match_face_by_plane
     →逐面删除+cap→x_t 原地写回，Preview 显示匹配面 tag；其余 7 类
     sheet/heal 算子仍为 intent 占位且明示）。""",
))

REPL.append((
    """   - **晚间复核新发现——Part Simplification 为假 UI**：三 Method 单选
     （internal loop / thin geometry / 2.5D）不绑定任何逻辑分支，
     Preview/Cancel 按钮 `lambda: None`（`cab_edit_dialogs.py`），
     `_exec` 实际只调 tess 级删面。要么接真算子（PK heal/简化），
     要么移除摆设，现状最伤可信度（R2 处理）。""",
    """   - **晚间复核新发现——Part Simplification 为假 UI（R1 已解，
     2026-08-16）**：原状三 Method 单选不绑定逻辑、Preview/Cancel
     `lambda: None`、`_exec` 只做 tess 级删面。现已接真算子：Method →
     `auto_faces_by_method`（PK 拓扑面选择：internal_loop=非平面 /
     thin_geometry=面积<25%最大面 / external_2d5=最长轴法向），
     Preview 报告选中面数，Delete → `simplify_part_faces_pk`
     （`PK_FACE_delete_2` 逐面删除 + cap 愈合 + x_t 成员原地写回 +
     cad 网格刷新，无 pskernel 时回退 tess 删除）。关键 kernel 事实
     （heal 只有 none/cap、相邻面批量删 rc525、`PK_FACE_ask_type`
     不可用、`_find_body_tags` 加 md5 缓存保 tag 稳定 + part 自有
     file 引用优先）见 docs/pskernel_user_guide.md §5.3；
     e2e 测试 test_m33_edit_kernel.py::
     test_part_simplification_pk_face_delete（贯穿槽四壁场景全链路）。""",
))

REPL.append((
    """① all 模式网格线 e2e 收敛（顶点→线合并/取整规则，探针已实测差距
`57×132×130` vs `59×118,121`）；② 假 UI 清理（Part Simplification 三 Method 摆设）；
③ 表达式管理器/
moving body 运动表等低成本深度项。整体完成度 **≈76%**，其中
「可运行、可持久化、可导出求解」的 MVP 闭环已完整。""",
    """① all 模式网格线 e2e 收敛（**已解，2026-08-16**：all `(59,118,121)`、
rep `(57,91,92)` 双 MATCH，`test_golden_reference.py` 原生断言固化）；
② 假 UI 清理（**Part Simplification / Edit Solid Delete faces 已解，
2026-08-16**，PK_FACE_delete_2 全链路，见 P1 节；blend ABI 亦已解，
见 pskernel_user_guide §6.9）；
③ 表达式管理器/
moving body 运动表等低成本深度项。整体完成度 **≈78%**（P0 全清 +
Edit B-rep 假 UI 接真算子），其中
「可运行、可持久化、可导出求解」的 MVP 闭环已完整。""",
))

REPL.append((
    """| **R2**（3–5 天） | 假 UI 清理 + 低垂果实 | Simplification 三 Method 绑真逻辑或移除摆设；`express_list` 接 Source 页表达式管理器（列表/编辑/删除）；包装并接线 `SetMoveBodyOption` 运动定义表（零件属性面板） | 无 `lambda: None` 占位按钮；表达式可往返管理；运动表写回→重载→`.s` 导出正确 |""",
    """| **R2**（3–5 天） | 假 UI 清理 + 低垂果实 | ~~Simplification 三 Method 绑真逻辑~~（✅ 2026-08-16 提前完成，PK_FACE_delete_2 全链路，Edit Solid Delete faces 同步接通）；`express_list` 接 Source 页表达式管理器（列表/编辑/删除）；包装并接线 `SetMoveBodyOption` 运动定义表（零件属性面板） | 无 `lambda: None` 占位按钮（✅ 已达成）；表达式可往返管理；运动表写回→重载→`.s` 导出正确 |""",
))

out = src
crlf = "\r\n" in src
if crlf:
    REPL = [(o.replace("\n", "\r\n"), n.replace("\n", "\r\n"))
            for o, n in REPL]
applied = 0
for old, new in REPL:
    if old in out:
        out = out.replace(old, new, 1)
        applied += 1
    elif new in out:
        applied += 1  # already applied
    else:
        print("MISS:", old[:60].replace("\r\n", "\\n"))
io.open(P, "w", encoding="utf-8", newline="").write(out)
print(f"applied {applied}/{len(REPL)}")
sys.exit(0 if applied == len(REPL) else 1)
