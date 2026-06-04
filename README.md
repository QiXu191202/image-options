# 图片工具箱

基于 PyQt6 的本地图片处理工具，提供调整尺寸、压缩、长图切割、图片裁剪四项功能，支持拖放操作，界面适配明暗模式。可打包为独立 App / exe。

---

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS / Windows |
| Python | 3.10 及以上（推荐 3.12） |
| 核心依赖 | PyQt6 ≥ 6.4、Pillow ≥ 10.0 |
| 可选依赖 | pyobjc-framework-Cocoa（macOS 修改 Dock 程序名，非必须） |

---

## 目录结构

```
resize-image/
├── main.py          # 入口：主窗口与功能导航
├── resize.py        # 功能模块：调整图片尺寸
├── compress.py      # 功能模块：图片压缩
├── split.py         # 功能模块：长图切割
├── crop.py          # 功能模块：图片裁剪
├── common.py        # 共享组件：工具函数、DropArea、弹窗 helper
├── build_app.py     # 构建脚本：打包为独立 App / exe
├── requirements.txt # 依赖清单
└── static/          # 图标资源（SVG）
    ├── EditImage.svg
    ├── resize.svg
    ├── compress.svg
    ├── split.svg
    └── crop.svg
```

---

## 准备工作

### 1. 克隆或下载项目

```bash
git clone <仓库地址>
cd resize-image
```

### 2. 创建并激活虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

如需在 macOS Dock / 活动监视器中显示「图片工具箱」而非「Python」，额外安装：

```bash
pip install pyobjc-framework-Cocoa
```

### 4. 启动程序

```bash
python main.py
```

---

## 打包为独立程序

使用 PyInstaller 将项目打包为可直接双击运行的 App（macOS）或 exe（Windows），无需 Python 环境。

```bash
# macOS → dist/ImageTools.app
python build_app.py

# Windows → dist/ImageTools.exe（在 Windows 上执行）
python build_app.py
```

打包过程自动安装 PyInstaller 和 cairosvg（图标转换），产物约 225 MB（含 PyQt6 完整框架）。

### 跨平台构建

- **macOS 打包** → `dist/ImageTools.app`，可以直接拖入「应用程序」文件夹使用
- **Windows 打包** → `dist/ImageTools.exe`，单文件，双击运行
- 将项目完整拷贝到目标平台，安装 `PyQt6`、`Pillow` 依赖后运行 `build_app.py` 即可

---

## 功能说明

### 调整图片尺寸

批量将图片缩放至指定宽度，高度按原始比例自动计算。

- 支持拖放或点击选择多张图片（JPG / PNG / WebP / BMP / TIFF）
- 设置目标宽度（px），原图小于目标宽度时不放大
- 输出选项：保存到原目录（可覆盖原图）或指定目录
- 后台线程处理，带进度条，完成后汇报成功/失败数量

### 图片压缩

调节质量参数，在不改变尺寸的前提下减小文件体积。

- 支持拖放或点击选择多张图片
- 质量滑块范围 1 ~ 100；JPEG / WebP 直接控制画质，PNG 为无损格式调节压缩速度
- 表格实时显示原始大小、压缩后大小、压缩率
- 输出选项同上

### 长图切割

将竖向或横向长图沿长边均匀切割为 N 份。

- 每次处理单张图片，拖放后自动读取尺寸
- 按 **4:3**（短边 × 4/3 = 长边分段长度）推算建议切割份数范围，可手动调整
- 最后一份不足 4:3 比例时保留原样输出
- 命名前缀同时作为输出子文件夹名称，切割结果保存到原图同级目录下的 `前缀/` 文件夹
- 文件命名格式：`前缀-1.jpg`、`前缀-2.jpg` …

### 图片裁剪

按比例裁剪图片并自定义输出尺寸。

- 拖入图片后自动按比例（原始比例 / 1:1 / 4:3 / 3:4 / 16:9 / 9:16）初始化裁剪框，支持实时拖动和缩放手柄
- 裁剪框自适应：选定比例后按最大可见区域居中，旋转图片及手柄自适应显示
- 输出尺寸独立控制：支持设置自定义宽高（px），宽度/高度联动锁定比例
- 实时预览：裁剪框尺寸动态显示，输出尺寸自动同步
- 支持放大超出原图范围（灰底标识），方便统一输出尺寸
- 后台线程处理，完成后保存到指定目录

---

## 支持格式

JPG / JPEG · PNG · WebP · BMP · TIFF / TIF

---

## 常见问题

**Q：启动后 Dock 程序名仍显示「Python」？**  
A：安装 `pyobjc-framework-Cocoa` 后重新启动即可（见准备工作第 3 步）。如果使用打包后的 .app 则无需此依赖。

**Q：打包后的 .app / .exe 体积为什么这么大？**  
A：PyQt6 是完整的 GUI 框架，打包时需包含 Qt 运行时库和 SVG 插件，约 225 MB。这是正常体积。

**Q：PNG 压缩后体积没有明显变化？**  
A：PNG 是无损格式，质量滑块仅影响 zlib 压缩等级，压缩幅度有限，不影响画质。

**Q：切割结果文件夹已存在会怎样？**  
A：直接写入该文件夹，同名文件会被覆盖，不会删除其他已有文件。
