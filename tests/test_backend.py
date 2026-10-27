import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS


class BackendTests(unittest.TestCase):
    def test_polygon_styling_uses_geometry_not_unsupported_symbol_type(self):
        from arcgis_paper_mcp.backend import _vector
        symbol = NS()
        sym = NS(renderer=NS(symbol=symbol),updateRenderer=lambda _:None)
        layer = NS(symbology=sym,isFeatureLayer=True)
        m = NS(addDataFromPath=lambda _:layer)
        _vector(m,'area.shp','Boundary',color=[1,2,3,100],width=1)
        self.assertEqual(symbol.outlineWidth,1)
        self.assertEqual(symbol.color,{'RGB':[255,255,255,0]})

    def test_undefined_crs_is_rejected_before_rendering(self):
        from arcgis_paper_mcp.backend import describe
        api = NS(Exists=lambda p: True, Describe=lambda p: NS(spatialReference=NS(name='Unknown', type='Unknown')))
        with self.assertRaisesRegex(ValueError, 'coordinate system'):
            describe(api, 'unknown.shp')

    def test_hydrology_refuses_degree_and_foot_dem(self):
        from arcgis_paper_mcp.backend import metric_cell_area
        for kind, unit in [('Geographic','Degree'),('Projected','Foot')]:
            desc = NS(spatialReference=NS(type=kind, linearUnitName=unit),meanCellWidth=30,meanCellHeight=30)
            with self.assertRaises(ValueError):
                metric_cell_area(desc)

    def test_area_threshold_uses_real_cell_area(self):
        from arcgis_paper_mcp.backend import threshold_cells
        desc = NS(spatialReference=NS(type='Projected',linearUnitName='Meter'),meanCellWidth=100,meanCellHeight=50)
        self.assertEqual(threshold_cells(desc, 2), 400)

    def test_dispatch_does_not_accept_arbitrary_python(self):
        from arcgis_paper_mcp.backend import dispatch
        with self.assertRaisesRegex(ValueError, 'allowed'):
            dispatch('execute_python', {'code':'anything'})

    def test_missing_data_rejected(self):
        from arcgis_paper_mcp.backend import describe
        with self.assertRaises(FileNotFoundError):
            describe(NS(Exists=lambda _:False),'missing.tif')


if __name__ == '__main__':
    unittest.main()
