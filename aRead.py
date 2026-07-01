from pathlib import Path
import re
import numpy as np
import h5py

# 定义输入 CSV 文件的文件夹路径和输出的 HDF5 文件路径
FOLDER_PATH = Path("./x")
OUTPUT_FILE = Path("m33.h5")

# 匹配浮点数（包括可选的正负号、小数点以及科学计数法 e/E）的正则表达式
FLOAT_PATTERN = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def numbers_in_line(line: str) -> list[float]:
    """提取单行文本中的所有数值，并将其转换为浮点数列表。"""
    return [float(x) for x in FLOAT_PATTERN.findall(line)]


def parse_numeric_line(line: str) -> list[float]:
    """
    解析只包含数值和空格的数据行。

    表头或描述行一般包含变量名（如 Vgs, Vds, OS(...)），此时返回空列表 []。
    数据行则仅包含浮点数值和空白字符。
    """
    stripped = line.strip()
    if not stripped:
        return []

    # 检查这一行是否只包含数字、小数点、科学计数符号、正负号以及空白字符
    if re.fullmatch(r"[\s+\-.0-9eE]+", stripped) is None:
        return []

    return numbers_in_line(stripped)


def parse_csv(file_path: Path) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    通用的多维仿真数据解析器。
    
    能够识别块头部标签（如 L=xxx, Vds=xxx, Vsb=xxx）以及列标题（如 Vds 0.1 0.5 1.0），
    并将所有分散的数据点重构成完整的 4D 数组，其维度顺序为: (VGS, VDS, L, VSB)。
    """
    # 提取头部声明参数的正则表达式
    L_PATTERN = re.compile(r"\bL\s*=\s*([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)", re.IGNORECASE)
    VDS_PATTERN = re.compile(r"\bVds\s*=\s*([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)", re.IGNORECASE)
    VSB_PATTERN = re.compile(r"\bVsb\s*=\s*([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)", re.IGNORECASE)

    current_L = 0.0
    current_Vds = 0.0
    current_Vsb = 0.0
    
    col_var = None          # 标记哪一个变量是作为各列的自变量（L、Vds 或 Vsb）
    column_values = []      # 存储各列对应的自变量坐标值
    data_points = []        # 存放临时解析出的元组: (vgs, vds, l, vsb, value)

    with file_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue

            # 1. 匹配块头部的参数声明（按物理扫描维度从外层到内层：Vsb -> Vds -> L）
            vsb_match = VSB_PATTERN.search(line_str)
            if vsb_match:
                current_Vsb = float(vsb_match.group(1))
                continue

            vds_match = VDS_PATTERN.search(line_str)
            if vds_match:
                current_Vds = float(vds_match.group(1))
                continue

            l_match = L_PATTERN.search(line_str)
            if l_match:
                current_L = float(l_match.group(1))
                continue

            # 2. 匹配列标题行（例如: Vds  0.1  0.5  1.0）
            col_header_match = re.match(r"^(L|Vds|Vsb)\s+([\s+\-.0-9eE]+)$", line_str, re.IGNORECASE)
            if col_header_match:
                var_name = col_header_match.group(1).lower()
                if var_name == "l":
                    col_var = "L"
                elif var_name == "vds":
                    col_var = "Vds"
                elif var_name == "vsb":
                    col_var = "Vsb"
                column_values = numbers_in_line(col_header_match.group(2))
                continue

            # 3. 解析数值数据行
            row = parse_numeric_line(line_str)
            if not row:
                continue

            vgs = row[0] # 首列通常是 Vgs 自变量
            for idx, val in enumerate(row[1:]):
                col_val = column_values[idx] if idx < len(column_values) else 0.0
                
                # 组合当前的 4D 自变量坐标 (L, Vds, Vsb)
                coords = {"L": current_L, "Vds": current_Vds, "Vsb": current_Vsb}
                if col_var in coords:
                    coords[col_var] = col_val
                    
                data_points.append((vgs, coords["Vds"], coords["L"], coords["Vsb"], val))

    if not data_points:
        raise ValueError(f"{file_path.name}: 未找到有效的数值数据")

    # 4. 获取各个维度去重并排序后的唯一坐标值列表
    vgs_coords = np.unique([p[0] for p in data_points])
    vds_coords = np.unique([p[1] for p in data_points])
    l_coords = np.unique([p[2] for p in data_points])
    vsb_coords = np.unique([p[3] for p in data_points])

    # 建立自变量坐标值到网格坐标索引的快速映射表
    vgs_map = {val: idx for idx, val in enumerate(vgs_coords)}
    vds_map = {val: idx for idx, val in enumerate(vds_coords)}
    l_map = {val: idx for idx, val in enumerate(l_coords)}
    vsb_map = {val: idx for idx, val in enumerate(vsb_coords)}

    # 5. 构建并填充 4D 数组，形状依次为: (VGS 长度, L 长度, VDS 长度, VSB 长度)
    data_4d = np.zeros((len(vgs_coords), len(l_coords), len(vds_coords), len(vsb_coords)))
    for vgs, vds, l, vsb, val in data_points:
        data_4d[vgs_map[vgs], l_map[l], vds_map[vds], vsb_map[vsb]] = val

    return {"Data": data_4d, "VGS": vgs_coords, "VDS": vds_coords, "L": l_coords, "VSB": vsb_coords}, vgs_coords, vds_coords, l_coords, vsb_coords


def main() -> None:
    # 1. 查找并加载文件夹中的 CSV 数据文件
    csv_files = sorted(FOLDER_PATH.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"在 {FOLDER_PATH} 目录中未找到任何 CSV 文件")

    all_data: dict[str, np.ndarray] = {}
    global_vgs: np.ndarray | None = None
    global_vds: np.ndarray | None = None
    global_vsb: np.ndarray | None = None
    global_l: np.ndarray | None = None

    # 循环遍历每个 CSV，提取其自变量坐标轴及仿真参数数据
    for file_path in csv_files:
        parsed, vgs, vds, l_values, vsb_values = parse_csv(file_path)
        name = file_path.stem
        all_data[name] = parsed["Data"]

        # 直接记录第一个文件的坐标网格作为全局坐标轴（因为所有仿真参数文件共享相同的扫描自变量轴）
        if global_vgs is None:
            global_vgs = vgs
        if global_vds is None:
            global_vds = vds
        if global_l is None:
            global_l = l_values
        if global_vsb is None:
            global_vsb = vsb_values
        
        data_shape = parsed["Data"].shape
        # 对齐打印输出：文件名占16位字符并左对齐，后面的维度数值采用右对齐
        print(f"成功处理数据: {file_path.name:<16}，去列后尺寸: {data_shape[0]:>3} x {data_shape[1]:>2} x {data_shape[2]:>2} x {data_shape[3]:>2}")

    # 合并全局坐标轴
    vgs_axis = global_vgs if global_vgs is not None else np.asarray([])
    vds_axis = global_vds if global_vds is not None else np.asarray([])
    l_axis = global_l if global_l is not None else np.asarray([])
    vsb_axis = global_vsb if global_vsb is not None else np.asarray([0.0])

    # 准备写入 HDF5 的字典，键名为路径，例如 "/VGS", "/Raw/N_cdd", "/N_gm_Id"
    output_hdf5_data = {
        "/VGS": vgs_axis,
        "/VDS": vds_axis,
        "/L": l_axis,
        "/VSB": vsb_axis
    }

    # 2. 计算派生参数 (在 Python 中集中向量化计算)
    # 动态搜集所有仿真参数文件包含的器件前缀 (如 n33_, p33_, n18_ 等)
    prefixes = set()
    for name in all_data.keys():
        match = re.match(r"^(n\d*|p\d*)_", name, re.IGNORECASE)
        if match:
            prefixes.add(match.group(0).lower()) # 统一转小写进行后续匹配

    W = 5.0e-6  # 器件仿真宽度 W = 5u (用于换算单位宽度电流)
    for prefix in sorted(prefixes):
        is_p = prefix.startswith("p")
        target_prefix = "P_" if is_p else "N_"
        
        # 提取并准备原始 4D 数组数据进行计算
        try:
            id_arr = all_data[prefix + "id"]
            gm_arr = all_data[prefix + "gm"]
            cgg_arr = all_data[prefix + "cgg"]
            cdd_arr = all_data[prefix + "cdd"]
            cgd_arr = all_data[prefix + "cgd"]
            gds_arr = all_data[prefix + "gds"]
            vth_arr = all_data[prefix + "vth"]
            vdsat_arr = all_data[prefix + "vdsat"]
        except KeyError as e:
            print(f"警告：未找到原始参数 {e}，跳过该器件的派生计算")
            continue
        
        # 使用 numpy errstate 屏蔽除以 0 以及无效运算的警告
        with np.errstate(divide='ignore', invalid='ignore'):
            # (1) 跨导效率 gm/Id = gm / abs(Id)
            gmid_arr = np.where(id_arr != 0, gm_arr / np.abs(id_arr), 0.0)
            
            # (2) 特征频率 ft = gm / (2 * pi * Cgg)
            ft_arr = np.where(cgg_arr != 0, gm_arr / (2 * np.pi * cgg_arr), 0.0)
            
            # (3) 漏端本征电容比值 Cdd/Cgg
            cdd_cgg_arr = np.where(cgg_arr != 0, cdd_arr / cgg_arr, 0.0)
            
            # (4) 反馈电容比值 Cgd/Cgg = abs(Cgd) / Cgg
            cgd_cgg_arr = np.where(cgg_arr != 0, np.abs(cgd_arr) / cgg_arr, 0.0)
            
            # (5) 饱和压降 Vdsat (取绝对值确保正值表示)
            vdsat_val_arr = np.abs(vdsat_arr)
            
            # (6) 过驱动电压 Vov = Vgs - Vth (NMOS: vgs - vth, PMOS: vth - vgs)
            # 通过 np.newaxis 升维，将一维 vgs 自变量广播为 4D，以对应 4D 数组中 vgs 维度的计算
            vgs_4d = vgs_axis[:, np.newaxis, np.newaxis, np.newaxis]
            if is_p:
                vov_arr = vth_arr - vgs_4d
            else:
                vov_arr = vgs_4d - vth_arr
                
            # (7) 单位宽度漏极电流 Id/W (NMOS: id/W, PMOS: -id/W，确保为正值表示)
            id_w_arr = (-id_arr if is_p else id_arr) / W
            
            # (8) 本征增益 gm/gds = gm * ro
            gmro_arr = np.where(gds_arr != 0, gm_arr / gds_arr, 0.0)
        
        # 将计算出来的派生参数放在最外层（加 N_ 或 P_ 前缀）
        output_hdf5_data[f"/{target_prefix}gm_Id"] = gmid_arr
        output_hdf5_data[f"/{target_prefix}ft"] = ft_arr
        output_hdf5_data[f"/{target_prefix}Cdd_Cgg"] = cdd_cgg_arr
        output_hdf5_data[f"/{target_prefix}Cgd_Cgg"] = cgd_cgg_arr
        output_hdf5_data[f"/{target_prefix}Vdsat"] = vdsat_val_arr
        output_hdf5_data[f"/{target_prefix}Vgs_Vth"] = vov_arr
        output_hdf5_data[f"/{target_prefix}Id_W"] = id_w_arr
        output_hdf5_data[f"/{target_prefix}gm_gds"] = gmro_arr

    # 将 40 个原始仿真参数放入 /Raw/ 组中（键名为 /Raw/N_xxx 或 /Raw/P_xxx）
    for name, data_arr in all_data.items():
        match = re.match(r"^(n\d*|p\d*)_(.*)$", name, re.IGNORECASE)
        if match:
            dev_type = "N" if match.group(1).lower().startswith("n") else "P"
            param = match.group(2)
            raw_path = f"/Raw/{dev_type}_{param}"
        else:
            raw_path = f"/Raw/{name}"
            
        output_hdf5_data[raw_path] = data_arr

    print("\n==== 预处理与派生参数计算完成！====")
    
    # 3. 将扁平化组织的数据写入 HDF5 文件
    with h5py.File(OUTPUT_FILE, "w") as f:
        for path, val_arr in output_hdf5_data.items():
            f.create_dataset(path, data=val_arr)

    print("\n==== 扁平化格式转换与打包完成！====")
    print(f"数据已打包并保存至：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
