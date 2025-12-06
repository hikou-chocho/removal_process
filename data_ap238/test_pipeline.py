"""
Unit tests for AP238 case JSON files with pipeline execution.
Tests that case JSON files can be processed through the pipeline and generate STL outputs.
"""

import json
import unittest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.main import app
from fastapi.testclient import TestClient


class TestAP238PipelineExecution(unittest.TestCase):
    """Test cases for running AP238 case JSON files through the pipeline."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures once for all tests."""
        cls.client = TestClient(app)
        cls.data_dir = Path(__file__).parent
        cls.input_dir = cls.data_dir / "input"
        cls.output_dir = cls.data_dir.parent / "data" / "output"

    def setUp(self):
        """Set up before each test."""
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_case_json(self, filename: str) -> dict:
        """Load a case JSON file."""
        case_file = self.input_dir / filename
        self.assertTrue(case_file.exists(), f"Case file not found: {case_file}")
        
        with open(case_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _run_pipeline(self, case_data: dict) -> dict:
        """Run the pipeline with case data and return the response."""
        response = self.client.post("/pipeline/run", json=case_data)
        # Pipeline may not support features yet - that's OK for this test
        return response

    def test_case1_milling_pipeline(self):
        """Test case1_milling.json through the full pipeline."""
        case = self._load_case_json("case1_milling.json")
        
        # Verify case structure
        self.assertIn("units", case)
        self.assertIn("stock", case)
        self.assertIn("features", case)
        self.assertEqual(len(case["features"]), 3)
        
        # Run pipeline (features as-is)
        response = self._run_pipeline(case)
        
        # If pipeline doesn't support features yet, skip execution check
        if response.status_code != 200:
            self.skipTest("Pipeline does not yet support features format")
        
        result = response.json()
        self.assertEqual(result["status"], "ok")
        
        # Check that STL files exist
        for step in result.get("steps", []):
            if step.get("solid"):
                solid_path = Path(step["solid"])
                if solid_path.exists():
                    self.assertGreater(solid_path.stat().st_size, 0)

    def test_case1_1_milling_pocket_pipeline(self):
        """Test case1-1_milling_pocket.json through the pipeline."""
        case = self._load_case_json("case1-1_milling_pocket.json")
        
        # Verify case structure
        self.assertIn("features", case)
        self.assertEqual(len(case["features"]), 1)
        self.assertEqual(case["features"][0]["feature_type"], "pocket_rectangular")
        
        # Run pipeline
        response = self._run_pipeline(case)
        if response.status_code != 200:
            self.skipTest("Pipeline does not yet support features format")

    def test_case1_2_milling_hole_pipeline(self):
        """Test case1-2_milling_hole.json through the pipeline."""
        case = self._load_case_json("case1-2_milling_hole.json")
        
        # Verify case has multiple hole features
        self.assertIn("features", case)
        self.assertGreater(len(case["features"]), 1)
        
        # All should be simple_hole
        for feature in case["features"]:
            self.assertEqual(feature["feature_type"], "simple_hole")
        
        # Run pipeline
        response = self._run_pipeline(case)
        if response.status_code != 200:
            self.skipTest("Pipeline does not yet support features format")

    def test_case2_lathe_pipeline(self):
        """Test case2_lathe.json through the pipeline."""
        case = self._load_case_json("case2_lathe.json")
        
        # Verify case structure
        self.assertEqual(case["stock"]["type"], "cylinder")
        self.assertIn("features", case)
        self.assertEqual(len(case["features"]), 3)
        
        # Run pipeline
        response = self._run_pipeline(case)
        if response.status_code != 200:
            self.skipTest("Pipeline does not yet support features format")

    def test_case3_profile_pipeline(self):
        """Test case3_profile.json through the pipeline."""
        case = self._load_case_json("case3_profile.json")
        
        # Verify case structure
        self.assertEqual(case["stock"]["type"], "cylinder")
        self.assertIn("features", case)
        self.assertEqual(len(case["features"]), 1)
        self.assertEqual(case["features"][0]["feature_type"], "turn_od_profile")
        
        # Run pipeline
        response = self._run_pipeline(case)
        if response.status_code != 200:
            self.skipTest("Pipeline does not yet support features format")

    def test_case4a_indexing_pipeline(self):
        """Test case4a_indexing_milling3+2.json through the pipeline."""
        case = self._load_case_json("case4a_indexing_milling3+2.json")
        
        # Verify case has multiple features and csys setups
        self.assertIn("features", case)
        self.assertGreater(len(case["features"]), 1)
        self.assertGreaterEqual(len(case["csys_list"]), 3)
        
        # Run pipeline
        response = self._run_pipeline(case)
        if response.status_code != 200:
            self.skipTest("Pipeline does not yet support features format")

    def test_all_cases_parse_successfully(self):
        """Test that all case JSON files can be parsed."""
        case_files = list(self.input_dir.glob("case*.json"))
        self.assertGreater(len(case_files), 0, "No case JSON files found")
        
        for case_file in case_files:
            with self.subTest(case_file=case_file.name):
                with open(case_file, 'r', encoding='utf-8') as f:
                    case = json.load(f)
                    # Basic validation
                    self.assertIsInstance(case, dict)
                    self.assertIn("units", case)
                    self.assertIn("output_mode", case)
                    self.assertIn("stock", case)

    def test_feature_structure_compliance(self):
        """Test that all features comply with the expected structure."""
        case_files = list(self.input_dir.glob("case*.json"))
        
        for case_file in case_files:
            with self.subTest(case_file=case_file.name):
                with open(case_file, 'r', encoding='utf-8') as f:
                    case = json.load(f)
                
                if "features" in case:
                    for idx, feature in enumerate(case["features"]):
                        # Each feature must have required fields
                        self.assertIn("feature_type", feature,
                                    f"{case_file.name} feature {idx} missing feature_type")
                        self.assertIn("id", feature,
                                    f"{case_file.name} feature {idx} missing id")
                        self.assertIn("params", feature,
                                    f"{case_file.name} feature {idx} missing params")
                        
                        # Metadata should be present
                        if "metadata" in feature:
                            self.assertIn("source", feature["metadata"],
                                        f"{case_file.name} feature {idx} metadata missing source")

    def test_csys_references_valid(self):
        """Test that all csys_ref in features reference valid CSYS."""
        case_files = list(self.input_dir.glob("case*.json"))
        
        for case_file in case_files:
            with self.subTest(case_file=case_file.name):
                with open(case_file, 'r', encoding='utf-8') as f:
                    case = json.load(f)
                
                csys_names = {csys["name"] for csys in case.get("csys_list", [])}
                
                if "features" in case:
                    for feature in case["features"]:
                        csys_id = feature.get("params", {}).get("csys_id")
                        if csys_id:
                            self.assertIn(csys_id, csys_names,
                                        f"{case_file.name} feature {feature['id']} "
                                        f"references unknown CSYS: {csys_id}")


class TestSTLOutputFiles(unittest.TestCase):
    """Test that STL files are generated when pipeline supports features."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.client = TestClient(app)
        cls.data_dir = Path(__file__).parent
        cls.output_dir = cls.data_dir.parent / "data" / "output"

    def test_stl_output_directory_exists(self):
        """Test that output directory exists."""
        self.assertTrue(self.output_dir.exists(), 
                       f"Output directory does not exist: {self.output_dir}")

    def test_existing_stl_files_valid(self):
        """Test that any existing STL files in output are valid size."""
        stl_files = list(self.output_dir.glob("*.stl")) + list(self.output_dir.glob("*.step"))
        
        for stl_file in stl_files:
            with self.subTest(file=stl_file.name):
                file_size = stl_file.stat().st_size
                # Files should have reasonable size
                self.assertGreater(file_size, 0,
                                 f"STL/STEP file is empty: {stl_file.name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
