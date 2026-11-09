from pathlib import Path
import unittest


class AnalysisInspectorLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qml = (
            Path(__file__).resolve().parents[1] / "ums" / "qml" / "Main.qml"
        ).read_text(encoding="utf-8")

    def test_analysis_scroll_content_uses_a_fixed_viewport_width(self):
        self.assertIn("id: analysisScroll", self.qml)
        self.assertIn("contentWidth: availableWidth", self.qml)
        self.assertIn("width: analysisScroll.availableWidth", self.qml)

    def test_metadata_cards_have_concrete_flow_cell_widths(self):
        self.assertIn("id: analysisMetadataFlow", self.qml)
        self.assertIn("width: Math.max(1, (analysisMetadataFlow.width", self.qml)
        self.assertIn("Layout.preferredHeight: Math.ceil(metadataRepeater.count / metadataColumns)", self.qml)

    def test_inspector_has_no_layout_managed_metadata_grid_repeater(self):
        start = self.qml.index("id: analysisMetadataFlow")
        end = self.qml.index("Rectangle {\n                            Layout.fillWidth: true", start)
        metadata_section = self.qml[start:end]
        self.assertNotIn("GridLayout {", metadata_section)
        self.assertIn("delegate: Rectangle {", metadata_section)
        self.assertIn("height: 57", metadata_section)

    def test_hero_and_detail_cards_are_not_allowed_to_shrink_to_zero_width(self):
        start = self.qml.index("id: analysisScroll")
        end = self.qml.index("Rectangle {\n                            Layout.fillWidth: true", start)
        inspector = self.qml[start:end]
        self.assertIn("Layout.minimumWidth: 0", inspector)
        self.assertIn("Layout.preferredWidth: analysisScroll.availableWidth", inspector)


if __name__ == "__main__":
    unittest.main()
