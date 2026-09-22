# Third-party notices

本文件说明本仓库中不由 `world-insight contributors` 以 MIT License 授权的
第三方项目、数据和素材。第三方条款只适用于对应的代码、文件、数据或服务，
不改变本仓库原创代码的 MIT License。

## World Monitor

本项目的产品方向和部分信息组织思路受 [World Monitor](https://github.com/koala73/worldmonitor)
启发，但本仓库不是其官方版本，也不随本仓库重新分发 World Monitor 主项目源代码。
World Monitor 主项目源代码采用 [AGPL-3.0-only](https://github.com/koala73/worldmonitor/blob/main/docs/license.mdx)。
如未来引入其源代码，应重新进行逐文件许可审查，不得仅依据本仓库的 MIT License
重新许可。

## Natural Earth

`web/assets/world-countries.geojson` 来自 Natural Earth vector v5.1.2，具体来源、
哈希和使用边界见 [`web/assets/world-countries.LICENSE.md`](web/assets/world-countries.LICENSE.md)。

## 数据来源

应用可按配置访问下列外部来源。访问权限、署名、保存、展示、导出和再利用范围以
各来源当前条款为准，不由本仓库的 MIT License 扩大：

- [GDELT](https://gdeltproject.org/about.html)：本项目按来源研究记录使用允许的元数据；不取得原新闻全文或图片的再发布许可。
- [Federal Reserve RSS](https://www.federalreserve.gov/feeds/feeds.htm)：按其 RSS 和版权说明使用；第三方内容及标志需单独核对。
- [World Bank WDI](https://datacatalog.worldbank.org/dataset/world-development-indicators)：按数据集及其公开许可说明使用。

## Runtime

运行基线使用 CPython 3.11 标准库、操作系统提供的 `curl` 以及用户浏览器，
不在仓库中打包第三方 Python 或 Node 依赖。运行环境本身的许可不因本文件改变。
