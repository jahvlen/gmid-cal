from pathlib import Path
import re
import numpy as np
import h5py

FOLDER_PATH = Path("./xx")
OUTPUT_FILE = Path("m33.h5")

FLOAT_PATTERN = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def numbers_in_line(line: str) -> list[float]:
    """Return all numeric tokens in a line."""
    return [float(x) for x in FLOAT_PATTERN.findall(line)]


def matlab_str2num_line(line: str) -> list[float]:
    """
    Approximate MATLAB str2num for these Spectre text exports.

    Header lines contain names such as Vgs, Vds, OS(...), so MATLAB returns [].
    Numeric data rows contain only floats and whitespace.
    """
    stripped = line.strip()
    if not stripped:
        return []

    if re.fullmatch(r"[\s+\-.0-9eE]+", stripped) is None:
        return []

    return numbers_in_line(stripped)


def parse_csv(file_path: Path) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Generic coordinate-based multi-dimensional parser.
    Supports 3D and 4D parameters dynamically.
    """
    L_PATTERN = re.compile(r"\bL\s*=\s*([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)", re.IGNORECASE)
    VDS_PATTERN = re.compile(r"\bVds\s*=\s*([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)", re.IGNORECASE)
    VSB_PATTERN = re.compile(r"\bVsb\s*=\s*([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)", re.IGNORECASE)

    current_L = 0.0
    current_Vds = 0.0
    current_Vsb = 0.0
    
    col_var = None
    column_values = []
    data_points = []

    with file_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue

            # Check block headers
            l_match = L_PATTERN.search(line_str)
            if l_match:
                current_L = float(l_match.group(1))
                continue

            vds_match = VDS_PATTERN.search(line_str)
            if vds_match:
                current_Vds = float(vds_match.group(1))
                continue

            vsb_match = VSB_PATTERN.search(line_str)
            if vsb_match:
                current_Vsb = float(vsb_match.group(1))
                continue

            # Check column headers (starts with L, Vds, or Vsb, followed by numbers)
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

            # Parse data row
            row = matlab_str2num_line(line_str)
            if not row:
                continue

            vgs = row[0]
            for idx, val in enumerate(row[1:]):
                col_val = column_values[idx] if idx < len(column_values) else 0.0
                
                # Combine block coordinates and column coordinate
                coords = {"L": current_L, "Vds": current_Vds, "Vsb": current_Vsb}
                if col_var in coords:
                    coords[col_var] = col_val
                    
                data_points.append((vgs, coords["Vds"], coords["L"], coords["Vsb"], val))

    if not data_points:
        raise ValueError(f"{file_path.name}: found no numeric data")

    # Extract unique coordinates
    vgs_coords = np.unique([p[0] for p in data_points])
    vds_coords = np.unique([p[1] for p in data_points])
    l_coords = np.unique([p[2] for p in data_points])
    vsb_coords = np.unique([p[3] for p in data_points])

    vgs_map = {val: idx for idx, val in enumerate(vgs_coords)}
    vds_map = {val: idx for idx, val in enumerate(vds_coords)}
    l_map = {val: idx for idx, val in enumerate(l_coords)}
    vsb_map = {val: idx for idx, val in enumerate(vsb_coords)}

    # Fill the 4D array: (VGS, VDS, L, VSB)
    data_4d = np.zeros((len(vgs_coords), len(vds_coords), len(l_coords), len(vsb_coords)))
    for vgs, vds, l, vsb, val in data_points:
        data_4d[vgs_map[vgs], vds_map[vds], l_map[l], vsb_map[vsb]] = val

    return {"Data": data_4d, "VGS": vgs_coords, "VDS": vds_coords, "L": l_coords, "VSB": vsb_coords}, vgs_coords, vds_coords, l_coords, vsb_coords


def rename_for_legacy_mat(old_name: str) -> str:
    new_name = re.sub(r"^n\d+_phase2_", "Vds_N_", old_name)
    new_name = re.sub(r"^p\d+_phase2_", "Vds_P_", new_name)
    new_name = re.sub(r"^n\d+_", "N_", new_name)
    new_name = re.sub(r"^p\d+_", "P_", new_name)
    return new_name


def build_output(all_data: dict[str, np.ndarray | dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    out_data: dict[str, np.ndarray] = {}

    for old_name, value in all_data.items():
        new_name = rename_for_legacy_mat(old_name)

        if isinstance(value, dict):
            # 直接保存为 4D 数组，不再扁平化为 2D
            out_data[new_name] = value["Data"]
        else:
            out_data[new_name] = value

    return out_data


def save_hdf5(file_path: Path, data: dict[str, np.ndarray]) -> None:
    with h5py.File(file_path, "w") as f:
        for name, value in data.items():
            f.create_dataset(name, data=value)


def main() -> None:
    csv_files = sorted(FOLDER_PATH.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {FOLDER_PATH}")

    all_data: dict[str, np.ndarray | dict[str, np.ndarray]] = {}
    global_vgs: np.ndarray | None = None
    global_vds: np.ndarray | None = None
    global_vsb: np.ndarray | None = None
    all_l_values: list[np.ndarray] = []
    all_vsb_values: list[np.ndarray] = []

    for file_path in csv_files:
        parsed, vgs, vds, l_values, vsb_values = parse_csv(file_path)
        name = file_path.stem
        all_data[name] = parsed

        if isinstance(parsed, dict):
            if global_vgs is None:
                global_vgs = vgs
            if global_vds is None:
                global_vds = vds
            if global_vsb is None:
                global_vsb = vsb_values
            all_l_values.append(l_values)
            all_vsb_values.append(vsb_values)
            data_shape = parsed["Data"].shape
            print(f"成功处理数据: {file_path.name}，去列后尺寸: {data_shape[0]} x {data_shape[1]} x {data_shape[2]} x {data_shape[3]}")

    all_data["VGS"] = global_vgs if global_vgs is not None else np.asarray([])
    all_data["VDS"] = global_vds if global_vds is not None else np.asarray([])
    all_data["L"] = np.unique(np.concatenate(all_l_values)) if all_l_values else np.asarray([])
    all_data["VSB"] = np.unique(np.concatenate(all_vsb_values)) if all_vsb_values else np.asarray([0.0])

    # 2. 计算派生参数 (由 Python 中心化处理，以提高 Ocean 导出速度)
    W = 5.0e-6  # 器件仿真宽度 W = 5u
    for prefix in ["n33_", "p33_"]:
        is_p = (prefix == "p33_")
        
        # 提取关键自变量
        vgs_val = all_data["VGS"]
        vds_val = all_data["VDS"]
        l_val = all_data["L"]
        vsb_val = all_data["VSB"]
        
        # 提取原始 4D 矩阵数据
        try:
            id_arr = all_data[prefix + "id"]["Data"]
            gm_arr = all_data[prefix + "gm"]["Data"]
            cgg_arr = all_data[prefix + "cgg"]["Data"]
            cdd_arr = all_data[prefix + "cdd"]["Data"]
            cgd_arr = all_data[prefix + "cgd"]["Data"]
            gds_arr = all_data[prefix + "gds"]["Data"]
            vth_arr = all_data[prefix + "vth"]["Data"]
            vdsat_arr = all_data[prefix + "vdsat"]["Data"]
        except KeyError as e:
            print(f"警告：未找到原始参数 {e}，跳过该器件的派生计算")
            continue
        
        # 使用 numpy errstate 避免除以 0 的警告
        with np.errstate(divide='ignore', invalid='ignore'):
            # 1. gm_Id (gm / abs(id))
            gmid_arr = np.where(id_arr != 0, gm_arr / np.abs(id_arr), 0.0)
            
            # 2. Cdd_Cgg (cdd / cgg)
            cdd_cgg_arr = np.where(cgg_arr != 0, cdd_arr / cgg_arr, 0.0)
            
            # 3. Cgd_Cgg (abs(cgd) / cgg)
            cgd_cgg_arr = np.where(cgg_arr != 0, np.abs(cgd_arr) / cgg_arr, 0.0)
            
            # 4. ft (gm / (2 * pi * cgg))
            ft_arr = np.where(cgg_arr != 0, gm_arr / (2 * np.pi * cgg_arr), 0.0)
            
            # 5. Vdsat (取绝对值保证恒正)
            vdsat_val_arr = np.abs(vdsat_arr)
            
            # 6. Vgs_Vth (NMOS: vgs - vth, PMOS: vth - vgs)
            vgs_4d = vgs_val[:, np.newaxis, np.newaxis, np.newaxis]
            if is_p:
                vov_arr = vth_arr - vgs_4d
            else:
                vov_arr = vgs_4d - vth_arr
                
            # 7. Id_W (NMOS: id / W, PMOS: -id / W)
            id_w_arr = (-id_arr if is_p else id_arr) / W
            
            # 8. gm_gds (gm / gds)
            gmro_arr = np.where(gds_arr != 0, gm_arr / gds_arr, 0.0)
        
        # 将计算出的 4D 派生数据存回 all_data 中以保持一致的格式
        all_data[prefix + "gm_Id"] = {"Data": gmid_arr, "VGS": vgs_val, "VDS": vds_val, "L": l_val, "VSB": vsb_val}
        all_data[prefix + "Cdd_Cgg"] = {"Data": cdd_cgg_arr, "VGS": vgs_val, "VDS": vds_val, "L": l_val, "VSB": vsb_val}
        all_data[prefix + "Cgd_Cgg"] = {"Data": cgd_cgg_arr, "VGS": vgs_val, "VDS": vds_val, "L": l_val, "VSB": vsb_val}
        all_data[prefix + "ft"] = {"Data": ft_arr, "VGS": vgs_val, "VDS": vds_val, "L": l_val, "VSB": vsb_val}
        all_data[prefix + "Vdsat"] = {"Data": vdsat_val_arr, "VGS": vgs_val, "VDS": vds_val, "L": l_val, "VSB": vsb_val}
        all_data[prefix + "Vgs_Vth"] = {"Data": vov_arr, "VGS": vgs_val, "VDS": vds_val, "L": l_val, "VSB": vsb_val}
        all_data[prefix + "Id_W"] = {"Data": id_w_arr, "VGS": vgs_val, "VDS": vds_val, "L": l_val, "VSB": vsb_val}
        all_data[prefix + "gm_gds"] = {"Data": gmro_arr, "VGS": vgs_val, "VDS": vds_val, "L": l_val, "VSB": vsb_val}

    print("\n==== 预处理完成！====")

    out_data = build_output(all_data)
    save_hdf5(OUTPUT_FILE, out_data)

    print("\n==== 智能格式转换与打包完成！====")
    print(f"已保存至：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
