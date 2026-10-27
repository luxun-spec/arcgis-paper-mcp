"""Opt-in tests in ArcGIS Python: PAPER_MCP_TEST_ARCPY=1."""
import os
import unittest


@unittest.skipUnless(os.environ.get('PAPER_MCP_TEST_ARCPY') == '1','requires licensed ArcGIS Python')
class NativeTests(unittest.TestCase):
    def test_globe_projection_centers_the_requested_location(self):
        import arcpy
        from arcgis_paper_mcp.backend import _orthographic
        sr = _orthographic(arcpy,105,32)
        center = arcpy.PointGeometry(arcpy.Point(105,32),arcpy.SpatialReference(4326)).projectAs(sr).firstPoint
        self.assertAlmostEqual(center.X,0,delta=1)
        self.assertAlmostEqual(center.Y,0,delta=1)


if __name__ == '__main__':
    unittest.main()
