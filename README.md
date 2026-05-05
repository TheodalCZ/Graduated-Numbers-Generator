# Graduated Numbers Generator for ArcGIS Pro

[![Download Toolbox](https://img.shields.io/badge/⬇%20Download%20Toolbox-.atbx-blue?style=for-the-badge)](https://github.com/TheodalCZ/Graduated-Numbers-Generator/releases/latest)

A geoprocessing toolbox (`.atbx`) for ArcGIS Pro that automates the creation of graduated number map method — a cartographic method where numeric values are visualised directly as styled labels with smooth gradation of size, colour, and font weight.

**IMPORTANT: This toolbox is supported in ArcGIS Pro 3.3 and newer.**

Developed as part of a master's thesis at the Department of Geoinformatics, Palacký University Olomouc (2026).

## About the Tool

ArcGIS Pro has no built-in support for graduated number map. This tool fills that gap by automating the entire workflow — classification, label generation, and advanced typographic styling — through a single parameterized toolbox with 36 parameters organised into five sections:

- **Data Statistics** — field selection and statistical overview
- **Classification & Size** — classification method, number of classes, size range
- **Font Styling** — font family, weight, letter spacing, colour gradients
- **Format & Units** — thousand separator, value scale, label suffix, decimal places, label wrapping
- **Advanced Styling** — label offsets, halo (with gradient), shadow, underline

The tool does not modify the source data. It uses a custom module connected to the Windows registry to read installed system fonts, and generates Arcade expressions for dynamic label formatting.

Sample data for the examples are accessed directly from ArcGIS Portal / ArcGIS Online (no local data download is required).

## Author

**Pavel Sedláček**
- LinkedIn: [linkedin.com/in/pavelsedlacek-1142000cz](https://www.linkedin.com/in/pavelsedlacek-1142000cz)
- Email: [pavel.sedlacek2000@seznam.cz](mailto:pavel.sedlacek2000@seznam.cz)

## About the Thesis

This tool was developed as part of the master's thesis:

> SEDLÁČEK, Pavel. *Automatizace tvorby číselných kartodiagramů v prostředí ArcGIS* (*Automation of Designing Graduated-Number Maps in ArcGIS Environment*). Palacký University Olomouc, Faculty of Science, Department of Geoinformatics, 2026. Supervisor: Mgr. Radek Barvíř, Ph.D.
> 
> Full thesis: https://www.geoinformatics.upol.cz/dprace/magisterske/sedlacek26/

A detailed thesis summary is available in [`docs/thesis-summary.md`](docs/thesis-summary.md).

## Repository Structure

- `toolbox/` — the `.atbx` toolbox file ready to load in ArcGIS Pro
- `src/` — standalone Python scripts `Execution.py` and `Validation.py`
- `docs/` — thesis summary and repository documentation
- `examples/` — sample maps and screenshots of the tool in action
- `sample-data/` — information about the datasets used in the examples

## Tool Interface

<p align="center">
  <strong>Collapsed</strong><br/>
  <img src="examples/screenshots/toolbox_collapsed.png" width="320" alt="Toolbox collapsed"/><br/>
  <em>Tool interface immediately after initialization.</em>
</p>

<p align="center">
  <strong>Expanded</strong><br/>
  <img src="examples/screenshots/toolbox_expanded.png" width="100%" alt="Toolbox expanded"/><br/>
  <em>Example of the fully expanded tool with default parameter values, active gradients, and a selected input layer and attribute.</em>
</p>

## How to Use

1. Open ArcGIS Pro.
2. Load the `.atbx` toolbox from the `toolbox/` folder.
3. Select your layer and numeric attribute field.
4. Configure classification, sizing, and styling parameters.
5. Run the tool — labels are applied directly to the map.

If needed, the source logic is documented in `src/` for reference or modification.

## Example Maps

---

### Germany — Number of Fire Brigades by Federal State

<div align="center">

![Germany - Number of Fire Brigades by Federal State](examples/maps/de.jpg)

This map demonstrates near-default tool settings. The only adjustments were font size scaled to match the map's extent, font family, and text colour — applied for visual consistency across the entire example series.

</div>

---

### Poland — Average Monthly Wages by Voivodeship (2020, PLN)

<div align="center">

![Poland - Average Monthly Wages by Voivodeship (2020, PLN)](examples/maps/pl.jpg)

This map was intentionally produced in English to demonstrate international use cases. It uses the Anglo-Saxon number format (comma as thousands separator, period as decimal). Classification method: Equal Interval with 5 classes. Font colour gradient from white to yellow, with halo effect and text shadow applied to improve legibility of labels on the map field.

</div>

---

### Europe — Number of Airports with an ICAO Code by Country

<div align="center">

![Europe - Number of Airports with an ICAO Code by Country](examples/maps/eu.jpg)

This map uses the **Proportional (Unclassed)** classification method to generate mathematically precise graduated font sizes. A reverse font weight gradient (Bold → Regular) was applied to improve readability of smaller values. The halo effect was also enabled. After generation, labels were converted to graphics using the native ArcGIS Pro *Convert Labels to Graphics* function, allowing manual repositioning of overlapping labels while preserving the exact sizes defined by the tool.

</div>

---

### Czech Republic — Number of Women and Men by Region (2021, thousands)

<div align="center">

![Czech Republic - Number of Women and Men by Region (2021, thousands)](examples/maps/cr.jpg)

This map demonstrates visualising two numeric values per feature simultaneously by running the tool twice on duplicated layers — once for women (pink) and once for men (blue), with colours matching the map title. Classification method: **Manual**, with class boundaries set at intervals of 100,000. Value Scale was set to thousands and Decimal Places After Scale to zero to avoid inappropriate decimal display for person counts.

</div>

---

## Sample Data (ArcGIS Portal)

Sample datasets used in this project are hosted externally in ArcGIS Portal / ArcGIS Online. They are not redistributed in this repository.

Source citation (example dataset used in this repository): **ARCDATA PRAHA, ZÚ, ČSÚ - Kraje (ArcČR 2024), Česká republika, (ArcGIS Online).**

To get working data quickly in ArcGIS Pro:

1. Open the **Catalog** pane and switch to **Portal** (or use [ArcGIS Online](https://www.arcgis.com)).
2. Search for one of the datasets listed in [`sample-data/README.md`](sample-data/README.md) (for example: `Kraje (ArcČR 2024)`).
3. Add the hosted feature layer to your map.
4. Run the toolbox on that layer and select a numeric attribute.

![ArcGIS Portal search example](examples/screenshots/data_examplepng.png)

Example of searching and adding the Czech regional boundary dataset from Portal in ArcGIS Pro.