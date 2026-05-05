"""
UI Dark Mode Tests

Verifies UI cleanliness and dark mode consistency.
"""

import pytest
import sys
from pathlib import Path
import py_compile
import importlib.util

PROJECT_ROOT = Path(__file__).parent.parent


class TestNoRawArtifacts:
    """Test that no raw UI artifacts appear in the dashboard."""

    def test_no_double_arrow_right_in_dashboard(self):
        """Verify double_arrow_right is not in dashboard.py."""
        dashboard_path = PROJECT_ROOT / "dashboard.py"
        content = dashboard_path.read_text()
        assert "double_arrow_right" not in content, "Found double_arrow_right in dashboard.py"

    def test_no_material_icons_in_dashboard(self):
        """Verify :material icon references are not in dashboard.py."""
        dashboard_path = PROJECT_ROOT / "dashboard.py"
        content = dashboard_path.read_text()
        assert ":material" not in content, "Found :material icon reference in dashboard.py"

    def test_no_arrow_right_raw_text(self):
        """Verify arrow_right is not used as raw text."""
        dashboard_path = PROJECT_ROOT / "dashboard.py"
        content = dashboard_path.read_text()
        # Allow arrow emoji (→) but not raw text "arrow_right"
        assert "arrow_right" not in content, "Found arrow_right raw text in dashboard.py"

    def test_no_st_icon_calls(self):
        """Verify st.icon is not used."""
        dashboard_path = PROJECT_ROOT / "dashboard.py"
        content = dashboard_path.read_text()
        assert "st.icon" not in content, "Found st.icon call in dashboard.py"

    def test_no_emoji_shortcodes(self):
        """Verify no emoji shortcodes like :arrow: are used."""
        dashboard_path = PROJECT_ROOT / "dashboard.py"
        content = dashboard_path.read_text()
        # Check for common emoji shortcode patterns
        import re
        shortcode_pattern = r':[a-z_]+:'
        matches = re.findall(shortcode_pattern, content)
        # Filter out CSS color references like :hover, :active
        css_pseudo = [m for m in matches if m in [':hover', ':active', ':focus', ':before', ':after']]
        non_css = [m for m in matches if m not in css_pseudo]
        assert len(non_css) == 0, f"Found emoji shortcodes in dashboard.py: {non_css}"


class TestPlotlyModebarDisabled:
    """Test that Plotly modebar is disabled on all charts."""

    def test_plotly_modebar_disabled_in_sector_section(self):
        """Verify sector allocation chart has displayModeBar=False."""
        section_path = PROJECT_ROOT / "src" / "ui" / "sections" / "sector_allocation_section.py"
        content = section_path.read_text()
        assert "displayModeBar': False" in content or 'displayModeBar": False' in content, \
            "Sector allocation chart missing displayModeBar=False"

    def test_no_plotly_chart_without_modebar_config(self):
        """Verify all st.plotly_chart calls include modebar config."""
        # Check all section files
        sections_dir = PROJECT_ROOT / "src" / "ui" / "sections"
        for file in sections_dir.glob("*.py"):
            content = file.read_text()
            if "st.plotly_chart" in content:
                # Each plotly_chart should have config with displayModeBar
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if "st.plotly_chart" in line:
                        # Check following lines for config
                        context = '\n'.join(lines[i:i+5])
                        assert "displayModeBar" in context, \
                            f"Found st.plotly_chart without displayModeBar config in {file.name}"


class TestDarkTableRenderer:
    """Test that dark table renderer exists and works."""

    def test_dark_table_renderer_exists(self):
        """Verify render_dark_table function exists in tables.py."""
        tables_path = PROJECT_ROOT / "src" / "ui" / "tables.py"
        assert tables_path.exists(), "tables.py does not exist"
        content = tables_path.read_text()
        assert "def render_dark_table" in content, "render_dark_table function not found"

    def test_dark_table_uses_html_tables(self):
        """Verify dark table renders HTML tables, not st.dataframe."""
        tables_path = PROJECT_ROOT / "src" / "ui" / "tables.py"
        content = tables_path.read_text()
        # Should generate HTML table tags
        assert "<table" in content, "Dark table should generate HTML table tags"
        assert "st.markdown" in content, "Dark table should use st.markdown to render HTML"

    def test_dark_table_has_dark_colors(self):
        """Verify dark table uses dark theme colors."""
        tables_path = PROJECT_ROOT / "src" / "ui" / "tables.py"
        content = tables_path.read_text()
        # Should use theme color attributes
        assert "theme.card_bg" in content or "CARD_BG" in content, "Dark table should use card_bg"
        assert "theme.text" in content or "theme.text_muted" in content or "TEXT" in content, "Dark table should use text colors"
        assert "theme.border" in content or "BORDER" in content, "Dark table should use border color"


