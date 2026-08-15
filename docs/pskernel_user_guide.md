# pskernel 逆向调用手册（Parasolid V37）

> 面向 cabdecoding 代码仓的 pskernel.dll（Cradle CFD 2025.2 内嵌 Parasolid 内核，
> 实为 Parasolid V37）的逆向工程与 ctypes 调用参考。公开 V35 文档仅作 ABI 骨架参考，
> V37 在结构体版本、PK_TRANSF_t 表示、facet 表顺序等处均有差异，本文逐项记录实测结论。
> 参考实现：本仓 ps_facet2_nodes.py / ps_tessellate.py / cab_ps_ops.py，
> 以及姊妹仓 D:\training\cgns\pphdecoding（ps_facet2_nodes.py 66KB 更完整）。

---

## 0. 概览

- DLL：C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\pskernel.dll
  （约 72MB，1454 个导出，其中 PK_* 1204 个）。
- Schema：同目录 Schemas\*.sch_txt（文本）与 *.s_t（二进制），frustrum 按名匹配。
- 版本：Parasolid V37。公开头文件为 V35（http://www.q-solid.com/Parasolid_Docs_V35/，
  结构体布局、x_t 流格式等资源清单见 §9），差异见 §4.1。
- 入口链路（STpre 显示网格生成，反汇编确认）：

      STpreBase_Bx64.dll
        ?MakeFacet@PreBody@@QEAAHHPEAVFacetParam@@@Z        RVA 0x293A20
        ?MakeFacetParam@PreBody@@QEAAPEAVFacetParam@@QEAN@Z RVA 0x293C20
          v
      ParasolidGW_Bx64.dll（Cradle 封装）
        ?PKBody_GetTriangles@LocalParasolid@@...            RVA 0xA49A0
        ?PKFaces_RenderV3@LocalParasolid@@...               RVA 0x1415C0 / 0x141850
          v
      pskernel.dll（真正内核）
        PK_TOPOL_facet_2                                    RVA 0x44DFA0
        PK_TOPOL_facet_2_r_f                                RVA 0x44FCE0

---

## 1. 环境与会话引导（session bootstrap）

ps_facet2_nodes.py 的 _PsSession.__init__ 是唯一会话入口：

      os.add_dll_directory(str(prog))                 # 让 pskernel 找到依赖 DLL
      os.environ["PATH"] = str(prog) + ";" + PATH
      os.environ["P_SCHEMA"] = str(prog / "Schemas")  # schema 目录
      self.pk = C.WinDLL(str(prog / "pskernel.dll"))
      self._build_frustrum()                           # 注册 FRU 回调
      self._start()                                    # PK_SESSION_start

find_cradle_programs() 按顺序探测：
1. 环境变量 CRADLE_PROGRAMS 或 P_SCHEMA（后者取父目录）；
2. 默认路径 C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64；
3. glob C:\Program Files\Cradle\CradleCFD*\Programs_x64（倒序取最新）。
判定：目录下同时存在 pskernel.dll 与 Schemas。

PK_SESSION_start 用 _START 结构 (o_t_version=1, journal_file=None, user_field=0, reserved=1)。

关键技巧——关闭参数检查：会话启动后必须

      pk.PK_SESSION_set_check_arguments(0)

否则结构体版本不匹配会先抛 PK_ERROR_o_t_version_incorrect（5022）。这是反向工程的
核心 workaround：STpre 自己总传匹配版本，我们传逆向出的版本 + 关检查。

---

## 2. FRU（frustrum）回调与 I/O

PK_SESSION_register_frustrum(_FRU) 传入 28 个 void* 回调（_FRU 结构按 fstart fabort
fstop fmallo fmfree gosgmt goopsg goclsg gopixl gooppx goclpx ffoprd ffopwr ffclos
ffread ffwrit ffoprb ffseek fftell fgcrcu fgcrsu fgevcu fgevsu fgprcu fgprsu ucoprd
ucopwr 顺序）。当前实现并验证了 15 个：

