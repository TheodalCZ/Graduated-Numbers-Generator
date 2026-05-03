# Thesis Summary

This master thesis deals with the automation of the graduated number map method within the ArcGIS Pro software environment. The main objective of the thesis is to design, develop, and test a tool that streamlines and automates the visualisation process of graduated numeric labels, which previously required tedious manual configuration in this native environment.

The theoretical part summarises the classification of proportional symbol maps and cartographic rules for creating scales and graduated number maps. It also analyses the technological limitations of current GIS software regarding these issues.

The practical part focuses on the development of a tool named **Graduated Numbers Generator** in a geoprocessing toolbox format (`.atbx`). The script is written in Python using the ArcPy library and advanced manipulation of Cartographic Information Model (CIM) objects. For the smooth gradation of visual variables (size, colour, and font weight), a linear interpolation algorithm is implemented. Arcade language expressions are generated for the interpretation and formatting of dynamic labels in the map layout.

A crucial aspect of the designed solution is that it does not modify the source data and uses a custom module connected directly to the Windows registry to read system fonts.

The result of the thesis is a fully functional and portable tool that allows users to easily apply various statistical methods for creating continuous scales. The tool has undergone user testing, and its practical applicability is demonstrated on a series of sample thematic maps. The developed solution significantly reduces the time demands placed on the cartographer and successfully fills a technological gap in the capabilities of the ArcGIS Pro platform.

## Goals

The main objective was to streamline and automate the process of creating graduated number map method in ArcGIS Pro, where this workflow previously required tedious manual configuration. A secondary objective was to develop a custom scripted tool (toolbox) that enables user-friendly creation of graduated number map — not only with smooth gradation of label size, colour, and font weight, but also with more advanced cartographic features.

## Results

- Development of the **Graduated Numbers Generator** tool (`.atbx`) for ArcGIS Pro, containing 36 parameters. With the exception of the first two input fields, the parameters are organised into five thematic sections: *Data Statistics*, *Classification & Size*, *Font Styling*, *Format & Units*, and *Advanced Styling*. This structure allows clear navigation within the tool and enables hiding of parameters not currently needed by the user.
- Creation of a set of 4 sample maps demonstrating the tool's versatility and its ability to work with different datasets, classification methods, and graphic settings (e.g. colour gradients, font weight gradients, and halo effects).

## Methods

The methodology combines a literature review of thematic cartography with iterative software development. First, Czech and international cartographic publications were studied to establish the theoretical basis for graduated number maps, scale construction, and label classification. An analysis of ArcGIS Pro and QGIS revealed that no direct support for this method exists in either platform, which became the primary motivation for building a custom tool.

The tool was developed in Python using the ArcPy library, with Visual Studio Code as the primary editor. Testing was performed on geographically and thematically varied datasets — polygon and point layers covering Czechia, Germany, Poland, and Europe — most of which were sourced from ArcGIS Online. Final user testing was conducted with first-year master's students of the Department of Geoinformatics, Palacký University Olomouc.

The development workflow proceeded in six main phases: literature review → analysis of ArcGIS Pro capabilities → tool design → Python/ArcPy implementation → validation and metadata → user testing and sample map creation.

## Contribution

- A significant simplification and democratisation of the graduated number map workflow, enabling faster and more efficient deployment in real-world cartographic practice.
- A comprehensive treatment of the subject matter and the design of a functional methodological approach that can serve as a foundation for developing further geoprocessing tools of a similar kind.
- The solution has strong potential not only for professionals, but also as a practical educational aid in teaching visualisation methods in cartography and geoinformatics.
- The tool represents an open system ready for future extension with new parameters, additional data classification methods, and more advanced graphic configuration options.


## Recommended Citation

**Thesis:**
> SEDLÁČEK, Pavel. *Automatizace tvorby číselných kartodiagramů v prostředí ArcGIS*. Master's thesis. Olomouc: Palacký University Olomouc, Faculty of Science, Department of Geoinformatics, 2026. Supervisor: Mgr. Radek Barvíř, Ph.D.
> Available at: https://www.geoinformatics.upol.cz/dprace/magisterske/sedlacek26/

**Repository:**
> SEDLÁČEK, Pavel. *Graduated Numbers Generator* [software]. GitHub, 2026. Available at: https://github.com/TheodalCZ/Ciselne_Kartodiagramy
