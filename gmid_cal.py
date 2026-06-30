import math
import io
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from scipy.io import loadmat
from dataclasses import dataclass
import plotly.graph_objects as go
import plotly.colors
# 设置网页宽屏并注入自定义 CSS
st.set_page_config(layout="wide", page_title="gm/Id Calculator")
# 注入 JS 禁用下拉选择框的手机虚拟键盘并实现纯选择
components.html(
    """
    <script>
    const parentDoc = window.parent.document;
    function preventKeyboard() {
        const inputs = parentDoc.querySelectorAll('div[data-baseweb="select"] input');
        inputs.forEach(input => {
            if (input && !input.readOnly) {
                input.readOnly = true;
                input.setAttribute('inputmode', 'none');
                input.style.cursor = 'pointer';
                input.style.caretColor = 'transparent';
            }
        });
    }
    preventKeyboard();
    setInterval(preventKeyboard, 500);
    </script>
    """,
    height=0,
    width=0
)
st.markdown("""
<style>
    /* 极致压缩网页全局顶部与底部留白 */
    .block-container { padding-top: 3.2rem; padding-bottom: 0rem; }
    
    /* 缩小垂直组件之间的间距 */
    div[data-testid="stVerticalBlock"] { gap: 0.3rem; }
  
    /* 限制多选框的高度，超过两行自动显示滚动条 */
    .stMultiSelect div[data-baseweb="select"] > div:first-child {
        max-height: 85px; 
        overflow-y: auto;
    }
    
    /* 微调 L 按钮专属样式：超美观、圆形、现代扁平风格 */
    div[class*="dec_l"] button,
    div[class*="inc_l"] button {
        padding: 0px !important;
        height: 24px !important;
        min-height: 24px !important;
        width: 24px !important;
        min-width: 24px !important;
        font-size: 14px !important;
        font-weight: 400 !important;
        line-height: 22px !important;
        border-radius: 50% !important; /* 圆形按钮 */
        border: 1px solid #e5e7eb !important;
        background-color: #f9fafb !important;
        color: #4b5563 !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        margin-top: 32px !important; /* 刚好垂直居中对齐 38px 的输入框 */
        transition: all 0.2s ease-in-out !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
    }
    
    div[class*="dec_l"] button:hover,
    div[class*="inc_l"] button:hover {
        border-color: #3b82f6 !important;
        color: #3b82f6 !important;
        background-color: #eff6ff !important;
        box-shadow: 0 2px 4px rgba(59, 130, 246, 0.15) !important;
    }
    
    div[class*="dec_l"] button:active,
    div[class*="inc_l"] button:active {
        background-color: #dbeafe !important;
        transform: scale(0.95) !important;
    }
</style>
""", unsafe_allow_html=True)
def vector(value: np.ndarray) -> np.ndarray:
    return np.asarray(value, dtype=float).reshape(-1)
def interp1(x: np.ndarray, y: np.ndarray, target: float, *, extrapolate: bool = False) -> float:
    x = vector(x)
    y = vector(y)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if x.size < 2: raise ValueError("not enough interpolation points")
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    unique_x, unique_idx = np.unique(x, return_index=True)
    unique_y = y[unique_idx]
    if not extrapolate and not (unique_x[0] <= target <= unique_x[-1]):
        raise ValueError("input is out of range")
    return float(np.interp(target, unique_x, unique_y))