class TestThemeFunctions:
    """Test that theme functions exist and are properly configured."""

    def test_apply_dark_theme_exists(self):
        """Verify apply_dark_theme function exists in theme.py."""
        theme_path = PROJECT_ROOT / "src" / "ui" / "theme.py"
        assert theme_path.exists(), "theme.py does not exist"
        content = theme_path.read_text()
        assert "def apply_dark_theme" in content, "apply_dark_theme function not found"

    def test_theme_has_header_css(self):
        """Verify theme includes header styling CSS."""
        theme_path = PROJECT_ROOT / "src" / "ui" / "theme.py"
        content = theme_path.read_text()
        # Should include header/toolbar fixes
        assert '[data-testid="stHeader"]' in content, "Theme missing stHeader styling"
        assert '[data-testid="stToolbar"]' in content, "Theme missing stToolbar styling"

    def test_theme_has_modebar_hide(self):
        """Verify theme includes modebar hide CSS."""
        theme_path = PROJECT_ROOT / "src" / "ui" / "theme.py"
        content = theme_path.read_text()
        assert ".modebar" in content, "Theme missing modebar CSS hide"

    def test_theme_has_button_styling(self):
        """Verify theme includes button styling."""
        theme_path = PROJECT_ROOT / "src" / "ui" / "theme.py"
        content = theme_path.read_text()
        assert ".stButton > button" in content, "Theme missing button styling"
        assert "background-color" in content, "Theme missing button background styling"


class TestDashboardCompilation:
    """Test that dashboard compiles without errors."""

    def test_dashboard_py_compiles(self):
        """Verify dashboard.py compiles with py_compile."""
        dashboard_path = PROJECT_ROOT / "dashboard.py"
        assert dashboard_path.exists(), "dashboard.py must exist"
        py_compile.compile(str(dashboard_path), doraise=True)

    def test_ui_modules_compile(self):
        """Verify all UI modules compile."""
        ui_dir = PROJECT_ROOT / "src" / "ui"
        for file in ui_dir.glob("*.py"):
            py_compile.compile(str(file), doraise=True)

    def test_section_modules_compile(self):
        """Verify all section modules compile."""
        sections_dir = PROJECT_ROOT / "src" / "ui" / "sections"
        for file in sections_dir.glob("*.py"):
            py_compile.compile(str(file), doraise=True)


class TestNoStDataframeInSections:
    """Test that sections use dark HTML tables instead of st.dataframe."""

    def test_sector_allocation_uses_dark_table(self):
        """Verify sector allocation uses render_sector_table."""
        section_path = PROJECT_ROOT / "src" / "ui" / "sections" / "sector_allocation_section.py"
        content = section_path.read_text()
        assert "render_sector_table" in content, "Should use render_sector_table"
        # Should not have st.dataframe call (but allow it in comments/docstrings)
        import re
        # Find actual st.dataframe calls (not in comments)
        lines = content.split('\n')
        for line in lines:
            # Skip comments and docstrings
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if 'st.dataframe(' in line.lower():
                assert False, f"Found st.dataframe call: {line}"

    def test_signal_snapshot_uses_dark_table(self):
        """Verify signal snapshot uses render_signal_table."""
        section_path = PROJECT_ROOT / "src" / "ui" / "sections" / "signal_snapshot_section.py"
        content = section_path.read_text()
        assert "render_signal_table" in content, "Should use render_signal_table"
        assert "st.dataframe" not in content, "Should not use st.dataframe"

    def test_model_agreement_uses_dark_table(self):
        """Verify model agreement uses render_model_agreement_table."""
        section_path = PROJECT_ROOT / "src" / "ui" / "sections" / "model_agreement_section.py"
        content = section_path.read_text()
        assert "render_model_agreement_table" in content, "Should use render_model_agreement_table"
        assert "st.dataframe" not in content, "Should not use st.dataframe"

    def test_business_layer_uses_dark_table(self):
        """Verify business layer uses render_dark_table."""
        section_path = PROJECT_ROOT / "src" / "ui" / "sections" / "business_layer_section.py"
        content = section_path.read_text()
        assert "render_dark_table" in content, "Should use render_dark_table"
        assert "st.dataframe" not in content, "Should not use st.dataframe"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
