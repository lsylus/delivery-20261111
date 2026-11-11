# 第三方与外部资源

- Python 第三方依赖版本及哈希由 `service/uv.lock` 锁定。离线 wheel 自带
  `.dist-info` 元数据和相应许可；发布二进制时保留 wheel 内容及许可。
- 浏览器 PDF 预览使用 pdfjs-dist。构建会复制 PDF.js 的 LICENSE 到
  `plugin/public/PDFJS-LICENSE.txt`，tgz 已包含该文件。
- Node 开发依赖版本由 `plugin/package-lock.json` 锁定。
- OpenCADStudio、Python 解释器及 HZDX.SHX 字体为外部运行资源，tgz 不包含它们。
  本地 fixtures/case/HZDX.SHX 为工程师原材料副本，已由 Git 忽略。
- 项目尚未指定开源许可证，本次交付没有替权利人选择或添加许可证。