def monotonic_clean(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = vector(x)
    y = vector(y)
    if x.size < 2: return x, y
    increasing = x[-1] > x[0]
    keep = np.ones(x.shape, dtype=bool)
    current = x[0]
    for i in range(1, x.size):
        if increasing:
            if x[i] > current: current = x[i]
            else: keep[i] = False
        else:
            if x[i] < current: current = x[i]
            else: keep[i] = False
    return x[keep], y[keep]
@dataclass
class DeviceResult:
    id_w: float
    gm_id: float    
    vdsat: float
    vgs_vth: float
    gm_gds: float
    ft_ghz: float    
    cdd_cgg: float
    cgd_cgg: float
    def summary(self) -> str:
        # 不管什么模式，永远强制输出全部 8 个参数
        return "\n".join([
            f"Id/W = {self.id_w:.6g} A/m",
            f"gm/Id = {self.gm_id:.6g} S/A",
            f"Vdsat = {self.vdsat:.6g} V",
            f"Vgs-Vth = {self.vgs_vth:.6g} V",
            f"gm/gds = {self.gm_gds:.6g}",
            f"ft = {self.ft_ghz:.6g} GHz",
            f"Cdd/Cgg = {self.cdd_cgg:.6g}",
            f"Cgd/Cgg = {self.cgd_cgg:.6g}",
        ])
class GmIdData:
    def __init__(self, mat_file) -> None:
        raw = loadmat(mat_file, squeeze_me=False)
        self.data = {k: np.asarray(v, dtype=float) for k, v in raw.items() if not k.startswith("__")}
        self.l = vector(self.data["L"])
        self.vds = vector(self.data["VDS"])
    def gm_id_range(self, device: str, l_index: int) -> tuple[float, float]:
        x = self.data[f"{device}_gm_Id"][:, l_index]
        return float(np.nanmin(x)), float(np.nanmax(x))
    def vdsat_range(self, device: str, l_index: int) -> tuple[float, float]:
        x = self.data[f"{device}_Vdsat"][:, l_index]
        return float(np.nanmin(x)), float(np.nanmax(x))
    def lookup_by_gm_id(self, device: str, l_index: int, gm_id: float) -> DeviceResult:
        gm_axis = self.data[f"{device}_gm_Id"][:, l_index]
        return DeviceResult(
            id_w=interp1(gm_axis, self.data[f"{device}_Id_W"][:, l_index], gm_id),
            gm_id=gm_id,
            vdsat=interp1(gm_axis, self.data[f"{device}_Vdsat"][:, l_index], gm_id),
            vgs_vth=interp1(gm_axis, self.data[f"{device}_Vgs_Vth"][:, l_index], gm_id),
            gm_gds=interp1(gm_axis, self.data[f"{device}_gm_gds"][:, l_index], gm_id),
            ft_ghz=interp1(gm_axis, self.data[f"{device}_ft"][:, l_index], gm_id) / 1e9,           
            cdd_cgg=interp1(gm_axis, self.data[f"{device}_Cdd_Cgg"][:, l_index], gm_id),
            cgd_cgg=interp1(gm_axis, self.data[f"{device}_Cgd_Cgg"][:, l_index], gm_id),
        )
    def lookup_by_vdsat(self, device: str, l_index: int, vdsat: float) -> DeviceResult:
        x_raw = self.data[f"{device}_Vdsat"][:, l_index]
        y_raw = self.data[f"{device}_gm_Id"][:, l_index]
        x_clean, y_clean = monotonic_clean(x_raw, y_raw)
        gm_id = interp1(x_clean, y_clean, vdsat, extrapolate=True)
        return self.lookup_by_gm_id(device, l_index, gm_id)
    def size_from_id(self, device: str, l_index: int, gm_id: float, drain_current_ua: float) -> str:
        result = self.lookup_by_gm_id(device, l_index, gm_id)
        gm_us = gm_id * drain_current_ua
        width_um = drain_current_ua / result.id_w
        cgg_ff = gm_us / (2 * math.pi * result.ft_ghz)
        gds_us = gm_us / result.gm_gds
        cdd_ff = cgg_ff * result.cdd_cgg
        cgd_ff = cgg_ff * result.cgd_cgg
        return "\n".join([
            f"gm = {gm_us:.6g} uS",
            f"Vdsat = {result.vdsat:.6g} V",
            f"W/L = {width_um:.6g} / {self.l[l_index] * 1e6:.6g} um",
            f"gds = {gds_us:.6g} uS",
            f"Cgg = {cgg_ff:.6g} fF",
            f"Cdd = {cdd_ff:.6g} fF",
            f"Cgd = {cgd_ff:.6g} fF",
        ])
plot_choices = [
    ("Id/W - gm/Id", "gm_Id", "Id_W", "gm/Id (S/A)", "Id/W (A/m)"),
    ("gm/gds - gm/Id", "gm_Id", "gm_gds", "gm/Id (S/A)", "gm/gds"),
    ("ft - gm/Id", "gm_Id", "ft", "gm/Id (S/A)", "ft (GHz)"),
    ("Vdsat - gm/Id", "gm_Id", "Vdsat", "gm/Id (S/A)", "Vdsat (V)"),
    ("Cgd/Cgg - gm/Id", "gm_Id", "Cgd_Cgg", "gm/Id (S/A)", "Cgd/Cgg"),
    ("Cdd/Cgg - gm/Id", "gm_Id", "Cdd_Cgg", "gm/Id (S/A)", "Cdd/Cgg"),
    ("Id/W - Vdsat", "Vdsat", "Id_W", "Vdsat (V)", "Id/W (A/m)"),
    ("gm/Id - Vgs-Vth", "Vgs_Vth", "gm_Id", "Vgs-Vth (V)", "gm/Id (S/A)"),
]
@st.cache_resource
def load_data_from_file(uploaded_file):
    return GmIdData(io.BytesIO(uploaded_file.getvalue()))
@st.cache_resource
def load_local_data(path):
    return GmIdData(path)
# ================================
# 左侧边栏 UI
# ================================
st.sidebar.markdown("### 🧮 gm/Id Calculator")
st.sidebar.markdown("---")
data_source = st.sidebar.radio("请选择数据来源：", ("☁️ 云端默认数据", "📁 本地上传数据"))
if data_source == "☁️ 云端默认数据":
    import os
    mat_files = sorted([f for f in os.listdir(".") if f.endswith(".mat")])
    if not mat_files:
        st.sidebar.error("❌ 警告：未检测到任何 .mat 数据文件！")
        st.stop()
    selected_mat_file = st.sidebar.selectbox("请选择云端工艺库文件：", mat_files)
    try: data = load_local_data(selected_mat_file)
    except Exception as e: st.sidebar.error(f"❌ 加载失败: {str(e)}"); st.stop()
else:
    uploaded_file = st.sidebar.file_uploader("请选择 .mat 文件")
    with st.sidebar.expander("📁 上传数据格式说明", expanded=False):
        st.markdown("""
        上传的工艺数据须为 **`.mat`** 格式，其中应包含以下自变量与参数：
        * **自变量网格**：包涵 3 个一维自变量数组 `L`（栅长）、`VDS`（漏源电压）和 `VGS`（栅源电压）。
        * **器件参数矩阵**：包含 NMOS 与 PMOS 两类器件，每类器件对应 8 个二维参数矩阵，其矩阵维度应与扫描网格一致。
        """)
    if uploaded_file is not None: data = load_data_from_file(uploaded_file)
    else: st.sidebar.warning("👈 请先上传文件。"); st.stop() 
l_options = [f"{x * 1e6:.2f} um" for x in data.l]
if "l_index" not in st.session_state or st.session_state["l_index"] >= len(l_options) or st.session_state.get("sidebar_l") not in l_options:
    st.session_state["l_index"] = 0
    default_l = l_options[0]
    st.session_state["sidebar_l"] = default_l
    st.session_state["NCH3_sz_l"] = default_l
    st.session_state["PCH3_sz_l"] = default_l
def update_l_globally(src_key):
    val = st.session_state[src_key]
    idx = l_options.index(val)
    st.session_state["l_index"] = idx
    st.session_state["sidebar_l"] = val
    st.session_state["NCH3_sz_l"] = val
    st.session_state["PCH3_sz_l"] = val
def change_l_by_step(step: int):
    current_idx = st.session_state.get("l_index", 0)
    new_idx = max(0, min(len(l_options) - 1, current_idx + step))
    val = l_options[new_idx]
    st.session_state["l_index"] = new_idx
    st.session_state["sidebar_l"] = val
    st.session_state["NCH3_sz_l"] = val
    st.session_state["PCH3_sz_l"] = val
sb_col1, sb_col2, sb_col3 = st.sidebar.columns([4, 1, 1])
with sb_col1:
    st.selectbox("选择 L", l_options, key="sidebar_l", on_change=update_l_globally, args=("sidebar_l",))
with sb_col2:
    st.button("−", on_click=change_l_by_step, args=(-1,), key="sb_dec_l")
with sb_col3:
    st.button("+", on_click=change_l_by_step, args=(1,), key="sb_inc_l")
l_index = st.session_state["l_index"]
vds_options = [f"{x:.2f} V" for x in data.vds]
vds_index = vds_options.index(st.sidebar.selectbox("选择 Vds", vds_options))
st.sidebar.info(f"🚀 **当前工艺库：**\n`{selected_mat_file if data_source == '☁️ 云端默认数据' else uploaded_file.name}`")
st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style="font-size: 0.75rem; color: #6b7280; line-height: 1.4;">
    <p style="margin-bottom: 0.5rem;">
        🔓 <b>项目开源地址</b>：<br>
        <a href="https://github.com/jahvlen/gmid-cal" target="_blank" style="color: #3b82f6; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">
            <svg height="12" width="12" viewBox="0 0 16 16" fill="currentColor" style="display: inline-block; vertical-align: middle;">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
            </svg>
            jahvlen/gmid-cal
        </a>
    </p>
    <p style="margin-top: 0.5rem; font-style: italic;">
        📚 此项目参考了斯坦福大学 <b>EE214</b> 中提到的 gm/Id 设计方法学。
    </p>
</div>
""", unsafe_allow_html=True)
# ================================
# 核心渲染逻辑：嵌套布局 (左侧计算区 vs 右侧画图区)
# ================================
def render_device_row(device_code, device_name):
    
    # 整体先分为【左侧大区】和【右侧画图大区】，比例可以微调
    col_left, col_plot = st.columns([1, 1.3])
    
    with col_left:
        # 1. 标题直接放在左侧大区的顶端
        st.subheader(f"🖥️ {device_name}", divider="blue")
        
        # 2. 在左侧大区内部，再一分为二（查表 和 计算）
        col_lookup, col_size = st.columns([1, 1])
        
        # --- 查表模块 ---
        with col_lookup:
            gm_key = f"{device_code}_saved_gm"
            vdsat_key = f"{device_code}_saved_vdsat"
            if gm_key not in st.session_state: st.session_state[gm_key] = 10.0
            if vdsat_key not in st.session_state: st.session_state[vdsat_key] = 0.20
            c_radio, c_input = st.columns([1.3, 1])
            with c_radio:
                lookup_mode = st.radio("查询模式", ["gm/Id", "Vdsat"], horizontal=True, key=f"{device_code}_mode")
            
            with c_input:
                try:
                    if lookup_mode == "gm/Id":
                        val = st.number_input("输入 gm/Id", value=st.session_state[gm_key], step=1.0, key=f"{device_code}_temp_gm")
                        st.session_state[gm_key] = val
                        res = data.lookup_by_gm_id(device_code, l_index, val)
                    else:
                        val = st.number_input("输入 Vdsat", value=st.session_state[vdsat_key], step=0.05, key=f"{device_code}_temp_vdsat")
                        st.session_state[vdsat_key] = val
                        res = data.lookup_by_vdsat(device_code, l_index, val)
                except Exception as e:
                    st.error(str(e))
                    res = None
            if res:
                # 💡 在这里去掉了参数，直接调用 summary()
                st.code(res.summary())
        # --- 尺寸计算模块 ---
        with col_size:
            c_sl, c_sid = st.columns([1.3, 1])
            with c_sl:
                c_sel_inner, c_dec_inner, c_inc_inner = st.columns([5, 1, 1])
                with c_sel_inner:
                    st.selectbox("栅长 L", l_options, key=f"{device_code}_sz_l", on_change=update_l_globally, args=(f"{device_code}_sz_l",))
                with c_dec_inner:
                    st.button("−", on_click=change_l_by_step, args=(-1,), key=f"{device_code}_dec_l")
                with c_inc_inner:
                    st.button("+", on_click=change_l_by_step, args=(1,), key=f"{device_code}_inc_l")
            with c_sid:
                size_id = st.number_input("目标 Id (uA)", value=10.0, step=1.0, key=f"{device_code}_sz_id")
                
            try:
                if res is not None:
                    size_res = data.size_from_id(device_code, l_index, res.gm_id, size_id)
                    st.code(size_res)
                else:
                    st.warning("⚠️ 请在左侧输入/计算有效的 gm/Id 或 Vdsat")
            except Exception as e:
                st.error(str(e))
    # --- 3. 右侧画图大区 ---
    with col_plot:
        st.markdown("<div style='height: 0px;'></div>", unsafe_allow_html=True)
        pc1, pc2, pc3 = st.columns([1, 0.8, 3.5])
        pc1, pc2, pc_log, pc3 = st.columns([1.1, 0.8, 0.6, 3])
        plot_name = pc1.selectbox("选择图表", [x[0] for x in plot_choices], key=f"{device_code}_plot", label_visibility="collapsed")
        
        l_filter_mode = pc2.selectbox(
            "L曲线过滤", 
            ["全部 L", "仅当前 L", "较小 L", "较大 L", "稀疏 L", "自定义"], 
            key=f"{device_code}_l_mode", 
            label_visibility="collapsed"
        )
        
        with pc_log:
            log_y = st.checkbox("Log Y", key=f"{device_code}_log_y")
            
        total_l = len(data.l)
        custom_indices = []
        if l_filter_mode == "自定义":
            selected_ls = pc3.multiselect("选几个想看的L", l_options, default=[l_options[0], l_options[-1]], key=f"{device_code}_custom_l", label_visibility="collapsed")
            custom_indices = [l_options.index(x) for x in selected_ls]
        
        if l_filter_mode == "全部 L": indices = range(total_l)
        elif l_filter_mode == "仅当前 L": indices = [l_index]
        elif l_filter_mode == "较小 L": indices = range(total_l // 2)
        elif l_filter_mode == "较大 L": indices = range(total_l // 2, total_l)
        elif l_filter_mode == "稀疏 L": indices = range(0, total_l, max(1, total_l // 5))
        else: indices = custom_indices
        choice = next(x for x in plot_choices if x[0] == plot_name)
        _, x_key, y_key, x_label, y_label = choice
        real_x_key, real_y_key = f"{device_code}_{x_key}", f"{device_code}_{y_key}"
        fig = go.Figure()
        palette = plotly.colors.qualitative.D3 
        colors = [palette[k % len(palette)] for k in range(len(indices))]
        for color, i in zip(colors, indices):
            l_val = data.l[i]
            y_data = data.data[real_y_key][:, i]
            if real_y_key.endswith("_ft"): y_data = y_data / 1e9
                
            fig.add_trace(go.Scatter(
                x=data.data[real_x_key][:, i], y=y_data, mode='lines',
                name=f"{l_val * 1e6:.2f} um", line=dict(color=color, width=2.5), 
                hovertemplate=f"L={l_val * 1e6:.2f} um : %{{y:.2f}}<extra></extra>"
            ))
        
        fig.update_layout(
            xaxis_title=x_label, yaxis_title=y_label, hovermode="x unified",
            height=400, 
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(
                orientation="v", yanchor="top", y=1, xanchor="left", x=1.01,
                font=dict(size=10), bgcolor='rgba(255,255,255,0.5)'
            )
        )
        if log_y:
            fig.update_layout(yaxis_type="log")
        st.plotly_chart(fig, use_container_width=True)
# ================================
# 页面执行
# ================================
render_device_row("NCH3", "NMOS")
render_device_row("PCH3", "PMOS")