| 回调 | 作用 | 要点 |
|---|---|---|
| FSTART/FSTOP | 会话起止 | ifail=0 |
| FMALLO/FMFREE | 内核内存分配 | 分配 c_char 缓冲并保留引用防 GC |
| FFOPRD | 打开读文件 | guise=6 按名匹配 Schemas/*.sch_txt/.s_t；否则按路径读 x_t |
| FFREAD | 顺序读 | 文本逐行、二进制裸读，维护 loc 偏移 |
| FFOPWR | 打开写文件 | 新建 bytearray 缓冲，返回 strid |
| FFWRIT | 写 | 追加到缓冲 |
| FFCLOS | 关闭 | 写缓冲关闭时把 bytes 存入 _transmit_output[key] |
| GOSGMT | GO 段回调 | 捕获 segment（facet 段 type=2016）供 render_facet 兜底 |
| GOOPSG/GOCLSG/GOPIXL/GOOPPX/GOCLPX | GO 其余 | 空实现 ifail=0 |

关键技巧——写回捕获：PK_PART_transmit 的文本输出不是返回值，而是通过
FFOPWR -> FFWRIT -> FFCLOS 回调写入。早期用桩回调导致 transmit 返回
973（PK_ERROR_file_access_error）；把写回调真正落进内存缓冲后解决。
ps_facet2_nodes.py 在 _build_frustrum 里维护 _write_files/_write_paths/_transmit_output 三张表。

---

## 3. 核心数据流

      x_t 文件
        +- receive_xt()          PK_PART_receive(key, _RECV, &n, &parts)
        |     +- 返回 body tag 列表（V37 直接返回 body tag，非 V35 的 part tag）
        +- expand_to_bodies()    PK_ENTITY_ask_class 分类 + PK_ASSEMBLY_ask_parts 递归展开
        |     +- 5006=body / 5007=instance / 5008=assembly；assembly 递归、body 保留
        +- body_name()           PK_PART_ask_all_attribs(SDL/TYSA_NAME) + PK_ATTRIB_ask_string
        +- facet2()/facet_body() PK_TOPOL_facet_2（表解码，见 §6.1）
        |     +- 失败则 facet_go()  PK_TOPOL_render_facet（GO 回调兜底）
        +- body_faces()/edges()/vertices()  PK_BODY_ask_faces/_edges/_vertices
        |     +- vertex_point()  PK_VERTEX_ask_point -> PK_POINT_ask
        +- 编辑（boolean/transform/delete）  PK_BODY_boolean_2 / PK_BODY_transform_2 / PK_FACE_delete_2
        +- transmit_parts()      PK_PART_transmit -> 捕获 x_t bytes（§2 写回）

---

## 4. 关键逆向技巧

### 4.1 V37 与 V35 的核心差异

| 项 | V35（公开文档） | V37（本内核实测） |
|---|---|---|
| PK_TRANSF_t | 4x4 double 矩阵 | 32 位 tag（由 PK_TRANSF_create_* 返回） |
| PK_BODY_transform_2 签名 | (body, matrix, tol, opts, track, res) | (body, transf_tag, tol, opts, track, res) |
| PK_PART_receive 返回 | part tag | body tag（本内核） |
| PK_PART_transmit_o_t 字段数 | V35 7 字段（曾误改） | 6 字段（见 §5） |
| PK_TOPOL_facet_2_o_t 表顺序 | point_vec/normal_vec 在 data_curv_idx 之后 | 在其之前（见 §6.1） |

> 曾把 _Transmit 误改成 V35 的 7 字段导致 transmit 失败；V35 矩阵当 V37 tag 传给
> PK_BODY_transform_2 会抛 963 PK_ERROR_bad_component（perspective）或直接访问违规。

### 4.2 PK_TRANSF_t 是 32 位 tag（不是矩阵）

变换一律先创建 tag 再按值应用：

      tag = c_int(0)
      pk.PK_TRANSF_create_translation(disp, byref(tag))
      pk.PK_TRANSF_create_rotation(pos, axis, angle, byref(tag))
      pk.PK_TRANSF_create_reflection(pos, normal, byref(tag))
      pk.PK_TRANSF_create_equal_scale(scale, centre, byref(tag))
      pk.PK_BODY_transform_2(body_tag, tag, tol, opts, track, res)

### 4.3 实体类码（PK_ENTITY_ask_class）

| 类码 | 实体 |
|---|---|
| 5006 | body（实体/片体） |
| 5007 | instance |
| 5008 | assembly |

关键坑：PK_BODY_ask_faces 打在 assembly tag 上会原生访问违规；必须先
expand_to_bodies 展开（assembly 递归取 parts，instance 跳过）。

### 4.4 错误码速查

| 码 | 常量 | 触发场景 |
|---|---|---|
| 963 | PK_ERROR_bad_component | V35 矩阵当 V37 tag 传给 transform（perspective） |
| 973 | PK_ERROR_file_access_error | transmit 时 FRU 写回调是桩（没捕获输出） |
| 5022 | PK_ERROR_o_t_version_incorrect | struct o_t_version 与内核 schema 不符且未关检查 |
| 5048/5049 | 会话/实体错误 | PK_SESSION_transmit / PK_PARTITION_transmit 对仅含 body 的会话拒绝 |

通用处理：每个入口函数前重设一次 PK_SESSION_set_check_arguments(0)（内核可能复位）。

### 4.5 沙箱安全临时目录

_temp_dir() 用 os.makedirs(tempfile.gettempdir()/prefix+uuid4().hex) 而非
tempfile.mkdtemp——后者创建的目录安全描述符被沙箱拒绝后续写，os.makedirs 的普通目录可写。
（receive_xt 需要落盘 x_t 才能让 FFOPRD 按路径读。）

### 4.6 命名/属性（body_name）

body 名存在 SDL/TYSA_NAME 与 SDL/TYSA_UNAME 属性里，PK_PART_ask_all_attribs +
PK_ATTRIB_ask_string 取字符串（ASCII 过滤 + 取最长）。

### 4.7 顶点坐标（B5 血泪教训）

PK_VERTEX_ask_point 返回的是 PK_POINT_t 实体 tag，不是 double[3]。早期把它当
double[3] 读得到 denormal 垃圾（6.4e-322）。正确链路：

      PK_VERTEX_ask_point(vertex_tag, &point_entity)   # 返回 int tag
      PK_POINT_ask(point_entity, &sf)                  # sf 是 double[3]

---

## 5. 关键 ctypes 结构体（实测布局）

### 5.1 收发选项

      class _Transmit(Structure):          # PK_PART_transmit_o_t（V37，6 字段）
          _fields_ = [
              ("o_t_version", c_int),      # =1
              ("transmit_format", c_int),  # 0=text
              ("transmit_user_fields", c_int),
              ("transmit_nw_version", c_int),
              ("transmit_xmt_file", c_int),
              ("transmit_attr", c_int),
          ]

      class _RECV(Structure):              # PK_PART_receive_o_t（14 字段）
          _fields_ = [
              ("o_t_version", c_int), ("transmit_format", c_int),
              ("receive_user_fields", c_int), ("attdef_mismatch", c_int),
              ("part_index", c_int), ("n_part_indices", c_int),
              ("part_indices", c_void_p), ("n_identifiers", c_int),
              ("identifiers", c_void_p), ("receive_indexed_context", c_void_p),
              ("key_is_partition", c_int), ("receive_compound", c_int),
              ("receive_using_seek", c_int), ("receive_mixed", c_int),
          ]

### 5.2 布尔运算

      class _BooleanOpts(Structure):       # PK_BODY_boolean_o_t（o_t_version=2，15 字段）
          _fields_ = [
              ("o_t_version", c_int), ("function", c_int),
              ("configuration", c_void_p), ("matched_region", c_void_p),
              ("merge_imprinted", c_int), ("prune_in_solid", c_int),
              ("prune_in_void", c_int), ("fence", c_int),
              ("allow_disjoint", c_int), ("selective_merge", c_int),
              ("check_fa", c_int), ("default_tol", c_double),
              ("max_tol", c_double), ("tracking", c_int),
              ("merge_attributes", c_int), ("keep_target_edges", c_int),
          ]
      class _TrackR(Structure):            # PK_body_boolean_track_r_t
          _fields_ = [("n_track_records", c_int), ("track_records", c_void_p),
                      ("internal_origs", c_void_p), ("internal_classes", c_void_p),
                      ("internal_prods", c_void_p)]
      class _BooleanR(Structure):          # PK_body_boolean_r_t
          _fields_ = [("result", c_int), ("n_bodies", c_int), ("bodies", POINTER(c_int)),
                      ("n_reports", c_int), ("reports", c_void_p)]

布尔 token（V35 数值码）：unite=15903、subtract=15902、intersect=15901、
fence_none=18212、check_fa_yes=21801、repair_fa_fa_no=24360。

### 5.3 删除面 / 变换

      class _FaceDeleteOpts(Structure):    # PK_FACE_delete_o_t（o_t_version=1，7 字段）
          _fields_ = [("o_t_version", c_int), ("update", c_int), ("heal_action", c_int),
                      ("heal_loops", c_int), ("local_check", c_int),
                      ("repair_fa_fa", c_int), ("track", c_int)]
      # heal：cap=18081、shrink=18084；update 默认=24330；track_no=26340

      class _TransformOpts(Structure):     # PK_BODY_transform_o_t（4 int）
          _fields_ = [("o_t_version", c_int), ("merge_face", c_int),
                      ("check_fa_fa", c_int), ("update", c_int)]
      # 用法：_TransformOpts(1, 1, 1, 0)

      class _AXIS2(Structure):             # PK_AXIS2_sf_t
          _fields_ = [("location", c_double*3), ("axis", c_double*3),
                      ("ref_direction", c_double*3)]

> PK_BODY_transform_2 的 track/res 用 256 字节 c_byte 缓冲即可，无需精确 _TrackR。

---

## 6. 显示网格（facet）两条路径

### 6.1 PK_TOPOL_facet_2（表解码，主路径）

facet 表 token（base 0x57B2，V37 顺序与 V35 文档不同）：

| token | 表 | 编码 |
|---|---|---|
| 0x57B2 | facet_fin | 8B 记录 {int facet; int fin}，每三角面 3 条连续 fin |
| 0x57B6 | fin_data | int data[fin] |
| 0x57B7 | data_point_idx | int point[data] |
| 0x57BB | point_vec | 24B/条 PK_VECTOR_t（xyz double），坐标 |
| 0x57BC | normal_vec | 同布局，单位法向 |
| 0x57C2 | fin_edge | 8B 记录 {int fin; PK_EDGE_t edge}（本内核非 V35 的 facet_face） |

关键差异：本内核把 point_vec/normal_vec 放在 data_curv_idx 之前（与 V35 头文件
顺序相反）。已三路验证：单 choice 探测、数据语义（0x57BB 存 8 角点）、
ParasolidGW 自己的解码器。

选项结构：PK_TOPOL_facet_2_o_t version 5 = 312 字节 _MeshControlV5 控制块 +
18 个连续字节 choice 标志（偏移 0x138..0x149，CHOICE_OFFSET 表）。option 转换器
（RVA 0x443550）按 version-5 走 22 项跳表。

结果解码：PK_TOPOL_facet_2_r_t.tables[] 每个指针指向 16 字节 wrapper
{qword data_ptr; int length}（PK_TOPOL_fctab_*_t），先 struct.unpack_from("<Qi")
解 wrapper，再按表类型解码：facet_fin 8B 记录（跳过 fin<0 的孔洞分隔）、
fin_data / data_point_idx 4B int 数组、point_vec length*24 字节 -> np.frombuffer("<f8")。
遍历：facet -> fin -> data -> point -> 坐标，取每 facet 前 3 条 fin 组成三角形。

### 6.2 PK_TOPOL_render_facet（GO 回调兜底）

facet2 失败（无表）时走 GO 路径：PK_TOPOL_render_facet 通过 GOSGMT 回调回吐 segment
（facet 段 type=2016，坐标按 ng*3 个 double），收集后组三角形。ps_tessellate.py 也走此路。

### 6.3 自适应细分（facet_body_adaptive）

策略：逐 PK_FACE 以基容差探测，测每面的 facet 数/面积/面内最大二面角；选
角向粗糙且面积够大的面，挂更紧的局部 surface_plane_ang/tol
（PK_facet_local_tolerances_t，5 个 double，0 表示用全局值），最后做一次 body 级 facet_2。
面数 >200 时退回普通 facet_2 防崩溃。
---

## 7. 可挖掘函数清单（1204 个 PK_* 导出按类别）

> 加粗 = 本仓已封装/使用；其余为可继续挖掘的候选。完整清单见
> docs/pskernel_exports.txt，tools/categorize_exports.py 可重新分类。

### 7.1 BODY（136）— 最常用
- 已用：PK_BODY_ask_faces/ask_edges/ask_vertices/ask_topology、PK_BODY_boolean/boolean_2、
  PK_BODY_create_solid_block、PK_BODY_transform/transform_2、PK_BODY_copy_topology。
- 建模（可挖）：PK_BODY_create_solid_cone/cyl/sphere/torus/prism（直接建基本体）、
  PK_BODY_create_sheet_circle/planar/polygon/rectangle（平面片体）、
  PK_BODY_create_topology(_2)、PK_BODY_create_minimum_topology。
- 编辑（可挖）：PK_BODY_sew_bodies、PK_BODY_make_compound、PK_BODY_disjoin、PK_BODY_knit、
  PK_BODY_thicken(_2/_3)、PK_BODY_hollow(_2)、PK_BODY_offset(_2)、PK_BODY_taper、
  PK_BODY_sweep、PK_BODY_spin、PK_BODY_extrude、PK_BODY_fill_hole、PK_BODY_emboss、
  PK_BODY_enlarge、PK_BODY_simplify_geom、PK_BODY_slice、PK_BODY_fix_blends、
  PK_BODY_reverse_orientation、PK_BODY_imprint_*（压印）、PK_BODY_make_swept/lofted_body、
  PK_BODY_make_facet_body（body->facet 方向，非三角->实体）、
  PK_BODY_is_cellular/is_disjoint、PK_BODY_ask_components/regions/shells/fins。
- 推荐：Wrap 非凸包化、Sheet/Shell 重建、孔洞填充。

### 7.2 FACE（110）
- 已用：PK_FACE_delete/delete_2、PK_FACE_boolean(_2)、PK_FACE_ask_*（经 facet 反推平面）。
- 可挖：PK_FACE_make_solid_bodies/make_sheet_bodies/make_sheet_body（三角面->实体/片体的
  mesh->B-rep 关键，Simplify 出 x_t 的长期项）、PK_FACE_make_neutral_sheet(_2)、
  PK_FACE_euler_*（Euler 算子建环/面）、PK_FACE_cover、PK_FACE_offset(_2)、PK_FACE_taper、
  PK_FACE_sweep、PK_FACE_spin、PK_FACE_imprint_*、PK_FACE_make_blend、
  PK_FACE_identify_blends(_2)、PK_FACE_close_gaps、PK_FACE_replace_surfs(_2/_3)、
  PK_FACE_reverse、PK_FACE_is_coincident。

### 7.3 SESSION（84）
- 已用：PK_SESSION_register_frustrum、PK_SESSION_start、PK_SESSION_set_check_arguments。
- 可挖：PK_SESSION_ask_kernel_version/schema_version（确认 V37 版本号）、
  PK_SESSION_ask_precision/set_precision、PK_SESSION_ask_journalling/set_journalling、
  PK_SESSION_abort、PK_SESSION_ask_memory_usage、PK_SESSION_ask_tags_remaining/tag_highest/tag_limit、
  PK_SESSION_ask_err_reports、PK_SESSION_ask_facet_geometry/set_facet_geometry、
  PK_SESSION_ask_smp/ask_max_threads（并行）、PK_SESSION_receive/receive_u（整会话接收）。

### 7.4 TRANSF（16）— 全部可挖
- 已用：PK_TRANSF_create_translation/rotation/reflection/equal_scale。
- 可挖：PK_TRANSF_create（复合 4x4->tag，把 XML 列主序矩阵直接转内核 tag）、
  PK_TRANSF_create_view、PK_TRANSF_ask（tag->矩阵）、PK_TRANSF_classify、
  PK_TRANSF_is_equal、PK_TRANSF_transform(_2)、PK_TRANSF_enlarge。
- 推荐：PK_TRANSF_create 可让 XML transform -> 真实 body 直接复用现有 16 值矩阵。

### 7.5 ENTITY（29）
- 已用：PK_ENTITY_ask_class、PK_ENTITY_copy。
- 可挖：PK_ENTITY_delete（释放临时 body，当前靠会话结束回收）、PK_ENTITY_ask_identifier、
  PK_ENTITY_ask_user_field/set_user_field、PK_ENTITY_range(_vector)、
  PK_ENTITY_is/is_geom/is_topol/is_surf/is_curve/is_part、PK_ENTITY_copy_2（带引用计数）。

### 7.6 VERTEX / EDGE / FIN / LOOP / REGION / SHELL（拓扑遍历）
- 已用：PK_VERTEX_ask_point、PK_POINT_ask、PK_BODY_ask_edges。
- 可挖：PK_VERTEX_ask_faces/ask_oriented_edges、PK_EDGE_ask_geometry/ask_vertices、
  PK_FIN_ask_geometry/ask_curve/ask_edge（B5 曾建议用 PK_EDGE_ask_geometry 取端点）、
  PK_LOOP_ask_*、PK_REGION_make_solid/make_void、PK_SHELL_ask_*。
- 推荐：PK_EDGE_ask_geometry 是边几何的更稳入口，比 vertex->point 链路更完整。

### 7.7 GEOM / CURVE / SURF（几何）
- 可挖：PK_GEOM_transform(_2)、PK_GEOM_range(_vector)、PK_GEOM_copy、PK_CURVE_ask_*、
  PK_SURF_ask_*、PK_BODY_ask_config。
- 推荐：XML transform 改走 PK_GEOM_transform 时，几何实体（曲线/曲面）也能一起变。

### 7.8 MESH / MFACET / MFIN / MVERTEX / MTOPOL（facet 网格拓扑）
- 可挖：PK_MESH_create_from_facets、PK_MESH_make_bodies（facet mesh->body 另一入口）、
  PK_MESH_fill_holes、PK_MESH_find_defects/fix_defects、PK_MESH_find_sharp_mfins、
  PK_MFACET_ask_positions/ask_normal、PK_MFIN_ask_mfacet、PK_MVERTEX_ask_position。
- 推荐：PK_MESH_make_bodies 与 PK_FACE_make_solid_bodies 是 Simplify/STL->x_t 的两条候选路线。

#### 7.8.1 PK_MESH_create_from_facets V37 实测 ABI（disasm 0x369270/0x368670 + V35 文档交叉验证）

本内核（Cradle 2025.2 pskernel = Parasolid V37）的 mesh 创建 ABI 与 V35 头文件
基本一致，但多个枚举值是 token 而非 0/1，全部通过探针实测：

```c
PK_MESH_create_from_facets(facet_reader, context, options, mesh)
// rcx=回调, rdx=context, r8=options*, r9=mesh out（写 *mesh=0 起步）
```

- **前置**：`PK_SESSION_set_facet_geometry(0x64E7)` = PK_facet_geometry_all_c
  （no_c=0x64E6；不设置则 create_from_facets 在 frustra 状态字节 +0x48 关卡处返回
  **5237**，回调永不触发）。会话查询 `PK_SESSION_ask_facet_geometry` 返回当前 token。
- **options V2 布局**：`{int o_t_version; int vertices_estimate; int facets_estimate;
  void *facet_free; int create; int have_box; PK_BOX_t box; int thread_safe}`。
  `create` 只接受 **0x6784 = PK_MESH_create_now_c / 0x6785 =
  PK_MESH_create_later_c**（内核 0x368b78 处 `sub ecx,0x6784; je/cmp 1` 校验）。
  o_t_version=1 时只读 +4/+8/+0x10 三字段，其余用默认值。
- **回调签名**（3 参、void 返回）：
  `void cb(void *context, PK_MESH_facet_t *facets, int *status)`；
  facet 结构 = `{int facet_type; int pad; union{void*} }`。
- **facet_type（V37 有 6 种，disasm 0x13ce262 起的 switch）**：
  **5 = index 块**、6 = vector 块、1/2/3/4 = 其它块种（strip/fan 等）。
  index 块布局（实测与 0x13ce26b 读取一致）：
  `{int is_relative_index; int n_vertex_positions; PK_VECTOR_t *vertex_positions;
    PK_VECTOR_t *vertex_normals; int n_facet_indices; int *facet_indices}`
  （PK_VECTOR_t=24 字节，引擎 0x13ce2db 以 24 字节步长读顶点）。
- **回调 status 是 token 不是 0/1**（disasm 0x13ce225 `test eax,0xfffffffd` 与
  0x13ceb4c `cmp 0x187a6`）：**0x187a4 = continue、0x187a6 = stop、
  0x187a8 = memory_full**；0x187a5 非法（会走失败出口）。
- **引擎内部流程**（0x13ce100 状态机）：kernel 先把 reader/context/facet_free 存入
  全局注册 trampoline（0x13c7720 → 全局 0x3191250/0x3191258），引擎经 trampoline
  回调用户 reader；每块消费后调 facet_free；stop 后 0x13c69c0 finalize 建实体。
- **当前状态**：create_later（0x6785）返回 rc=0 + 合法 mesh tag（实体只存
  {reader,context,facet_free,预估} 供延迟加载）；create_now（0x6784）回调触发、
  块被消费，但 finalize 返回 **5241（0x1479，引擎 status 3 = 无有效 facet）**——
  这是下一步要解的最后一个点（候选：会话 mesh_angle 模式、finalize 的 arg3/法向
  分支、或块数据一致性要求）。未物化的 lazy mesh 上 PK_MESH_make_bodies 返回 907，
  PK_MESH_ask_n_mfacets 强制加载会崩溃（access violation），不要直接调用。
- 完整可运行探针：`tools/mesh_create_probe.py`（含所有 struct/回调定义）。

### 7.9 其余类别（按数量）
EDGE(67)、PARTITION(56)、CURVE(54)、TOPOL(42，含 PK_TOPOL_facet_2 已用)、LATTICE(41)、
SURF(41)、ATTRIB(38，PK_ATTRIB_ask_string 已用)、BCURVE(30)、PART(28，PK_PART_receive/
transmit/ask_all_attribs 已用)、THREAD(26)、BSURF(22)、DEBUG(18)、MARK(18)、GROUP(15)、
ATTDEF(14)、PMARK(11)、FRAME(10)、LBALL(10)、REPORT(10)、VECTOR(9，PK_VECTOR_* 平面/法向运算)、
ASSEMBLY(8，PK_ASSEMBLY_ask_parts 已用)、BB(7)、MEMORY(7)、SHELL(7)、ERROR(6)、LTOPOL(6)、
POINT(6，PK_POINT_ask 已用)、APPITEM(5)、INSTANCE(5)、MTOPOL(5)、LROD(4)、
基本几何 CONE/CYL/SPHERE/TORUS(各3)、LINE/CIRCLE/ELLIPSE/PLANE(各2)、SPUN/SWEPT(各2) 等。

---

## 8. 调用范式（复制即用）

      # 1) 每个入口前关参数检查（幂等）
      pk.PK_SESSION_set_check_arguments.restype = c_int
      pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
      pk.PK_SESSION_set_check_arguments(0)

      # 2) 声明返回类型 + 参数类型（ctypes 强类型，防 ABI 错误）
      pk.PK_BODY_ask_faces.restype = c_int
      pk.PK_BODY_ask_faces.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p)]
      n = c_int(0); faces = c_void_p()
      rc = pk.PK_BODY_ask_faces(tag, byref(n), byref(faces))
      # 3) 解包变长数组：cast(ptr, POINTER(c_int * n.value)).contents

      # 4) 结构体清零 + 设 o_t_version，避免残留脏数据
      opts = _BooleanOpts(); memset(byref(opts), 0, sizeof(opts)); opts.o_t_version = 2

通用纪律：
- 每个函数单独设 restype/argtypes（内核不做运行时类型检查，一旦设错静默损坏）；
- 结构体用 memset 清零再填，o_t_version 必须匹配逆向出的版本；
- 变长输出数组一律 cast(ptr, POINTER(c_int * n)).contents 解包，用前判 n>0 且 ptr 非空；
- body tag 上的 PK_BODY_* 调用前先 expand_to_bodies（assembly 会访问违规）；
- 坐标单位一律米（Parasolid 内核单位），GUI 侧 mm 需 x1000 换算。

---

## 9. 网络资源与 V35 公开文档对照（精确 ABI 参考）

Parasolid V35 文档公开在 q-solid.com。⚠️ 注意：Cradle 2025.2 内核可能高于 V35，
函数签名/枚举 token 基本可信，**结构体布局仍需黑盒校准**（本项目已对
PK_BODY_boolean_2 o_t=2、PK_TOPOL_facet_2 v5 这样验证过，见 §4.1、§5）。

| 资源 | URL | 用途 |
|---|---|---|
| 头文件 | http://www.q-solid.com/Parasolid_Docs_V35/headers/pk_*.html | 每个 _o_t / _r_t 结构体精确字段布局（ABI 骨架） |
| 函数描述 PDF | http://www.q-solid.com/Parasolid_Docs_V35/pdf/fd.pdf | 函数参考手册全集（函数描述、参数语义） |
| 函数章节 | http://www.q-solid.com/Parasolid_Docs_V35/chapters/fd_chap.*.html | 函数描述（分章节 HTML，便于单函数查阅） |
| x_t 流格式 | http://www.q-solid.com/Parasolid_Docs_V35/chapters/xt_chap.02.html | x_t 传输流格式（对应 PK_PART_receive / PK_PART_transmit） |

常用头文件速查（与 §7 已封装/可挖函数一一对应）：
- pk_vertex_ask_point.html —— PK_VERTEX_ask_point / PK_POINT_t 语义（§4.7 坑）
- pk_body_boolean_2.html —— PK_BODY_boolean_2_o_t / _r_t（§5.2）
- pk_transf_create.html —— PK_TRANSF_create / PK_TRANSF_t 表示（注意 V37 是 32 位 tag）
- pk_body_transform_2.html —— PK_BODY_transform_o_t（§5.3）
- pk_face_delete_2.html —— PK_FACE_delete_o_t（§5.3）
- pk_topol_facet_2.html —— PK_TOPOL_facet_2_o_t / 表 token（§6.1）
- pk_part_receive.html / pk_part_transmit.html —— PK_PART_receive_o_t / transmit_o_t（§5.1）

x_t 流格式（xt_chap.02.html）与本仓数据流的对应：
- receive_xt：PK_PART_receive 按文本/二进制流解析，FFOPRD/FFREAD 逐行（文本）或裸读（二进制 .s_t）
- transmit_parts：PK_PART_transmit 生成文本 .x_t，经 FFOPWR/FFWRIT/FFCLOS 捕获（§2）

黑盒校准清单（V37 与 V35 差异，务必实测）：
1. PK_TRANSF_t 是 32 位 tag（V35 是 4x4 double 矩阵）
2. PK_PART_transmit_o_t 是 6 字段（曾照 V35 误改 7 字段）
3. PK_BODY_boolean_o_t o_t_version=2
4. PK_TOPOL_facet_2_o_t version 5 表顺序 point_vec/normal_vec 在 data_curv_idx 之前
5. PK_PART_receive 返回 body tag（非 V35 的 part tag）

---

## 10. 已知坑清单（速查）

1. PK_VERTEX_ask_point 返回 tag 不是 double[3]（-> PK_POINT_ask）。
2. PK_TRANSF_t 是 32 位 tag，不是 V35 的 4x4 矩阵（-> PK_TRANSF_create_*）。
3. _Transmit 是 6 字段（勿照 V35 改 7 字段）。
4. assembly tag 上 PK_BODY_ask_faces 访问违规（-> 先 expand_to_bodies）。
5. transmit 依赖 FRU 写回调捕获输出（桩回调 -> 973）。
6. 关参数检查必须每个入口重设一次。
7. facet 表 point_vec/normal_vec 在 data_curv_idx 前（V37 顺序）。
8. tempfile.mkdtemp 目录在沙箱下不可写（-> os.makedirs）。
9. PK_PART_receive 本内核返回 body tag（非 V35 的 part tag）。
10. PK_PART_add_geoms 只加构造几何（点/曲线/曲面/lattice），不能加 body；独立 body
    （如 boolean 结果）没有 owning part，transmit 需走 body 路径兜底 STL。
