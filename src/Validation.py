import arcpy
import os
import re
import winreg
import statistics
from fontTools.ttLib import TTFont


class ToolValidator:
    """Validator for the Graduated Numbers Generator toolbox.

    This class manages parameter validation and dynamic list updates for
    the custom graduated labels script tool in ArcGIS Pro.
    """

    def __init__(self):
        """Initialise the validator instance.

        Sets up parameter metadata and caches to optimise repeated access.
        """
        self.params = arcpy.GetParameterInfo()
        # cache to avoid expensive registry reads each update
        self._font_registry_names = None
        self._font_catalog = None

    def _decode_name_record(self, name_record):
        """Decode a font name-table record to text."""
        try:
            return name_record.toUnicode().strip()
        except Exception:
            try:
                return name_record.string.decode("utf-8", errors="ignore").strip()
            except Exception:
                return ""

    def _normalize_family_name(self, family_name):
        """Normalize a family name for matching and UI display."""
        family_name = re.sub(r"\s*\(.*?\)\s*$", "", str(family_name or "")).strip()
        family_name = re.sub(r"[-_]VariableFont.*$", "", family_name, flags=re.IGNORECASE).strip()
        family_name = re.sub(r"\s+", " ", family_name).strip()
        return family_name

    def _normalize_style_name(self, raw_style):
        """Normalize style names to ArcGIS-friendly labels."""
        if not raw_style:
            return None

        style_name_map = {
            "bi": "Bold Italic",
            "sb": "SemiBold",
            "db": "DemiBold",
            "li": "Light Italic",
            "b": "Bold",
            "i": "Italic",
            "z": "Regular",
        }
        strict_styles = {
            "thin", "extrathin", "ultrathin", "extralight", "ultralight", "light", "book",
            "regular", "normal", "medium", "semibold", "demibold", "bold", "extrabold",
            "ultrabold", "black", "heavy", "italic", "oblique"
        }
        canonical_style_names = {
            "thin": "Thin",
            "extrathin": "ExtraThin",
            "ultrathin": "UltraThin",
            "extralight": "ExtraLight",
            "ultralight": "UltraLight",
            "light": "Light",
            "book": "Book",
            "medium": "Medium",
            "semibold": "SemiBold",
            "demibold": "DemiBold",
            "bold": "Bold",
            "extrabold": "ExtraBold",
            "ultrabold": "UltraBold",
            "black": "Black",
            "heavy": "Heavy",
        }

        raw_style = re.sub(r"[-_]", " ", str(raw_style).strip())
        raw_style = re.sub(r"\s+", " ", raw_style).strip()
        if not raw_style:
            return None

        key = raw_style.lower()
        if key in style_name_map:
            return style_name_map[key]

        tokens = [t for t in re.split(r"\s+", key) if t]
        if not tokens:
            return None

        normalized_tokens = []
        for token in tokens:
            if token in style_name_map:
                normalized_tokens.extend(style_name_map[token].split())
                continue
            if token not in strict_styles:
                return None
            if token in ("italic", "oblique"):
                normalized_tokens.append(token.title())
            elif token in ("regular", "normal"):
                normalized_tokens.append("Regular")
            else:
                normalized_tokens.append(canonical_style_names.get(token, token.title()))

        if "Regular" in normalized_tokens and len(normalized_tokens) > 1:
            normalized_tokens = [token for token in normalized_tokens if token != "Regular"]

        style_value = " ".join(dict.fromkeys(normalized_tokens))
        if style_value.lower() == "regular italic":
            style_value = "Italic"
        return style_value or None

    def _iter_font_file_paths(self):
        """Yield unique absolute font file paths from registry and system folders."""
        font_paths = set()
        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        search_dirs = (
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
            os.path.join(local_appdata, r"Microsoft\Windows\Fonts"),
        )

        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                key = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
                i = 0
                while True:
                    try:
                        _, file_name, _ = winreg.EnumValue(key, i)
                        i += 1
                        candidate = str(file_name or "").strip()
                        if not candidate:
                            continue
                        if os.path.isabs(candidate) and os.path.exists(candidate):
                            font_paths.add(candidate)
                            continue
                        for base_dir in search_dirs:
                            resolved = os.path.join(base_dir, os.path.basename(candidate))
                            if os.path.exists(resolved):
                                font_paths.add(resolved)
                                break
                    except OSError:
                        break
                winreg.CloseKey(key)
            except Exception:
                pass

        for base_dir in search_dirs:
            if not os.path.isdir(base_dir):
                continue
            try:
                for file_name in os.listdir(base_dir):
                    if file_name.lower().endswith((".ttf", ".otf", ".ttc")):
                        font_paths.add(os.path.join(base_dir, file_name))
            except Exception:
                pass

        return sorted(font_paths)

    def _build_font_catalog(self):
        """Build a catalog of real font families and styles from font metadata."""
        if self._font_catalog is not None:
            return self._font_catalog

        catalog = {}
        for font_path in self._iter_font_file_paths():
            try:
                font = TTFont(font_path, recalcBBoxes=False)
            except Exception:
                continue

            try:
                family_names = set()
                style_names = set()

                if "name" in font:
                    for name_record in font["name"].names:
                        decoded = self._decode_name_record(name_record)
                        if not decoded:
                            continue
                        if name_record.nameID in (1, 16):
                            family_names.add(decoded)
                        elif name_record.nameID in (2, 17):
                            style_names.add(decoded)

                normalized_families = {
                    self._normalize_family_name(name)
                    for name in family_names
                    if self._normalize_family_name(name)
                }
                if not normalized_families:
                    font.close()
                    continue

                normalized_styles = {
                    self._normalize_style_name(style_name)
                    for style_name in style_names
                    if self._normalize_style_name(style_name)
                }
                if not normalized_styles:
                    normalized_styles = {"Regular"}

                has_wght_axis = False
                has_italic_axis = False
                real_min = 400
                real_max = 400
                if "fvar" in font:
                    for axis in font["fvar"].axes:
                        if axis.axisTag == "wght":
                            has_wght_axis = True
                            real_min = int(round(axis.minValue))
                            real_max = int(round(axis.maxValue))
                        elif axis.axisTag in ("ital", "slnt"):
                            has_italic_axis = True

                for family_name in normalized_families:
                    entry = catalog.setdefault(
                        family_name,
                        {
                            "styles": set(),
                            "files": set(),
                            "is_variable": False,
                            "has_wght_axis": False,
                            "has_italic_axis": False,
                            "real_min": 400,
                            "real_max": 400,
                        },
                    )
                    entry["styles"].update(normalized_styles)
                    entry["files"].add(font_path)
                    entry["has_wght_axis"] = entry["has_wght_axis"] or has_wght_axis
                    entry["has_italic_axis"] = entry["has_italic_axis"] or has_italic_axis
                    entry["is_variable"] = entry["is_variable"] or has_wght_axis or "variable" in family_name.lower()
                    if has_wght_axis:
                        entry["real_min"] = min(entry["real_min"], real_min)
                        entry["real_max"] = max(entry["real_max"], real_max)
            finally:
                try:
                    font.close()
                except Exception:
                    pass

        self._font_catalog = catalog
        return catalog

    def _load_font_families(self):
        """Load available font families from Windows registry and folders.

        This method reads both HKLM/HKCU font registry keys and user/system
        font folders to gather family names. It normalises and filters entries
        to remove style suffixes for a cleaner family list.
        """
        return sorted(self._build_font_catalog().keys())

    def _load_font_registry(self):
        """Build a mapping from font names to file paths.

        Reads registry values and supplements them with files found in the
        Windows and user font folders so that fonts installed without registry
        entries (e.g. per-user fonts) are still discovered.
        """
        return {family_name: sorted(entry["files"]) for family_name, entry in self._build_font_catalog().items()}

    def _get_font_styles(self, family_name):
        """Robust style detection with strict family matching and fontTools consistency."""
        if not family_name:
            return ["Regular"]

        weight_to_preferred = {
            100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular",
            500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold",
            900: "Black", 950: "UltraBlack"
        }
        name_to_weight = {
            "thin": 100, "extrathin": 100, "ultrathin": 100,
            "extralight": 200, "ultralight": 200,
            "light": 300, "book": 350,
            "regular": 400, "normal": 400,
            "medium": 500,
            "semibold": 600, "demibold": 600,
            "bold": 700,
            "extrabold": 800, "ultrabold": 800,
            "black": 900, "heavy": 900, "extrablack": 950, "ultrablack": 950,
        }

        family_clean = self._normalize_family_name(family_name)
        catalog = self._build_font_catalog()
        matched_family = next((name for name in catalog if name.lower() == family_clean.lower()), None)
        if not matched_family:
            return ["Regular"]

        entry = catalog[matched_family]
        styles = set(entry["styles"]) or {"Regular"}
        explicit_italic_styles = {style_name for style_name in styles if re.search(r"italic|oblique", style_name, re.IGNORECASE)}
        explicit_nonitalic_styles = styles - explicit_italic_styles

        def sort_key(s):
            s_low = s.lower()
            is_italic = "italic" in s_low or "oblique" in s_low
            tokens = re.sub(r"[^a-z0-9]", " ", re.sub(r"\s+italic$", "", s_low).strip()).split()
            wt = name_to_weight.get(tokens[0].replace("extra", "").replace("ultra", ""), 400) if tokens else 400
            return (0 if not is_italic else 1, wt, s_low)

        if entry["is_variable"] or entry["has_wght_axis"]:
            if len(explicit_nonitalic_styles) >= 2:
                result = sorted(explicit_nonitalic_styles, key=sort_key)
            else:
                available_weights = [wt for wt in weight_to_preferred if entry["real_min"] <= wt <= entry["real_max"]]
                result = [weight_to_preferred[wt] for wt in sorted(available_weights)]
                if not result:
                    result = ["Regular"]

            for style in sorted(explicit_italic_styles, key=sort_key):
                if style not in result:
                    result.append(style)

            if entry["has_italic_axis"] and "Italic" not in result:
                result.append("Italic")
        else:
            result = sorted(styles, key=sort_key)

        for light_family in ["Light", "ExtraLight", "UltraLight"]:
            it_style = f"{light_family} Italic"
            if it_style in explicit_italic_styles and it_style not in result:
                result.append(it_style)

        if not result:
            result = ["Regular"]

        return sorted(set(result), key=sort_key)
    
    def initializeParameters(self):
        """Set initial help text, defaults and choice lists."""
        try:
            # Input parameters
            self.params[0].displayName = "Input Layer"
            self.params[0].description = "Select the input layer to label."

            self.params[1].displayName = "Attribute Field"
            self.params[1].description = "Select the numeric field for classification."
            self.params[1].filter.list = ['Short', 'Long', 'Float', 'Double']

            # read-only info param for total element count
            self.params[2].displayName = "Total Element Count"
            self.params[2].value = "Select Layer and Attribute to preview count"

            # read-only info param for value range
            self.params[3].displayName = "Value Range"
            self.params[3].value = "Select Layer and Attribute to preview range"

            # read-only info param for average and median
            self.params[4].displayName = "Average | Median"
            self.params[4].value = "Select Layer and Attribute to preview average and median"

            # Classification parameters
            self.params[5].displayName = "Classification Method"
            self.params[5].description = "Choose how to classify values into categories."
            self.params[5].filter.list = [
                "Manual ...",
                "Proportional (Unclassed) ...",
                "Equal Interval",
                "Quantile",
                "Natural Breaks",
                "Geometric Interval",
            ]

            self.params[6].displayName = "Number of Categories"
            self.params[6].description = "Specify the number of categories (2-10)."
            self.params[7].displayName = "Manual Class Breaks (Space or ";" Separated)"
            self.params[7].description = "Enter custom break values, e.g., '10.5; 500; 1000' or '10,5 500 1000'."

            # Styling parameters
            self.params[8].displayName = "Minimum Font Size (pt)"
            self.params[8].description = "Minimum size for labels."

            self.params[9].displayName = "Maximum Font Size (pt)"
            self.params[9].description = "Maximum size for labels."
            
            self.params[10].displayName = "Font Selection"
            self.params[10].description = "Select the font family."
            families = self._load_font_families()

            if families:
                self.params[10].filter.list = families
                if self.params[10].value is None:
                    self.params[10].value = "Calibri" if "Calibri" in families else "Arial" if "Arial" in families else families[0]
                    
            self.params[11].displayName = "Font Weight/Style"
            self.params[11].datatype = "GPString"
            self.params[11].description = (
                "Select font style (Regular, Bold, etc.) or "
                "'Gradient Font Weight ...' to interpolate between two styles."
            )

            # Font Weight (min) only enabled if gradient
            self.params[12].displayName = "Font Weight (min)"
            self.params[12].datatype = "GPString"
            self.params[12].description = "Minimum font style/weight for gradient (e.g. Light)."
            self.params[12].enabled = False

            # Font Weight (max) only enabled if gradient
            self.params[13].displayName = "Font Weight (max)"
            self.params[13].datatype = "GPString"
            self.params[13].description = "Maximum font style/weight for gradient (e.g. Bold)."
            self.params[13].enabled = False

            # Letter Spacing (%)
            self.params[14].displayName = "Letter Spacing (%)"
            self.params[14].datatype = "GPLong"
            self.params[14].description = "Extra character spacing in percent (e.g., 200). Default is 0."
            if self.params[14].value is None:
                self.params[14].value = 0

            # Text Color (start)
            self.params[15].displayName = "Text Color (start)"
            self.params[15].datatype = "GPString"
            self.params[15].description = (
                "Start text color. Examples: HEX '#RRGGBB' or 'RRGGBBAA', "
                "RGBA 'R,G,B,A' (R,G,B 0-255, A 0-1 or 0-255), "
                "CMYKA 'C,M,Y,K,A' (0..1 or 0..100, A 0-1 or 0-255)."
            )
            if self.params[15].value is None:
                self.params[15].value = "0,0,0,1"

            # Use a gradient for text color?
            self.params[16].displayName = "Use color gradient"
            self.params[16].datatype = "GPBoolean"
            self.params[16].description = (
                "If True, the second text color will be used for a gradient. "
                "If False, the end color is ignored."
            )
            self.params[16].direction = "Input"
            self.params[16].parameterType = "Optional"
            self.params[16].enabled = True
            if self.params[16].value is None:
                self.params[16].value = False

            # Mid color (enabled only when gradient is on)
            self.params[17].displayName = "Text Color (mid)"
            self.params[17].datatype = "GPString"
            self.params[17].description = "Middle text color (used only when 'Use color gradient' is True)."
            self.params[17].enabled = False
            if self.params[17].value is None:
                self.params[17].value = ""

            # End color (enabled only when gradient is on)
            self.params[18].displayName = "Text Color (end)"
            self.params[18].datatype = "GPString"
            self.params[18].description = "End text color (used only when 'Use color gradient' is True)."
            self.params[18].enabled = False
            if self.params[18].value is None:
                self.params[18].value = "0,0,0,1"

            # Thousands Separator
            self.params[19].displayName = "Thousands Separator"
            self.params[19].datatype = "GPString"
            self.params[19].description = "Choose separator: Comma (3,215,410.50), Space (3 215 410,50), or None (3215410,50)."
            self.params[19].filter.list = ["Comma", "Space", "None"]
            if self.params[19].value is None:
                self.params[19].value = "Space"

            # Value Scale
            self.params[20].displayName = "Value Scale"
            self.params[20].datatype = "GPString"
            self.params[20].description = "Scale values by dividing by: 1 (no scaling), 1000 (thousands), etc. Or multiply by selecting decimals."
            self.params[20].filter.list = [
                "0.000001 (millionths)",
                "0.001 (thousandths)",
                "0.01 (hundredths)",
                "0.1 (tenths)",
                "1 (no scaling)",
                "1,000 (thousands)",
                "1,000,000 (millions)",
                "1,000,000,000 (billions)",
                "1,000,000,000,000 (trillions)"
            ]
            if self.params[20].value is None:
                self.params[20].value = "1 (no scaling)"

            # Value Suffix (optional)
            self.params[21].displayName = "Value Suffix (optional)"
            self.params[21].datatype = "GPString"
            self.params[21].description = "Optional text after numbers, e.g., 'mil.' for millions."
            if self.params[21].value is None:
                self.params[21].value = ""

            # Decimal Places After Scaling
            self.params[22].displayName = "Decimal Places After Scaling"
            self.params[22].datatype = "GPLong"
            self.params[22].description = "Round to this many decimals after scaling."
            if self.params[22].value is None:
                self.params[22].value = 1

            # Prevent Label Wrapping (toggle)
            self.params[23].displayName = "Prevent Label Wrapping"
            self.params[23].datatype = "GPBoolean"
            self.params[23].description = (
                "If True, the tool will disable label stacking (set stackLabel to False in Maplex) so values stay on one line."
            )
            self.params[23].direction = "Input"
            self.params[23].parameterType = "Optional"
            self.params[23].enabled = True
            if self.params[23].value is None:
                self.params[23].value = True

            # Label Offset X (pt)
            self.params[24].displayName = "Label Offset X (pt)"
            self.params[24].datatype = "GPLong"
            self.params[24].description = "Horizontal offset for label position in points (pt). Default is 0."
            if self.params[24].value is None:
                self.params[24].value = 0

            # Label Offset Y (pt)
            self.params[25].displayName = "Label Offset Y (pt)"
            self.params[25].datatype = "GPLong"
            self.params[25].description = "Vertical offset for label position in points (pt). Default is 0."
            if self.params[25].value is None:
                self.params[25].value = 0

            # Underline Text
            self.params[26].displayName = "Underline Text"
            self.params[26].datatype = "GPBoolean"
            self.params[26].description = "If True, adds an underline to all generated class labels (uniform for the text symbol)."
            self.params[26].direction = "Input"
            self.params[26].parameterType = "Optional"
            self.params[26].enabled = True
            if self.params[26].value is None:
                self.params[26].value = False

            # Halo parameters
            self.params[27].displayName = "Halo Color (start)"
            self.params[27].datatype = "GPString"
            self.params[27].description = (
                "Start halo color. Examples: HEX '#RRGGBB' or 'RRGGBBAA', "
                "RGBA 'R,G,B,A' (R,G,B 0-255, A 0-1 or 0-255), "
                "CMYKA 'C,M,Y,K,A' (0..1 or 0..100, A 0-1 or 0-255)."
            )
            if self.params[27].value is None:
                self.params[27].value = "255,255,255,1"

            self.params[28].displayName = "Halo Width (pt)"
            self.params[28].datatype = "GPDouble"
            self.params[28].description = "Width of the label halo in points (pt). Set to 0 to disable halo."
            if self.params[28].value is None:
                self.params[28].value = 0.0

            self.params[29].displayName = "Use Halo Gradient"
            self.params[29].datatype = "GPBoolean"
            self.params[29].description = (
                "If True, the middle and end halo colors (and optional width end) will be used for a gradient. "
                "If False, secondary halo settings are ignored."
            )
            self.params[29].direction = "Input"
            self.params[29].parameterType = "Optional"
            self.params[29].enabled = True
            if self.params[29].value is None:
                self.params[29].value = False

            self.params[30].displayName = "Halo Color (mid)"
            self.params[30].datatype = "GPString"
            self.params[30].description = "Middle halo color (used only when 'Use halo gradient' is True)."
            self.params[30].enabled = False
            if self.params[30].value is None:
                self.params[30].value = ""

            self.params[31].displayName = "Halo Color (end)"
            self.params[31].datatype = "GPString"
            self.params[31].description = "End halo color (used only when 'Use halo gradient' is True)."
            self.params[31].enabled = False
            if self.params[31].value is None:
                self.params[31].value = "255,255,255,1"

            self.params[32].displayName = "Halo Width (end)"
            self.params[32].datatype = "GPDouble"
            self.params[32].description = "End halo width (pt) used only when 'Use halo gradient' is True. If empty, uses the same width as 'Halo Width'."
            self.params[32].enabled = False
            # No default value - will use min halo width if empty

            # Shadow Color 
            shadow_color_text = self.params[33].valueAsText
            if shadow_color_text and not str(shadow_color_text).strip():
                self.params[31].setErrorMessage(
                    "Invalid shadow color format. Use HEX '#RRGGBB'/'RRGGBBAA', 'R,G,B,A', or 'C,M,Y,K,A'."
                )

        except Exception:
            pass

        try:
            sel_family = (self.params[10].valueAsText or (self.params[10].filter.list[0] if self.params[10].filter.list else None))
            styles = self._get_font_styles(sel_family)
            if styles:
                full_list = ["Gradient Font Weight ..."] + styles
                self.params[11].filter.list = full_list
                # If nothing is selected or gradient is selected, set default to Regular (not gradient)
                cur_val = (self.params[11].valueAsText or '').strip()
                if not cur_val or cur_val == "Gradient Font Weight ...":
                    preferred = next((s for s in styles if s.lower() == "regular"), styles[0])
                    self.params[11].valueAsText = preferred
        except Exception:
            pass

        # cache raw registry names for future calls (save as dict for compatibility with _get_font_styles)
        try:
            self._font_registry_names = dict(self._load_font_registry())
        except Exception:
            pass

    def updateParameters(self):
        """Refresh dependent parameters based on current user selections.

        This method enables or disables parameters in response to user actions,
        such as switching classification method or toggling gradient options.
        It also updates colours and preview stats that are derived from input
        layer data.
        """
        # enable/disable manual breaks vs count
        try:
            classification_method = self.params[5].valueAsText or self.params[5].value
            if classification_method in {"Manual", "Manual ..."}:
                self.params[6].enabled = False
                self.params[7].enabled = True
            elif classification_method == "Proportional (Unclassed) ...":
                # Proportional unclassed has no fixed number of categories
                self.params[6].enabled = False
                self.params[7].enabled = False
            else:
                self.params[6].enabled = True
                self.params[7].enabled = False
        except Exception:
            pass

        # refresh font styles immediately when family changes (so param[11] shows only supported styles)
        try:
            sel_family = self.params[10].valueAsText
            available_families = list(self.params[10].filter.list or [])
            if sel_family:
                if available_families and sel_family not in available_families:
                    self.params[10].setWarningMessage(
                        "Selected font family is not available on this system. Choose a family from the list or the tool will fall back during execution."
                    )
                    styles = ["Regular"]
                else:
                    self.params[10].clearMessage()
                    styles = self._get_font_styles(sel_family) or []
                full_list = ["Gradient Font Weight ..."] + styles
                try:
                    cur_list = list(self.params[11].filter.list or [])
                except Exception:
                    cur_list = []
                # update filter list only when different to avoid flicker
                if full_list and cur_list != full_list:
                    try:
                        self.params[11].filter.list = full_list
                    except Exception:
                        pass

                # current selected style (as text)
                try:
                    cur_sel = (self.params[11].valueAsText or str(self.params[11].value or "")).strip()
                except Exception:
                    cur_sel = ""

                # helper normalizer
                norm = lambda s: str(s or "").strip().lower()

                # if nothing is selected, set default to Regular (not gradient)
                if not cur_sel:
                    preferred = next((s for s in styles if norm(s) == "regular"), styles[0] if styles else "")
                    if preferred:
                        try:
                            self.params[11].valueAsText = preferred
                        except Exception:
                            try:
                                self.params[11].value = preferred
                            except Exception:
                                pass
        except Exception:
            pass

        # Dynamically enable start/end style only if gradient is selected in param[11]
        try:
            fw_val = (self.params[11].valueAsText or "").strip()
            is_gradient = fw_val == "Gradient Font Weight ..."
            self.params[12].enabled = is_gradient
            self.params[13].enabled = is_gradient
            if is_gradient:
                sel_family = self.params[10].valueAsText
                styles = self._get_font_styles(sel_family) if sel_family else []
                if styles:
                    self.params[12].filter.list = styles
                    self.params[13].filter.list = styles
                    if not (self.params[12].valueAsText or "").strip():
                        self.params[12].valueAsText = styles[0]
                    if not (self.params[13].valueAsText or "").strip():
                        self.params[13].valueAsText = styles[-1] if len(styles) > 1 else styles[0]
        except Exception:
            pass

        # Enable/disable mid and end color parameters based on the gradient toggles
        try:
            use_color_gradient = bool(self.params[16].value)
            self.params[17].enabled = use_color_gradient
            self.params[18].enabled = use_color_gradient
        except Exception:
            pass
        try:
            use_halo_gradient = bool(self.params[29].value)
            self.params[30].enabled = use_halo_gradient
            self.params[31].enabled = use_halo_gradient
            self.params[32].enabled = use_halo_gradient
        except Exception:
            pass

        # update preview range text (including new Total Count, Value Range, Average & Median)
        try:
            input_layer = self.params[0].valueAsText
            attribute_field = self.params[1].valueAsText
            if input_layer and attribute_field:
                # First check if field is numeric
                field_is_numeric = False
                try:
                    fields = arcpy.ListFields(str(input_layer))
                    for f in fields:
                        if f.name == str(attribute_field):
                            numeric_types = ['Integer', 'Single', 'Double', 'OID', 'SmallInteger', 'Long']
                            if f.type in numeric_types:
                                field_is_numeric = True
                            break
                except Exception:
                    pass
                
                if not field_is_numeric:
                    self.params[2].value = "Error: Non-numeric field selected"
                    self.params[3].value = "Error: Non-numeric field selected"
                    self.params[4].value = "Error: Non-numeric field selected"
                else:
                    try:
                        values = [
                            row[0]
                            for row in arcpy.da.SearchCursor(input_layer, [attribute_field])
                            if row[0] is not None
                        ]
                        if values:
                            # Total Element Count
                            total_count = len(values)
                            self.params[2].value = f"{total_count}"
                            
                            # Value Range
                            min_val = min(values)
                            max_val = max(values)
                            formatted_min = f"{min_val:,}".replace(",", " ")
                            formatted_max = f"{max_val:,}".replace(",", " ")
                            self.params[3].value = f"Min: {formatted_min} | Max: {formatted_max}"
                            
                            # Average and Median
                            avg_val = statistics.mean(values)
                            median_val = statistics.median(values)
                            formatted_avg = f"{avg_val:,.1f}".replace(",", " ")
                            formatted_median = f"{median_val:,.1f}".replace(",", " ")
                            self.params[4].value = f"Avg: {formatted_avg} | Med: {formatted_median}"
                        else:
                            self.params[2].value = "Select Layer and Attribute to preview count"
                            self.params[3].value = "Select Layer and Attribute to preview range"
                            self.params[4].value = "Select Layer and Attribute to preview average and median"
                    except Exception as exc:
                        self.params[2].value = f"Error: {exc}"
                        self.params[3].value = f"Error: {exc}"
                        self.params[4].value = f"Error: {exc}"
            else:
                self.params[2].value = "Select Layer and Attribute to preview count"
                self.params[3].value = "Select Layer and Attribute to preview range"
                self.params[4].value = "Select Layer and Attribute to preview average and median"
        except Exception:
            pass

        return

    def updateMessages(self):
        """Validate font sizes, color text formats, and field types."""
        # Validate Attribute Field (param 1) - must be numeric
        try:
            input_layer = self.params[0].value
            attribute_field = self.params[1].value
            
            if input_layer and attribute_field:
                # Get field type
                field_obj = None
                try:
                    fields = arcpy.ListFields(str(input_layer))
                    for f in fields:
                        if f.name == str(attribute_field):
                            field_obj = f
                            break
                except Exception:
                    pass
                
                if field_obj:
                    # Check if field is numeric (Integer, Single, Double, OID, SmallInteger)
                    numeric_types = ['Integer', 'Single', 'Double', 'OID', 'SmallInteger', 'Long']
                    if field_obj.type not in numeric_types:
                        self.params[1].setWarningMessage(
                            f"Field '{attribute_field}' is of type '{field_obj.type}'. "
                            "A numeric field (Integer, Double, etc.) is required for classification."
                        )
                    else:
                        self.params[1].clearMessage()
        except Exception:
            pass
        
        # Font Size Check (Parameters 8 and 9)
        min_size = self.params[8].value
        max_size = self.params[9].value
        if min_size is not None and max_size is not None:
            try:
                min_val = float(min_size)
                max_val = float(max_size)
                if min_val <= 0:
                    self.params[8].setErrorMessage("Font size must be greater than 0.")
                elif min_val >= max_val:
                    self.params[9].setErrorMessage("Maximum Font Size must be strictly greater than Minimum Font Size.")
                elif (max_val - min_val) < 3:
                    self.params[9].setWarningMessage("The difference between Min and Max font size is very small.")
                else:
                    self.params[8].clearMessage()
                    self.params[9].clearMessage()
            except Exception:
                self.params[8].setErrorMessage("Please enter numeric values for font sizes.")
                self.params[9].setErrorMessage("Please enter numeric values for font sizes.")

        # Number of Categories Check (Parameter 6)
        num_categories = self.params[6].value
        if num_categories is not None:
            try:
                if int(num_categories) <= 0:
                    self.params[6].setErrorMessage("Number of categories must be at least 1.")
                else:
                    self.params[6].clearMessage()
            except Exception:
                self.params[6].setErrorMessage("Number of categories must be a positive integer.")

        # Validate decimal places parameter (must be an integer >= 0)
        try:
            dp_val = self.params[22].value
            if dp_val is not None:
                try:
                    dp_int = int(dp_val)
                    if dp_int < 0:
                        self.params[22].setErrorMessage("Decimal places must be 0 or greater.")
                except Exception:
                    self.params[22].setErrorMessage("Decimal places must be an integer.")
        except Exception:
            pass

        def valid_alpha(a):
            try:
                if 0 <= a <= 1 or 0 <= int(round(a)) <= 255:
                    return True
            except Exception:
                pass
            return False

        def parse_hsl_angle(p):
            p = str(p).strip().lower()
            if p.endswith('deg'):
                p = p[:-3]
            return float(p)

        def parse_hsl_component(p):
            p = str(p).strip()
            if p.endswith('%'):
                return float(p[:-1]) / 100.0
            v = float(p)
            return v / 100.0 if v > 1 else v

        def valid_color_text(s):
            if not s:
                return False
            s = s.strip()
            first = s.split(",")[0].strip()
            if re.match(r"^#?[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$", first):
                return True
            parts = [p.strip() for p in s.split(",")]
            
            # RGB / HSL (3 parts)
            if len(parts) == 3:
                # HSL is accepted when explicitly marked by % or deg.
                if parts[1].endswith('%') or parts[2].endswith('%') or parts[0].lower().endswith('deg'):
                    try:
                        h = parse_hsl_angle(parts[0])
                        s_comp = parse_hsl_component(parts[1])
                        l_comp = parse_hsl_component(parts[2])
                        if 0 <= h <= 360 and 0 <= s_comp <= 1 and 0 <= l_comp <= 1:
                            return True
                    except Exception:
                        pass
                try:
                    r, g, b = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
                    if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                        return True
                except Exception:
                    pass
                return False
            
            # RGBA / HSLA / CMYK (4 parts)
            if len(parts) == 4:
                # HSLA is accepted when explicitly marked by % or deg.
                if parts[1].endswith('%') or parts[2].endswith('%') or parts[0].lower().endswith('deg'):
                    try:
                        h = parse_hsl_angle(parts[0])
                        s_comp = parse_hsl_component(parts[1])
                        l_comp = parse_hsl_component(parts[2])
                        a = float(parts[3])
                        if 0 <= h <= 360 and 0 <= s_comp <= 1 and 0 <= l_comp <= 1 and valid_alpha(a):
                            return True
                    except Exception:
                        pass

                # Try first as RGBA (RGB 0-255 + alpha)
                try:
                    r, g, b = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
                    a = float(parts[3])
                    if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255 and valid_alpha(a):
                        return True
                except Exception:
                    pass
                
                # Try as CMYK (0-1 or 0-100 range)
                try:
                    c, m, y, k = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
                    def ok(v): return 0 <= v <= 1 or 0 <= v <= 100
                    if all(ok(v) for v in (c, m, y, k)):
                        return True
                except Exception:
                    pass
                
                return False
            
            # CMYKA (5 parts)
            if len(parts) == 5:
                try:
                    c, m, y, k = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
                    a = float(parts[4])
                    def ok(v): return 0 <= v <= 1 or 0 <= v <= 100
                    if all(ok(v) for v in (c, m, y, k)) and valid_alpha(a):
                        return True
                except Exception:
                    pass
                return False
            
            return False

        # Correct color validation for Text Colour (param 14) and optional gradient end (param 16)
        color_text_start = self.params[15].valueAsText
        if color_text_start and not valid_color_text(color_text_start):
            self.params[15].setErrorMessage(
                "Invalid start color. Use HEX '#RRGGBB'/'RRGGBBAA', RGB/RGBA, HSL/HSLA, or CMYK/CMYKA."
            )

        try:
            use_color_gradient = bool(self.params[16].value)
        except Exception:
            use_color_gradient = False

        if use_color_gradient:
            color_text_mid = self.params[17].valueAsText
            if color_text_mid and not valid_color_text(color_text_mid):
                self.params[17].setErrorMessage("Invalid mid text color format.")

            color_text_end = self.params[18].valueAsText
            if color_text_end and not valid_color_text(color_text_end):
                self.params[18].setErrorMessage("Invalid end text color format.")

        # Halo color validation (start always validated, mid and end only when gradient is used)
        halo_start = self.params[27].valueAsText
        if halo_start and not valid_color_text(halo_start):
            self.params[27].setErrorMessage(
                "Invalid start halo color format. Use HEX, RGB/RGBA, HSL/HSLA or CMYK/CMYKA as described."
            )

        try:
            use_halo_gradient = bool(self.params[29].value)
        except Exception:
            use_halo_gradient = False

        if use_halo_gradient:
            halo_mid = self.params[30].valueAsText
            if halo_mid and not valid_color_text(halo_mid):
                self.params[30].setErrorMessage("Invalid mid halo color format.")

            halo_end = self.params[31].valueAsText
            if halo_end and not valid_color_text(halo_end):
                self.params[31].setErrorMessage("Invalid end halo color format.")

            # Validate end halo width if gradient is on (optional - if empty, uses halo_width)
            halo_width_end_val = self.params[32].valueAsText
            if halo_width_end_val and str(halo_width_end_val).strip():
                try:
                    halo_width_end = float(halo_width_end_val)
                    if halo_width_end < 0:
                        self.params[32].setErrorMessage("Halo Width (end) must be >= 0.")
                except Exception:
                    self.params[32].setErrorMessage("Halo Width (end) must be a number.")
            else:
                self.params[32].clearMessage()  # No error if empty

        # validate font-weight gradient availability and start/end selections (only for font style, not for color or separator)
        try:
            # Check only if it is a style gradient (not a color gradient)
            fw_val = (self.params[11].valueAsText or '').strip()
            is_fw_gradient = fw_val == 'Gradient Font Weight ...'

            def is_numeric_weight(val):
                if not val:
                    return False
                try:
                    m = re.search(r"([-+]?[0-9]*\.?[0-9]+)", str(val))
                    return bool(m)
                except Exception:
                    return False

            if is_fw_gradient:
                sel_family = self.params[10].valueAsText
                styles = self._get_font_styles(sel_family) if sel_family else []
                if len(styles) < 2:
                    try:
                        self.params[11].setWarningMessage("Selected font has few or no distinct styles — gradient may not be visible.")
                    except Exception:
                        pass
                # check start/end values for font weight min/max only (param 12/13)
                start = self.params[12].valueAsText
                end = self.params[13].valueAsText
                if start and styles and start not in styles and not is_numeric_weight(start):
                    try:
                        self.params[12].setErrorMessage("Start style not available for selected font.")
                    except Exception:
                        pass
                if end and styles and end not in styles and not is_numeric_weight(end):
                    try:
                        self.params[13].setErrorMessage("End style not available for selected font.")
                    except Exception:
                        pass
        except Exception:
            pass

        # Feature Count & Classification Method Check (Parameters 0, 2, and 5)
        total_element_count = self.params[2].valueAsText
        classification_method = self.params[5].valueAsText or self.params[5].value
        count = None
        if total_element_count:
            try:
                count_str = total_element_count.replace(" ", "").replace(",", "")
                count = int(count_str)
            except ValueError:
                pass

        # GENERAL LAYER WARNING (Evaluates independently of the method)
        if count is not None and count > 200:
            self.params[1].setWarningMessage("Layer has a high number of features. Generating this many graded labels is "
                                             "cartographically unsuitable. The Maplex placement engine will be severely overloaded, "
                                             "which may cause ArcGIS Pro to become unresponsive or completely freeze.")

        # SPECIFIC METHOD WARNING
        if classification_method == "Proportional (Unclassed) ..." and count is not None and count > 50:
            self.params[5].setWarningMessage("WARNING: The Proportional method creates a unique label class for EVERY single feature. "
                                             "Using this on > 50 features will exponentially bloat your Table of Contents, "
                                             "with a risk of completely freezing or crashing ArcGIS Pro.")

        # Value Scale vs Data Range Check (Parameters 3 and 19)
        try:
            value_scale_text = self.params[20].valueAsText
            value_range_text = self.params[3].valueAsText

            if value_scale_text and value_range_text:
                clean_p3 = str(value_range_text).replace(",", "").replace(" ", "")
                clean_p19 = str(value_scale_text).replace(",", "").replace(" ", "")

                numeric_values = re.findall(r"[-+]?\d*\.\d+|\d+", clean_p3)
                if numeric_values:
                    max_value = max(float(v) for v in numeric_values)

                    scale_match = re.search(r"[-+]?\d*\.\d+|\d+", clean_p19)
                    if scale_match:
                        scale = float(scale_match.group(0))
                        if max_value < scale and scale > 1:
                            self.params[20].setWarningMessage(
                                "Warning: Your selected Value Scale is larger than the maximum value in your dataset. "
                                "Labels will likely display as 0 or extremely small fractions."
                            )
                        elif scale < 1 and max_value > 0:
                            # For decimal scales, check if the potential maximum label exceeds 1 billion
                            potential_max_label = max_value / scale
                            if potential_max_label > 1_000_000_000:
                                self.params[20].setWarningMessage(
                                    "Warning: The selected scale will result in extremely large numbers (over 1 billion). "
                                    "Labels may be unreadable or overlap significantly."
                                )
                            else:
                                self.params[20].clearMessage()
                        else:
                            self.params[20].clearMessage()
            else:
                self.params[20].clearMessage()
        except Exception:
            pass

        # Removed overwriting filter.list for param[14] to only styles without gradient
        # (Font weight list ordering is managed in initializeParameters/updateParameters.)

        return

