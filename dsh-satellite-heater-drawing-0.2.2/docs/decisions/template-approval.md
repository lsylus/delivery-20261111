# B02 模板开发基线与交付审批

用户已接受fix-12及当前PDF字体作为开发基线。当前实施见 [开发决定](B02-development-baseline.md)，原fix-12报告保留于 `docs/reports/archive/B02-fix-12.md`。

原模板DXF、HZ=txt.shx+hzdx.shx、原始材料保持。NotoSansCJKsc-Regular为当前接受的PDF开发渲染效果，暂不追求原PDF完全同字形；这不构成SHX分发授权或CAD字体兼容证明。

技术要求纸面右3/上8mm；引线统一采用short-edge-paper-v1，不再逐代号复刻三个引线，也无另一路引线fallback。图形中心/标注位置继承fix-12的还原位置，原测量不确定度只表示来源，不改变Excel真实毫米几何。

FreeCAD实际结果在 `docs/evidence/B02-development-baseline/freecad/summary.json`，必须保留其失败/限制；AutoCAD兼容性未验证。具名工程审批留到加工交付前，当前 `human-approval.json` 仍pending，不妨碍开发技术验收。默认delivery门槛保留，禁止将development通过当正式加工批准。
